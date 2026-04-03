"""
WebSocket handler for movie recommendations.

Turn N — user message arrives
─────────────────────────────────────
add_message(content=raw, raw_content=raw)   ← immediate write to DB

_generate_and_stream()
  │  reads message history from Postgres:
  │    previous messages use msg.content (contextualized or raw if fallback)
  │    the current message is already in Postgres as raw
  │
  └─ when finished → launches contextualize_task in background

Turn N (background, while user is reading)
──────────────────────────────────────────────
contextualize_question_background() finishes
  → UPDATE messages SET content = <contextualized> WHERE id = user_msg_id
     (if the contextualized result equals the raw, no UPDATE is done — saves writes)

Turn N+1 — next message arrives
─────────────────────────────────────
_load_langchain_messages() reads from Postgres
  → the message from turn N already has content = contextualized (if finished in time)
  → if it didn’t finish in time, content is still raw → natural fallback
  → pre_contextualized_question in ChatSession is no longer needed
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.assistants.movie_assistant import build_app, summarize_question_background
from app.core.config.logger import get_logger
from app.core.config.settings import llmsettings
from app.crud.conversation_crud import (
    add_message,
    create_conversation,
    get_conversation,
    get_conversation_with_messages_limited,
    update_message_content,
)
from app.crud.ws_protocol import (
    build_error_response,
    request_validation_error,
    send_if_open as _send_if_open,
    send_response,
)
from app.schemas.ws_schemas import WSRequest, WSResponse

logger = get_logger("WS_MOVIES_HANDLER")

INTERRUPTED_SUFFIX = "\n\n[message interrupted by the user]"

# Graph nodes that emit progress events to the client.

GRAPH_NODES = frozenset(
    {
        "router",
        "retrieve",
        "contextualize",
        "generate_retrieve",
        "generate_general",
        "reask_user",
    }
)
app_graph = build_app()

CONVERSATION_MODEL_LABEL = "movie agent v1"


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
@dataclass
class ChatSession:
    """All mutable state for a WebSocket connection.
    - convo_id: active conversation.
    - generation_task: running asyncio generation task.
    - contextualize_task: background contextualization task.
    - current_msg_id: ID of the current user message.
    - interrupt_event: shared interrupt signal with the generation task.
    - client_disconnected: disables DB writes after disconnect.
    """

    convo_id: int | None = None
    generation_task: asyncio.Task | None = None
    contextualize_task: asyncio.Task | None = None
    current_msg_id: int | None = None
    interrupt_event: asyncio.Event = field(default_factory=asyncio.Event)
    client_disconnected: bool = False
    consecutive_reasks: int = 0

    async def cancel_generation(self) -> None:
        if self.generation_task and not self.generation_task.done():
            self.interrupt_event.set()
            self.generation_task.cancel()
            try:
                await self.generation_task
            except (asyncio.CancelledError, Exception):
                pass
        self.generation_task = None

    async def collect_contextualization(self, db: AsyncSession) -> None:
        if self.contextualize_task is None or self.current_msg_id is None:
            return
        if self.contextualize_task.done():
            try:
                result = self.contextualize_task.result()
                await update_message_content(db, self.current_msg_id, result)
            except Exception:
                pass  # fallback: content stays as raw, which is correct
        else:
            self.contextualize_task.cancel()
        self.contextualize_task = None
        self.current_msg_id = None

    def reset_interrupt(self) -> None:
        self.interrupt_event.clear()


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
    Args:
        websocket: The WebSocket connection.
        db: The database session.
    Returns:
        None
    Raises:
        WebSocketDisconnect: If the WebSocket connection is disconnected.
        Exception: If an unexpected error occurs.
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
    """
    Handles the interrupt request.
    Args:
        websocket: The WebSocket connection.
        session: The chat session.
    Returns:
        None
    """
    await session.cancel_generation()
    session.reset_interrupt()
    await send_response(websocket, WSResponse(type="interrupt_ack", content=None))


async def _handle_start_conversation(
    websocket: WebSocket,
    db: AsyncSession,
    req: Any,
    session: ChatSession,
) -> None:
    """
    Handles the start conversation request.
    Args:
        websocket: The WebSocket connection.
        db: The database session.
        req: The request.
        session: The chat session.
    Returns:
        None
    """
    await session.collect_contextualization(db)
    await session.cancel_generation()
    session.reset_interrupt()
    session.consecutive_reasks = 0  # reset consecutive reasks
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
            content=raw,  # this will be updated by the contextualization task
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
        _generate_and_stream(
            websocket=websocket,
            user_message=raw,
            user_msg_id=user_msg.id,
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
    """
    Handles the resume conversation request.
    Args:
        websocket: The WebSocket connection.
        db: The database session.
        req: The request.
        session: The chat session.
    Returns:
        None
    """
    if req.convo_id == session.convo_id:
        await send_response(
            websocket, WSResponse(type="conversation_resumed", content=session.convo_id)
        )
        return

    await session.collect_contextualization(db)
    await session.cancel_generation()
    session.reset_interrupt()
    session.current_msg_id = None  # discarding pending contextualization result
    session.consecutive_reasks = 0  # reset consecutive reasks

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
    """
    Handles the message request.
    Args:
        websocket: The WebSocket connection.
        db: The database session.
        req: The request.
        session: The chat session.
    Returns:
        None
    """
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

    # 1. Collect previous turn's contextualization result and UPDATE in Postgres
    await session.collect_contextualization(db)

    # 2. Cancel any running generation
    await session.cancel_generation()
    session.reset_interrupt()

    raw = req.message or ""
    try:
        user_msg = await add_message(
            db=db,
            conversation_id=session.convo_id,
            role="user",
            content=raw,  # this will be updated by the contextualization task
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
        _generate_and_stream(
            websocket=websocket,
            user_message=raw,
            user_msg_id=user_msg.id,
            convo_id=session.convo_id,
            db=db,
            session=session,
        )
    )


# ---------------------------------------------------------------------------
# Generation pipeline
# ---------------------------------------------------------------------------


async def _generate_and_stream(
    websocket: WebSocket,
    user_message: str,
    user_msg_id: int,
    convo_id: int,
    db: AsyncSession,
    session: ChatSession,
) -> None:
    """
    Handles the generation and streaming request
    Args:
        websocket: The WebSocket connection.
        user_message: The user message.
        user_msg_id: The user message ID.
        convo_id: The conversation ID.
        db: The database session.
        session: The chat session.
    Returns:
        None
    """
    req_id = f"movies-c{convo_id}-t{int(time.time() * 1000)}"
    start_ts = time.time()

    assistant_chunks: list[str] = []
    thinking_end_sent = False
    active_node: str | None = None
    final_generation_node: str | None = None
    interrupted = False

    try:
        logger.info("[%s] generation start (convo_id=%s)", req_id, convo_id)
        await _send_event(websocket, "thinking_start", None)

        langchain_messages = await _load_langchain_messages(db, convo_id, user_message)
        if langchain_messages is None:
            await _send_conversation_not_found_error(websocket)
            return

        logger.info("[%s] history → %d msgs", req_id, len(langchain_messages))

        await _send_event(websocket, "graph_start", None)

        graph_input = {
            "messages": langchain_messages,
            "reask_count": session.consecutive_reasks,
        }
        async for event in app_graph.astream_events(
            graph_input, config={}, version="v1"
        ):
            if session.interrupt_event.is_set():
                interrupted = True
                break

            kind = event["event"]
            lg_node = event.get("metadata", {}).get("langgraph_node", "")

            active_node = await _handle_node_transition(websocket, active_node, lg_node)

            if kind == "on_chain_end":
                await _handle_chain_end_event(websocket, req_id, event, lg_node)

            if kind == "on_chat_model_stream" and lg_node in {
                "generate_retrieve",
                "generate_general",
                "reask_user",
            }:
                final_generation_node = lg_node
                thinking_end_sent = await _handle_stream_chunk(
                    websocket, event, thinking_end_sent, assistant_chunks
                )

    except asyncio.CancelledError:
        interrupted = True
    except Exception:
        logger.exception("[%s] LangGraph generation error", req_id)
        await _handle_generation_failure(websocket, active_node)
        return

    await _finalize_generation(
        websocket=websocket,
        db=db,
        req_id=req_id,
        user_message=user_message,
        user_msg_id=user_msg_id,
        convo_id=convo_id,
        assistant_chunks=assistant_chunks,
        thinking_end_sent=thinking_end_sent,
        active_node=active_node,
        interrupted=interrupted,
        skip_db=session.client_disconnected,
    )

    if not interrupted:
        if final_generation_node == "reask_user":
            session.consecutive_reasks += 1
        elif final_generation_node in {"generate_retrieve", "generate_general"}:
            session.consecutive_reasks = 0

    # Launch background contextualization for the NEXT turn.
    # current_msg_id is already set in session (assigned before this task was created).
    # collect_contextualization() will do the UPDATE when the next message arrives.
    if not session.client_disconnected:
        session.contextualize_task = asyncio.create_task(
            summarize_question_background(user_message)
        )

    elapsed = time.time() - start_ts
    logger.info(
        "[%s] %s in %.2fs",
        req_id,
        "interrupted" if interrupted else "completed",
        elapsed,
    )


# ---------------------------------------------------------------------------
# Event helpers
# ---------------------------------------------------------------------------


def _ws_event(event_type: str, content: Any) -> str:
    return json.dumps({"type": event_type, "content": content})


async def _send_event(websocket: WebSocket, event_type: str, content: Any) -> None:
    await _send_if_open(websocket, _ws_event(event_type, content))


async def _handle_node_transition(
    websocket: WebSocket,
    current_node: str | None,
    next_node: str | None,
) -> str | None:
    """Emits node_end / node_start when the active graph node changes."""
    if next_node not in GRAPH_NODES or next_node == current_node:
        return current_node
    if current_node:
        await _send_event(websocket, "node_end", current_node)
    await _send_event(websocket, "node_start", next_node)
    return next_node


async def _handle_chain_end_event(
    websocket: WebSocket,
    req_id: str,
    event: dict[str, Any],
    lg_node: str,
) -> None:
    """Emits node_output with useful metadata for the client (LangGraphPanel)."""
    if lg_node not in GRAPH_NODES:
        return

    output = event.get("data", {}).get("output", {})
    if not isinstance(output, dict):
        return

    node_payload = _build_node_output_payload(lg_node, output)
    if node_payload:
        await _send_event(websocket, "node_output", json.dumps(node_payload))


async def _handle_stream_chunk(
    websocket: WebSocket,
    event: dict[str, Any],
    thinking_end_sent: bool,
    assistant_chunks: list[str],
) -> bool:
    """Sends a token to the client; emits thinking_end on the first."""
    content = event["data"]["chunk"].content
    if not content:
        return thinking_end_sent

    if not thinking_end_sent:
        await _send_event(websocket, "thinking_end", None)
        thinking_end_sent = True

    assistant_chunks.append(content)
    await _send_event(websocket, "response_chunk", content)
    return thinking_end_sent


def _build_node_output_payload(
    node_name: str, output: dict[str, Any]
) -> dict[str, Any] | None:
    node_data: dict[str, Any] = {"node": node_name}
    if "decision" in output:
        node_data["decision"] = output["decision"]
    if "media_type" in output:
        mt = str(output["media_type"]).strip().lower()
        if mt not in ("movie", "series", "any"):
            mt = "any"
        node_data["media_type"] = mt
    if "documents" in output:
        node_data["documents_count"] = len(output["documents"])
    if "needs_reask" in output:
        node_data["needs_reask"] = output["needs_reask"]
    if "contextualized_question" in output:
        node_data["rewritten_question"] = output["contextualized_question"]
    if "rewrote" in output:
        node_data["rewrote"] = output["rewrote"]
    return node_data if len(node_data) > 1 else None


# ---------------------------------------------------------------------------
# Finalization
# ---------------------------------------------------------------------------


async def _finalize_generation(
    websocket: WebSocket,
    db: AsyncSession,
    req_id: str,
    user_message: str,
    user_msg_id: int,
    convo_id: int,
    assistant_chunks: list[str],
    thinking_end_sent: bool,
    active_node: str | None,
    interrupted: bool,
    skip_db: bool,
) -> None:
    """
    Closes streaming events and persists the assistant's response.
    skip_db=True when the client has already disconnected.
    """
    if active_node:
        await _send_event(websocket, "node_end", active_node)

    final_response = "".join(assistant_chunks).strip()

    if interrupted and final_response:
        await _send_event(websocket, "response_chunk", INTERRUPTED_SUFFIX)
        final_response += INTERRUPTED_SUFFIX

    if not thinking_end_sent:
        await _send_event(websocket, "thinking_end", None)

    if not skip_db:
        if final_response:
            await _persist_assistant_response(db, convo_id, final_response, req_id)
        elif not interrupted:
            logger.error("[%s] no tokens received from model", req_id)
            await send_response(
                websocket,
                build_error_response(
                    message="No tokens received from the model.",
                    error_code="empty_generation",
                    retryable=True,
                ),
            )

    await _send_event(websocket, "graph_end", None)
    await _send_event(websocket, "response_done", "")


async def _handle_generation_failure(
    websocket: WebSocket,
    active_node: str | None,
) -> None:
    if active_node:
        await _send_event(websocket, "node_end", active_node)
    await _send_event(websocket, "graph_end", None)
    await send_response(
        websocket,
        build_error_response(
            message="Could not generate a response right now. Please try again.",
            error_code="generation_failed",
            retryable=True,
        ),
    )
    await _send_event(websocket, "response_done", "")


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


async def _persist_assistant_response(
    db: AsyncSession,
    convo_id: int,
    final_response: str,
    req_id: str,
) -> None:
    try:
        await add_message(
            db=db,
            conversation_id=convo_id,
            role="assistant",
            content=final_response,
        )
    except Exception:
        await db.rollback()
        logger.warning("[%s] failed to save assistant message", req_id)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _build_conversation_title(message: str) -> str:
    return message[:30] + ("..." if len(message) > 30 else "")


async def _load_langchain_messages(
    db: AsyncSession,
    convo_id: int,
    user_message: str,
) -> list | None:
    """
    Loads the previous messages from the database
    Args:
        db: The database session.
        convo_id: The conversation ID.
        user_message: The user message.
    Returns:
        The list of messages.
    """
    recent_msgs = await get_conversation_with_messages_limited(
        conversation_id=convo_id,
        db=db,
        number_of_messages=llmsettings.number_of_messages_to_contextualize,
    )
    if recent_msgs is None:
        return None
    return _map_messages_to_langchain(recent_msgs, user_message)


def _map_messages_to_langchain(recent_msgs: list[Any], user_message: str) -> list:
    langchain_messages = []
    for msg in recent_msgs:
        role = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
        if role == "user":
            langchain_messages.append(HumanMessage(content=msg.content))
        elif role in ("assistant", "model"):
            langchain_messages.append(AIMessage(content=msg.content))
    return langchain_messages or [HumanMessage(content=user_message)]


async def _send_conversation_not_found_error(websocket: WebSocket) -> None:
    await _send_event(websocket, "thinking_end", None)
    await _send_event(websocket, "graph_end", None)
    await send_response(
        websocket,
        build_error_response(
            message="Conversation not found.",
            error_code="conversation_not_found",
            retryable=False,
        ),
    )
    await _send_event(websocket, "response_done", "")
