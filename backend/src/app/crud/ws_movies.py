"""
WebSocket handler for movie recommendations.
"""

import asyncio
import json
import time
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.assistants.movie_assistant import build_app
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
    parse_ws_request,
    request_validation_error,
    send_if_open as _send_if_open,
    send_response,
)
from app.schemas.ws_schemas import WSResponse

logger = get_logger("WS_MOVIES_HANDLER")

INTERRUPTED_SUFFIX = "\n\n[message interrupted by the user]"
GRAPH_NODES = {"contextualize", "router", "retrieve", "generate", "generate_general"}

# Graph LangGraph: a single instance, all generation passes through it
app_graph = build_app()

# Model saved in history (LiteLLM; the real model is chosen by the assistant)
CONVERSATION_MODEL_LABEL = "litellm"


async def ws_handler_movies(websocket: WebSocket, db: AsyncSession):
    """WebSocket endpoint for movie recommendations use case."""
    await websocket.accept()

    current_convo_id: int | None = None
    interrupt_event = asyncio.Event()
    generation_task: asyncio.Task | None = None

    async def _cancel_generation() -> None:
        """Cancel current generation immediately and wait for cleanup."""
        nonlocal generation_task

        if generation_task and not generation_task.done():
            interrupt_event.set()
            generation_task.cancel()
            try:
                await generation_task
            except (asyncio.CancelledError, Exception):
                pass

        generation_task = None

    try:
        while True:
            data = await websocket.receive_text()

            try:
                req = parse_ws_request(data)
            except (ValidationError, json.JSONDecodeError) as err:
                await send_response(websocket, request_validation_error(err))
                continue

            if req.type == "interrupt":
                await _handle_interrupt(
                    websocket=websocket,
                    cancel_generation=_cancel_generation,
                    interrupt_event=interrupt_event,
                )
                continue

            if req.type == "start_conversation":
                current_convo_id, generation_task = await _handle_start_conversation(
                    websocket=websocket,
                    db=db,
                    req=req,
                    cancel_generation=_cancel_generation,
                    interrupt_event=interrupt_event,
                )
                continue

            if req.type == "resume_conversation":
                current_convo_id = await _handle_resume_conversation(
                    websocket=websocket,
                    db=db,
                    req=req,
                    current_convo_id=current_convo_id,
                    cancel_generation=_cancel_generation,
                    interrupt_event=interrupt_event,
                )
                continue

            if req.type == "message":
                generation_task = await _handle_message(
                    websocket=websocket,
                    db=db,
                    req=req,
                    current_convo_id=current_convo_id,
                    cancel_generation=_cancel_generation,
                    interrupt_event=interrupt_event,
                )

    except WebSocketDisconnect:
        await _cancel_generation()
        return
    except Exception:
        await _cancel_generation()
        logger.exception("Unhandled websocket server error")
        await send_response(
            websocket,
            build_error_response(
                message="Unexpected server error. Please reconnect.",
                error_code="server_error",
                retryable=False,
            ),
        )
        return


async def _handle_interrupt(
    websocket: WebSocket,
    cancel_generation,
    interrupt_event: asyncio.Event,
) -> None:
    await cancel_generation()
    interrupt_event.clear()
    await send_response(
        websocket,
        WSResponse(type="interrupt_ack", content=None),
    )


async def _handle_start_conversation(
    websocket: WebSocket,
    db: AsyncSession,
    req: Any,
    cancel_generation,
    interrupt_event: asyncio.Event,
) -> tuple[int | None, asyncio.Task | None]:
    await cancel_generation()
    interrupt_event.clear()

    title = _build_conversation_title(req.message or "")

    try:
        convo = await create_conversation(
            title=title,
            model=CONVERSATION_MODEL_LABEL,
            use_case="movies",
            db=db,
        )
        current_convo_id = convo.id

        user_msg = await add_message(
            db=db,
            conversation_id=convo.id,
            role="user",
            content=req.message or "",
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
        return None, None

    await send_response(
        websocket,
        WSResponse(type="conversation_started", content=current_convo_id),
    )

    generation_task = asyncio.create_task(
        _generate_and_stream_langgraph(
            websocket=websocket,
            user_message=req.message or "",
            user_msg_id=user_msg.id,
            convo_id=current_convo_id,
            db=db,
            interrupt_event=interrupt_event,
        )
    )

    return current_convo_id, generation_task


async def _handle_resume_conversation(
    websocket: WebSocket,
    db: AsyncSession,
    req: Any,
    current_convo_id: int | None,
    cancel_generation,
    interrupt_event: asyncio.Event,
) -> int | None:
    if req.convo_id != current_convo_id:
        await cancel_generation()
        interrupt_event.clear()

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
            return current_convo_id

        if not convo or convo.use_case != "movies":
            await send_response(
                websocket,
                build_error_response(
                    message="Conversation not found.",
                    error_code="conversation_not_found",
                    retryable=False,
                ),
            )
            return current_convo_id

        current_convo_id = req.convo_id

    await send_response(
        websocket,
        WSResponse(type="conversation_resumed", content=current_convo_id),
    )
    return current_convo_id


async def _handle_message(
    websocket: WebSocket,
    db: AsyncSession,
    req: Any,
    current_convo_id: int | None,
    cancel_generation,
    interrupt_event: asyncio.Event,
) -> asyncio.Task | None:
    if not current_convo_id:
        await send_response(
            websocket,
            build_error_response(
                message="No active conversation.",
                error_code="no_active_conversation",
                retryable=True,
            ),
        )
        return None

    await cancel_generation()
    interrupt_event.clear()

    try:
        user_msg = await add_message(
            db=db,
            conversation_id=current_convo_id,
            role="user",
            content=req.message or "",
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
        return None

    return asyncio.create_task(
        _generate_and_stream_langgraph(
            websocket=websocket,
            user_message=req.message or "",
            user_msg_id=user_msg.id,
            convo_id=current_convo_id,
            db=db,
            interrupt_event=interrupt_event,
        )
    )


def _build_conversation_title(message: str) -> str:
    return message[:30] + ("..." if len(message) > 30 else "")


def _ws_event(event_type: str, content: Any) -> str:
    return json.dumps({"type": event_type, "content": content})


async def _send_ws_event(websocket: WebSocket, event_type: str, content: Any) -> None:
    await _send_if_open(websocket, _ws_event(event_type, content))


def _map_recent_messages_to_langchain(recent_msgs: list[Any], user_message: str) -> list:
    langchain_messages = []

    for msg in recent_msgs:
        role_val = msg.role.value if hasattr(msg.role, "value") else str(msg.role)

        if role_val == "user":
            langchain_messages.append(HumanMessage(content=msg.content))
        elif role_val in ("assistant", "model"):
            langchain_messages.append(AIMessage(content=msg.content))

    if not langchain_messages:
        langchain_messages = [HumanMessage(content=user_message)]

    return langchain_messages


async def _load_langchain_messages(
    db: AsyncSession,
    convo_id: int,
    user_message: str,
) -> list | None:
    recent_msgs = await get_conversation_with_messages_limited(
        conversation_id=convo_id,
        db=db,
        number_of_messages=llmsettings.number_of_messages_to_contextualize,
    )

    if recent_msgs is None:
        return None

    return _map_recent_messages_to_langchain(recent_msgs, user_message)


async def _send_conversation_not_found_generation_error(websocket: WebSocket) -> None:
    await _send_ws_event(websocket, "thinking_end", None)
    await _send_ws_event(websocket, "graph_end", None)
    await send_response(
        websocket,
        build_error_response(
            message="Conversation not found.",
            error_code="conversation_not_found",
            retryable=False,
        ),
    )
    await _send_ws_event(websocket, "done", "")


def _build_node_output_payload(node_name: str, output: dict[str, Any]) -> dict[str, Any] | None:
    node_data: dict[str, Any] = {"node": node_name}

    if "reformulated_question" in output:
        node_data["reformulated_question"] = output["reformulated_question"]
    if "decision" in output:
        node_data["decision"] = output["decision"]
    if "documents" in output:
        node_data["documents_count"] = len(output["documents"])

    return node_data if len(node_data) > 1 else None


async def _handle_node_transition(
    websocket: WebSocket,
    current_node: str | None,
    next_node: str | None,
) -> str | None:
    if next_node not in GRAPH_NODES or next_node == current_node:
        return current_node

    if current_node:
        await _send_ws_event(websocket, "node_end", current_node)

    await _send_ws_event(websocket, "node_start", next_node)
    return next_node


async def _handle_chain_end_event(
    websocket: WebSocket,
    req_id: str,
    event: dict[str, Any],
    lg_node: str,
) -> str | None:
    if lg_node not in GRAPH_NODES:
        return None

    output = event.get("data", {}).get("output", {})
    if not isinstance(output, dict):
        return None

    reformulated_question = None
    if lg_node == "contextualize" and "reformulated_question" in output:
        reformulated_question = output["reformulated_question"]
        logger.info("[%s] Captured reformulated_question=%r", req_id, reformulated_question)

    node_payload = _build_node_output_payload(lg_node, output)
    if node_payload:
        await _send_ws_event(
            websocket,
            "node_output",
            json.dumps(node_payload),
        )

    return reformulated_question


async def _handle_chat_model_stream_event(
    websocket: WebSocket,
    event: dict[str, Any],
    thinking_end_sent: bool,
    assistant_chunks: list[str],
) -> bool:
    content = event["data"]["chunk"].content
    if not content:
        return thinking_end_sent

    if not thinking_end_sent:
        await _send_ws_event(websocket, "thinking_end", None)
        thinking_end_sent = True

    assistant_chunks.append(content)
    await _send_ws_event(websocket, "response_chunk", content)
    return thinking_end_sent


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
        logger.warning("[%s] Failed to save assistant message after interruption", req_id)


async def _persist_reformulated_question(
    db: AsyncSession,
    message_id: int,
    user_message: str,
    reformulated_question: str | None,
    req_id: str,
) -> None:
    if not reformulated_question or reformulated_question == user_message:
        return

    try:
        await update_message_content(
            db=db,
            message_id=message_id,
            content=reformulated_question,
        )
    except Exception:
        await db.rollback()
        logger.warning(
            "[%s] Failed to update user message with contextualized content",
            req_id,
        )


async def _handle_generation_failure(
    websocket: WebSocket,
    active_node: str | None,
) -> None:
    if active_node:
        await _send_ws_event(websocket, "node_end", active_node)

    await _send_ws_event(websocket, "graph_end", None)
    await send_response(
        websocket,
        build_error_response(
            message="Could not generate a response right now. Please try again.",
            error_code="generation_failed",
            retryable=True,
        ),
    )
    await _send_ws_event(websocket, "done", "")


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
    reformulated_question: str | None,
) -> None:
    if active_node:
        await _send_ws_event(websocket, "node_end", active_node)

    final_response = "".join(assistant_chunks).strip()

    if interrupted and final_response:
        await _send_ws_event(websocket, "response_chunk", INTERRUPTED_SUFFIX)
        final_response += INTERRUPTED_SUFFIX

    if not thinking_end_sent:
        await _send_ws_event(websocket, "thinking_end", None)

    if final_response:
        await _persist_assistant_response(
            db=db,
            convo_id=convo_id,
            final_response=final_response,
            req_id=req_id,
        )
    elif not interrupted:
        msg = "No tokens received from the model."
        logger.error("[%s] %s", req_id, msg)
        await send_response(
            websocket,
            build_error_response(
                message=msg,
                error_code="empty_generation",
                retryable=True,
            ),
        )

    await _persist_reformulated_question(
        db=db,
        message_id=user_msg_id,
        user_message=user_message,
        reformulated_question=reformulated_question,
        req_id=req_id,
    )

    await _send_ws_event(websocket, "graph_end", None)
    await _send_ws_event(websocket, "done", "")


async def _generate_and_stream_langgraph(
    websocket: WebSocket,
    user_message: str,
    user_msg_id: int,
    convo_id: int,
    db: AsyncSession,
    interrupt_event: asyncio.Event | None = None,
):
    """Generate and stream the assistant's response using LangGraph and Postgres history.

    Handles asyncio.CancelledError for immediate interruption via task.cancel().
    Always sends 'done' as the single completion signal.
    """
    req_id = f"movies-c{convo_id}-t{int(time.time() * 1000)}"
    start_ts = time.time()

    assistant_chunks: list[str] = []
    thinking_end_sent = False
    active_node: str | None = None
    interrupted = False
    reformulated_question: str | None = None

    try:
        logger.info(
            "[%s] _generate_and_stream_langgraph: start (convo_id=%s)",
            req_id,
            convo_id,
        )

        await _send_ws_event(websocket, "thinking_start", None)

        langchain_messages = await _load_langchain_messages(
            db=db,
            convo_id=convo_id,
            user_message=user_message,
        )

        if langchain_messages is None:
            await _send_conversation_not_found_generation_error(websocket)
            return

        logger.info(
            "[%s] History → %d msgs, last=%s",
            req_id,
            len(langchain_messages),
            repr(langchain_messages[-1].content[:80]) if langchain_messages else "EMPTY",
        )

        inputs = {"messages": langchain_messages}
        await _send_ws_event(websocket, "graph_start", None)

        async for event in app_graph.astream_events(inputs, config={}, version="v1"):
            if interrupt_event and interrupt_event.is_set():
                interrupted = True
                break

            kind = event["event"]
            meta = event.get("metadata", {})
            lg_node = meta.get("langgraph_node", "")

            active_node = await _handle_node_transition(
                websocket=websocket,
                current_node=active_node,
                next_node=lg_node,
            )

            if kind == "on_chain_end":
                captured_question = await _handle_chain_end_event(
                    websocket=websocket,
                    req_id=req_id,
                    event=event,
                    lg_node=lg_node,
                )
                if captured_question is not None:
                    reformulated_question = captured_question

            if kind == "on_chat_model_stream" and lg_node in {"generate", "generate_general"}:
                thinking_end_sent = await _handle_chat_model_stream_event(
                    websocket=websocket,
                    event=event,
                    thinking_end_sent=thinking_end_sent,
                    assistant_chunks=assistant_chunks,
                )

    except asyncio.CancelledError:
        interrupted = True
    except Exception:
        logger.exception("[%s] LangGraph generation error", req_id)
        await _handle_generation_failure(
            websocket=websocket,
            active_node=active_node,
        )
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
        reformulated_question=reformulated_question,
    )

    elapsed = time.time() - start_ts
    if interrupted:
        logger.info("[%s] Generation interrupted by user after %.2fs", req_id, elapsed)
    else:
        logger.info("[%s] Generation completed in %.2fs", req_id, elapsed)