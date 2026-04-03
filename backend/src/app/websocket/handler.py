"""
WebSocket handler for movie recommendations.
"""

import asyncio
import json
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config.logger import get_logger
from app.crud.conversation_crud import add_message, create_conversation, get_conversation
from app.schemas.ws_schemas import WSRequest, WSResponse
from app.websocket.generation import generate_and_stream
from app.websocket.protocol import build_error_response, request_validation_error, send_response
from app.websocket.session import CONVERSATION_MODEL_LABEL, ChatSession

logger = get_logger("WS_MOVIES_HANDLER")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def ws_handler_movies(websocket: WebSocket, db: AsyncSession) -> None:
    """
    Main WebSocket endpoint for movie recommendations.

    Request types:
    - interrupt: Interrupt the current generation.
    - start_conversation: Start a new conversation.
    - resume_conversation: Resume a conversation.
    - message: Send a message to the conversation.
    """
    await websocket.accept()
    session = ChatSession()

    try:
        while True:
            data = await websocket.receive_text()

            try:
                req = WSRequest.model_validate_json(data)
            except (ValidationError, json.JSONDecodeError) as err:
                await send_response(websocket, request_validation_error(err))
                continue

            if req.type == "interrupt":
                await _handle_interrupt(websocket, session)

            elif req.type == "start_conversation":
                await _handle_start_conversation(websocket, db, req, session)

            elif req.type == "resume_conversation":
                await _handle_resume_conversation(websocket, db, req, session)

            elif req.type == "message":
                await _handle_message(websocket, db, req, session)

    except WebSocketDisconnect:
        session.client_disconnected = True
        session.interrupt_event.set()
        await session.cancel_generation()

    except Exception:
        await session.cancel_generation()
        logger.exception("Unhandled websocket server error")
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


async def _handle_interrupt(websocket: WebSocket, session: ChatSession) -> None:
    await session.cancel_generation()
    session.reset_interrupt()
    await send_response(websocket, WSResponse(type="interrupt_ack", content=None))


async def _handle_start_conversation(
    websocket: WebSocket,
    db: AsyncSession,
    req: Any,
    session: ChatSession,
) -> None:
    await session.collect_summarization(db)
    await session.cancel_generation()
    session.reset_interrupt()
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
        logger.exception("Failed starting conversation")
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

    session.generation_task = asyncio.create_task(
        generate_and_stream(
            websocket=websocket,
            user_message=raw,
            convo_id=convo.id,
            db=db,
            session=session,
        )
    )


async def _handle_resume_conversation(
    websocket: WebSocket,
    db: AsyncSession,
    req: Any,
    session: ChatSession,
) -> None:
    if req.convo_id == session.convo_id:
        await send_response(
            websocket,
            WSResponse(type="conversation_resumed", content=session.convo_id),
        )
        return

    await session.collect_summarization(db)
    await session.cancel_generation()
    session.reset_interrupt()
    session.current_msg_id = None
    session.current_msg_id_assistant = None
    session.consecutive_reasks = 0

    try:
        convo = await get_conversation(req.convo_id, db=db)
    except Exception:
        await db.rollback()
        logger.exception("Failed loading conversation to resume")
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


async def _handle_message(
    websocket: WebSocket,
    db: AsyncSession,
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

    # 1. Flush previous turn's summarization to DB before loading history.
    await session.collect_summarization(db)

    # 2. Cancel any running generation.
    await session.cancel_generation()
    session.reset_interrupt()

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
        logger.exception("Failed saving user message")
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
    session.generation_task = asyncio.create_task(
        generate_and_stream(
            websocket=websocket,
            user_message=raw,
            convo_id=session.convo_id,
            db=db,
            session=session,
        )
    )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _build_conversation_title(message: str) -> str:
    return message[:30] + ("..." if len(message) > 30 else "")
