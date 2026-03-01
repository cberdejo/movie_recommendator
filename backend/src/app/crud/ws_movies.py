"""
WebSocket handler for movie recommendations.
"""

import asyncio
import json
import time

from fastapi import WebSocket, WebSocketDisconnect
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.assistants.movie_assistant import build_app
from app.crud.conversation_crud import (
    add_message,
    create_conversation,
    get_conversation,
    get_conversation_with_messages_limited,
    update_message_content,
)
from app.core.config.logger import get_logger
from app.core.config.settings import llmsettings
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

    async def _cancel_generation():
        """Cancel current generation immediately and wait for its cleanup."""
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
                await _cancel_generation()
                interrupt_event.clear()
                await send_response(
                    websocket,
                    WSResponse(type="interrupt_ack", content=None),
                )
                continue

            if req.type == "start_conversation":
                await _cancel_generation()
                interrupt_event.clear()

                title = (req.message or "")[:30] + (
                    "..." if len(req.message or "") > 30 else ""
                )
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
                    continue
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

            elif req.type == "resume_conversation":
                if req.convo_id != current_convo_id:
                    await _cancel_generation()
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
                        continue

                    if not convo or convo.use_case != "movies":
                        await send_response(
                            websocket,
                            build_error_response(
                                message="Conversation not found.",
                                error_code="conversation_not_found",
                                retryable=False,
                            ),
                        )
                        continue
                    current_convo_id = req.convo_id

                await send_response(
                    websocket,
                    WSResponse(type="conversation_resumed", content=current_convo_id),
                )

            elif req.type == "message":
                if not current_convo_id:
                    await send_response(
                        websocket,
                        build_error_response(
                            message="No active conversation.",
                            error_code="no_active_conversation",
                            retryable=True,
                        ),
                    )
                    continue

                await _cancel_generation()
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
                    continue

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

GRAPH_NODES = {"contextualize", "router", "retrieve", "generate", "generate_general"}


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
        logger.info("[%s] _generate_and_stream_langgraph: start (convo_id=%s)", req_id, convo_id)

        await _send_if_open(websocket, '{"type": "thinking_start", "content": null}')

        recent_msgs = await get_conversation_with_messages_limited(
            conversation_id=convo_id,
            db=db,
            number_of_messages=llmsettings.number_of_messages_to_contextualize,
        )

        if recent_msgs is None:
            await _send_if_open(websocket, '{"type": "thinking_end", "content": null}')
            await _send_if_open(websocket, '{"type": "graph_end", "content": null}')
            await send_response(
                websocket,
                build_error_response(
                    message="Conversation not found.",
                    error_code="conversation_not_found",
                    retryable=False,
                ),
            )
            await _send_if_open(websocket, '{"type": "done", "content": ""}')
            return

        langchain_messages = []
        for msg in recent_msgs:
            role_val = msg.role.value if hasattr(msg.role, "value") else str(msg.role)
            if role_val == "user":
                langchain_messages.append(HumanMessage(content=msg.content))
            elif role_val in ("assistant", "model"):
                langchain_messages.append(AIMessage(content=msg.content))

        if not langchain_messages:
            langchain_messages = [HumanMessage(content=user_message)]

        logger.info(
            "[%s] History → %d msgs, last=%s",
            req_id,
            len(langchain_messages),
            repr(langchain_messages[-1].content[:80]) if langchain_messages else "EMPTY",
        )

        inputs = {"messages": langchain_messages}

        await _send_if_open(
            websocket,
            json.dumps({"type": "graph_start", "content": None}),
        )

        async for event in app_graph.astream_events(inputs, config={}, version="v1"):
            if interrupt_event and interrupt_event.is_set():
                interrupted = True
                break

            kind = event["event"]
            meta = event.get("metadata", {})
            lg_node = meta.get("langgraph_node", "")

            if lg_node in GRAPH_NODES and lg_node != active_node:
                if active_node:
                    await _send_if_open(
                        websocket,
                        json.dumps({"type": "node_end", "content": active_node}),
                    )
                active_node = lg_node
                await _send_if_open(
                    websocket,
                    json.dumps({"type": "node_start", "content": active_node}),
                )

            if kind == "on_chain_end" and lg_node in GRAPH_NODES:
                output = event.get("data", {}).get("output", {})
                if isinstance(output, dict):
                    if lg_node == "contextualize" and "reformulated_question" in output:
                        reformulated_question = output["reformulated_question"]
                        logger.info("[%s] Captured reformulated_question=%r", req_id, reformulated_question)

                    node_data = {}
                    if "reformulated_question" in output:
                        node_data["reformulated_question"] = output["reformulated_question"]
                    if "decision" in output:
                        node_data["decision"] = output["decision"]
                    if "documents" in output:
                        node_data["documents_count"] = len(output["documents"])
                    if node_data:
                        await _send_if_open(
                            websocket,
                            json.dumps({
                                "type": "node_output",
                                "content": json.dumps({"node": lg_node, **node_data}),
                            }),
                        )

            if kind == "on_chat_model_stream":
                node_name = meta.get("langgraph_node", "")

                if node_name in ["generate", "generate_general"]:
                    content = event["data"]["chunk"].content
                    if content:
                        if not thinking_end_sent:
                            thinking_end_sent = True
                            await _send_if_open(websocket, '{"type": "thinking_end", "content": null}')

                        assistant_chunks.append(content)
                        chunk_msg = json.dumps({"type": "response_chunk", "content": content})
                        await _send_if_open(websocket, chunk_msg)

    except asyncio.CancelledError:
        interrupted = True
    except Exception:
        logger.exception("[%s] LangGraph generation error", req_id)
        if active_node:
            await _send_if_open(
                websocket,
                json.dumps({"type": "node_end", "content": active_node}),
            )
        await _send_if_open(
            websocket,
            json.dumps({"type": "graph_end", "content": None}),
        )
        await send_response(
            websocket,
            build_error_response(
                message="Could not generate a response right now. Please try again.",
                error_code="generation_failed",
                retryable=True,
            ),
        )
        await _send_if_open(websocket, '{"type": "done", "content": ""}')
        return

    # --- Cleanup: runs for both normal completion and interruption ---

    if active_node:
        await _send_if_open(
            websocket,
            json.dumps({"type": "node_end", "content": active_node}),
        )

    final_response = "".join(assistant_chunks).strip()

    if interrupted and final_response:
        await _send_if_open(
            websocket,
            json.dumps({"type": "response_chunk", "content": INTERRUPTED_SUFFIX}),
        )
        final_response += INTERRUPTED_SUFFIX

    if not thinking_end_sent:
        await _send_if_open(websocket, '{"type": "thinking_end", "content": null}')

    # Persist assistant response
    if final_response:
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

    # Persist contextualized question on the user message
    if reformulated_question and reformulated_question != user_message:
        try:
            await update_message_content(
                db=db,
                message_id=user_msg_id,
                content=reformulated_question,
            )
        except Exception:
            await db.rollback()
            logger.warning("[%s] Failed to update user message with contextualized content", req_id)

    await _send_if_open(
        websocket,
        json.dumps({"type": "graph_end", "content": None}),
    )
    await _send_if_open(websocket, '{"type": "done", "content": ""}')

    elapsed = time.time() - start_ts
    if interrupted:
        logger.info("[%s] Generation interrupted by user after %.2fs", req_id, elapsed)
    else:
        logger.info("[%s] Generation completed in %.2fs", req_id, elapsed)
