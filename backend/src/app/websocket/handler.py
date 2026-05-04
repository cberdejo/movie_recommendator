"""
WebSocket handler for movie recommendations.

Generation runs in a detached background task that writes events to Redis;
this handler accepts requests, kicks off generation, and forwards stream
events to the live socket via the relay.
"""

import asyncio
import json
import uuid
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logger import log
from app.core.redis import get_redis
from app.crud.conversation_crud import (
    add_message,
    create_conversation,
    get_conversation,
)
from app.schemas.ws_schemas import WSRequest, WSResponse
from app.services.stream_bus import (
    get_active_generation,
    request_interrupt,
    stream_exists,
)
from app.websocket.generation import generate_to_redis
from app.websocket.protocol import (
    build_error_response,
    request_validation_error,
    send_response,
)
from app.websocket.relay import relay_stream_to_websocket
from app.websocket.session import CONVERSATION_MODEL_LABEL, ChatSession

# ---------------------------------------------------------------------------
# Background task registry
# ---------------------------------------------------------------------------
#
# Generation tasks are detached from any single WebSocket connection. We keep
# strong references here so the asyncio event loop doesn't garbage-collect
# them when the originating handler returns.
_BACKGROUND_TASKS: set[asyncio.Task] = set()


def _spawn_generation(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return task


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def ws_handler_movies(websocket: WebSocket, db: AsyncSession) -> None:
    """
    Main WebSocket endpoint for movie recommendations.

    Request types:
    - interrupt: signal the active generation to stop (Redis flag).
    - start_conversation: create conversation + start generation.
    - resume_conversation: rebind to a conversation; replay if a generation is live.
    - resume_stream: continue forwarding an in-flight stream from a known entry id.
    - message: append a user message + start generation.
    """
    await websocket.accept()
    session = ChatSession()
    redis = get_redis()

    try:
        while True:
            data = await websocket.receive_text()

            try:
                req = WSRequest.model_validate_json(data)
            except (ValidationError, json.JSONDecodeError) as err:
                await send_response(websocket, request_validation_error(err))
                continue

            if req.type == "interrupt":
                await _handle_interrupt(websocket, redis, req, session)

            elif req.type == "start_conversation":
                await _handle_start_conversation(websocket, db, redis, req, session)

            elif req.type == "resume_conversation":
                await _handle_resume_conversation(websocket, db, redis, req, session)

            elif req.type == "resume_stream":
                await _handle_resume_stream(websocket, redis, req, session)

            elif req.type == "message":
                await _handle_message(websocket, db, redis, req, session)

    except WebSocketDisconnect:
        session.client_disconnected = True
        # Cancel only the relay; the generation task keeps running.
        await session.cancel_relay()

    except Exception:
        await session.cancel_relay()
        log.exception("Unhandled websocket server error")
        await send_response(
            websocket,
            build_error_response(
                message="Unexpected server error. Please reconnect.",
                error_code="server_error",
                retryable=False,
            ),
        )


# ---------------------------------------------------------------------------
# Request handlers
# ---------------------------------------------------------------------------


async def _handle_interrupt(
    websocket: WebSocket,
    redis,
    req: Any,
    session: ChatSession,
) -> None:
    target_id = req.message_id or session.active_message_id
    if target_id:
        await request_interrupt(redis, target_id)
    await send_response(websocket, WSResponse(type="interrupt_ack", content=None))


async def _handle_start_conversation(
    websocket: WebSocket,
    db: AsyncSession,
    redis,
    req: Any,
    session: ChatSession,
) -> None:
    await session.collect_summarization(db)
    await session.cancel_relay()
    session.consecutive_reasks = 0

    title = _build_conversation_title(req.message or "")

    try:
        convo = await create_conversation(
            title=title,
            model=CONVERSATION_MODEL_LABEL,
            use_case="movies",
            db=db,
        )
        raw = req.message or ""
        user_msg = await add_message(
            db=db,
            conversation_id=convo.id,
            role="user",
            content=raw,
            raw_content=raw,
        )
    except Exception:
        await db.rollback()
        log.exception("Failed starting conversation")
        await send_response(
            websocket,
            build_error_response(
                message="Could not start the conversation.",
                error_code="conversation_start_failed",
                retryable=True,
            ),
        )
        return

    session.convo_id = convo.id
    session.current_msg_id = user_msg.id

    await send_response(
        websocket, WSResponse(type="conversation_started", content=convo.id)
    )

    await _start_generation(websocket, redis, session, convo.id, raw)


async def _handle_resume_conversation(
    websocket: WebSocket,
    db: AsyncSession,
    redis,
    req: Any,
    session: ChatSession,
) -> None:
    same_convo = req.convo_id == session.convo_id

    if not same_convo:
        await session.collect_summarization(db)
        await session.cancel_relay()
        session.current_msg_id = None
        session.current_msg_id_assistant = None
        session.consecutive_reasks = 0

        try:
            convo = await get_conversation(req.convo_id, db=db)
        except Exception:
            await db.rollback()
            log.exception("Failed loading conversation to resume")
            await send_response(
                websocket,
                build_error_response(
                    message="Could not resume the conversation.",
                    error_code="conversation_resume_failed",
                    retryable=True,
                ),
            )
            return

        if not convo or convo.use_case != "movies":
            await send_response(
                websocket,
                build_error_response(
                    message="Conversation not found.",
                    error_code="conversation_not_found",
                    retryable=False,
                ),
            )
            return

        session.convo_id = req.convo_id

    await send_response(
        websocket, WSResponse(type="conversation_resumed", content=session.convo_id)
    )

    # Prefer the client's explicit stream pointer. If it does not have one,
    # fall back to any in-flight stream registered for this conversation.
    registered_message_id = await get_active_generation(redis, session.convo_id)
    active_message_id = req.message_id or registered_message_id
    if active_message_id:
        if req.message_id and not registered_message_id:
            if not await stream_exists(redis, req.message_id):
                await send_response(
                    websocket,
                    WSResponse(
                        type="response_done",
                        content="",
                        message_id=req.message_id,
                        conversation_id=session.convo_id,
                    ),
                )
                return
        await _start_relay(
            websocket,
            redis,
            session,
            active_message_id,
            req.from_id or "0-0",
        )


async def _handle_resume_stream(
    websocket: WebSocket,
    redis,
    req: Any,
    session: ChatSession,
) -> None:
    """Continue forwarding an in-flight stream from a known entry id."""
    await session.cancel_relay()
    if req.convo_id:
        session.convo_id = req.convo_id
    if not await stream_exists(redis, req.message_id):
        await send_response(
            websocket,
            WSResponse(
                type="response_done",
                content="",
                message_id=req.message_id,
                conversation_id=session.convo_id,
            ),
        )
        return
    from_id = req.from_id or "0-0"
    await _start_relay(websocket, redis, session, req.message_id, from_id)


async def _handle_message(
    websocket: WebSocket,
    db: AsyncSession,
    redis,
    req: Any,
    session: ChatSession,
) -> None:
    if not session.convo_id:
        await send_response(
            websocket,
            build_error_response(
                message="No active conversation.",
                error_code="no_active_conversation",
                retryable=True,
            ),
        )
        return

    # Refuse to start a new turn while one is in flight for this conversation.
    existing = await get_active_generation(redis, session.convo_id)
    if existing:
        await send_response(
            websocket,
            build_error_response(
                message="A response is already being generated.",
                error_code="generation_in_progress",
                retryable=True,
            ),
        )
        return

    await session.collect_summarization(db)
    await session.cancel_relay()

    raw = req.message or ""
    try:
        user_msg = await add_message(
            db=db,
            conversation_id=session.convo_id,
            role="user",
            content=raw,
            raw_content=raw,
        )
    except Exception:
        await db.rollback()
        log.exception("Failed saving user message")
        await send_response(
            websocket,
            build_error_response(
                message="Could not save your message.",
                error_code="message_persist_failed",
                retryable=True,
            ),
        )
        return

    session.current_msg_id = user_msg.id
    await _start_generation(websocket, redis, session, session.convo_id, raw)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _start_generation(
    websocket: WebSocket,
    redis,
    session: ChatSession,
    convo_id: int,
    user_message: str,
) -> None:
    """Spawn detached generation and a relay bound to this socket."""
    message_id = uuid.uuid4().hex
    session.reset_stream(message_id)

    _spawn_generation(
        generate_to_redis(
            redis=redis,
            user_message=user_message,
            convo_id=convo_id,
            message_id=message_id,
            session=session,
        )
    )
    await _start_relay(websocket, redis, session, message_id, "0-0")


async def _start_relay(
    websocket: WebSocket,
    redis,
    session: ChatSession,
    message_id: str,
    from_id: str,
) -> None:
    session.relay_task = asyncio.create_task(
        relay_stream_to_websocket(
            websocket=websocket,
            redis=redis,
            session=session,
            message_id=message_id,
            from_id=from_id,
        )
    )


def _build_conversation_title(message: str) -> str:
    return message[:30] + ("..." if len(message) > 30 else "")
