"""
LangGraph generation pipeline that publishes events to Redis Streams.

The generation task owns its own AsyncSession (so it survives WebSocket
disconnects) and writes every event to a Redis stream keyed by message_id.
A separate relay (websocket/relay.py) forwards those events to the live
WebSocket connection.
"""

import asyncio
import json
import time
from typing import Any

import redis.asyncio as aioredis
from langchain_core.messages import AIMessage, HumanMessage
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logger import log
from app.core.settings import llm_settings
from app.crud.conversation_crud import (
    add_message,
    get_conversation_with_messages_limited,
)
from app.db.session import AsyncSessionLocal
from app.services.history_compressor import compress_pair
from app.services.stream_bus import (
    clear_active_generation,
    clear_interrupt,
    is_interrupted,
    mark_active_generation,
    publish_event,
)
from app.websocket.session import (
    GRAPH_NODES,
    INTERRUPTED_SUFFIX,
    ChatSession,
    app_graph,
)

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def generate_to_redis(
    redis: aioredis.Redis,
    user_message: str,
    convo_id: int,
    message_id: str,
    session: ChatSession,
) -> None:
    """
    Run the LangGraph and publish every event to Redis. Owns its own DB
    sessions so the task is independent of the WebSocket connection.
    """
    req_id = f"movies-c{convo_id}-m{message_id[:8]}"
    start_ts = time.time()

    assistant_chunks: list[str] = []
    thinking_end_published = False
    active_node: str | None = None
    final_generation_node: str | None = None
    interrupted = False

    await mark_active_generation(redis, convo_id, message_id)

    try:
        log.info(
            "[%s] generation start (convo_id=%s message_id=%s)",
            req_id,
            convo_id,
            message_id,
        )
        await _publish(redis, message_id, convo_id, "generation_started", message_id)
        await _publish(redis, message_id, convo_id, "thinking_start", None)

        async with AsyncSessionLocal() as db:
            langchain_messages = await _load_langchain_messages(
                db, convo_id, user_message
            )

        if langchain_messages is None:
            await _publish_conversation_not_found(redis, message_id, convo_id)
            await _cleanup(redis, convo_id, message_id)
            return

        log.info("[%s] history → %d msgs", req_id, len(langchain_messages))
        await _publish(redis, message_id, convo_id, "graph_start", None)

        graph_input = {
            "messages": langchain_messages,
            "reask_count": session.consecutive_reasks,
        }

        async for event in app_graph.astream_events(
            graph_input, config={}, version="v1"
        ):
            if await is_interrupted(redis, message_id):
                interrupted = True
                break

            kind = event["event"]
            lg_node = event.get("metadata", {}).get("langgraph_node", "")

            active_node = await _handle_node_transition(
                redis, message_id, convo_id, active_node, lg_node
            )

            if kind == "on_chain_end":
                await _handle_chain_end_event(
                    redis, message_id, convo_id, req_id, event, lg_node
                )

            if kind == "on_chat_model_stream" and lg_node in {
                "generate_retrieve",
                "generate_general",
                "reask_user",
            }:
                final_generation_node = lg_node
                thinking_end_published = await _handle_stream_chunk(
                    redis,
                    message_id,
                    convo_id,
                    event,
                    thinking_end_published,
                    assistant_chunks,
                )

    except asyncio.CancelledError:
        interrupted = True
        # Don't suppress: the task itself was cancelled (e.g. server shutdown).
        # Run finalization in a shield-friendly fashion.
        await _finalize_on_cancel(
            redis, message_id, convo_id, req_id, assistant_chunks, active_node
        )
        await _cleanup(redis, convo_id, message_id)
        raise
    except Exception:
        log.exception("[%s] LangGraph generation error", req_id)
        await _handle_generation_failure(redis, message_id, convo_id, active_node)
        await _cleanup(redis, convo_id, message_id)
        return

    assistant_msg_id = await _finalize_generation(
        redis=redis,
        message_id=message_id,
        convo_id=convo_id,
        req_id=req_id,
        assistant_chunks=assistant_chunks,
        thinking_end_published=thinking_end_published,
        active_node=active_node,
        interrupted=interrupted,
    )

    if not interrupted:
        if final_generation_node == "reask_user":
            session.consecutive_reasks += 1
        elif final_generation_node in {"generate_retrieve", "generate_general"}:
            session.consecutive_reasks = 0

    if not interrupted:
        final_response = "".join(assistant_chunks).strip()
        session.current_msg_id_assistant = assistant_msg_id
        session.summarize_task = asyncio.create_task(
            compress_pair(
                user_message=user_message,
                assistant_message=final_response,
                token_threshold=llm_settings.message_token_threshold,
            )
        )

    await _cleanup(redis, convo_id, message_id)

    elapsed = time.time() - start_ts
    log.info(
        "[%s] %s in %.2fs",
        req_id,
        "interrupted" if interrupted else "completed",
        elapsed,
    )


# ---------------------------------------------------------------------------
# Event publishing helpers
# ---------------------------------------------------------------------------


async def _publish(
    redis: aioredis.Redis,
    message_id: str,
    convo_id: int,
    event_type: str,
    content: Any,
) -> str:
    return await publish_event(
        redis=redis,
        message_id=message_id,
        event_type=event_type,
        content=content,
        conversation_id=convo_id,
    )


async def _handle_node_transition(
    redis: aioredis.Redis,
    message_id: str,
    convo_id: int,
    current_node: str | None,
    next_node: str | None,
) -> str | None:
    if next_node not in GRAPH_NODES or next_node == current_node:
        return current_node
    if current_node:
        await _publish(redis, message_id, convo_id, "node_end", current_node)
    await _publish(redis, message_id, convo_id, "node_start", next_node)
    return next_node


async def _handle_chain_end_event(
    redis: aioredis.Redis,
    message_id: str,
    convo_id: int,
    req_id: str,
    event: dict[str, Any],
    lg_node: str,
) -> None:
    if lg_node not in GRAPH_NODES:
        return
    output = event.get("data", {}).get("output", {})
    if not isinstance(output, dict):
        return
    node_payload = _build_node_output_payload(lg_node, output)
    if node_payload:
        await _publish(
            redis, message_id, convo_id, "node_output", json.dumps(node_payload)
        )


async def _handle_stream_chunk(
    redis: aioredis.Redis,
    message_id: str,
    convo_id: int,
    event: dict[str, Any],
    thinking_end_published: bool,
    assistant_chunks: list[str],
) -> bool:
    content = event["data"]["chunk"].content
    if not content:
        return thinking_end_published
    if not thinking_end_published:
        await _publish(redis, message_id, convo_id, "thinking_end", None)
        thinking_end_published = True
    assistant_chunks.append(content)
    await _publish(redis, message_id, convo_id, "response_chunk", content)
    return thinking_end_published


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
    redis: aioredis.Redis,
    message_id: str,
    convo_id: int,
    req_id: str,
    assistant_chunks: list[str],
    thinking_end_published: bool,
    active_node: str | None,
    interrupted: bool,
) -> int | None:
    if active_node:
        await _publish(redis, message_id, convo_id, "node_end", active_node)

    final_response = "".join(assistant_chunks).strip()

    if interrupted and final_response:
        await _publish(
            redis, message_id, convo_id, "response_chunk", INTERRUPTED_SUFFIX
        )
        final_response += INTERRUPTED_SUFFIX

    if not thinking_end_published:
        await _publish(redis, message_id, convo_id, "thinking_end", None)

    assistant_msg_id: int | None = None
    if final_response:
        assistant_msg_id = await _persist_assistant_response(
            convo_id, final_response, req_id
        )
    elif not interrupted:
        log.error("[%s] no tokens received from model", req_id)
        await _publish(
            redis,
            message_id,
            convo_id,
            "error",
            "No tokens received from the model.",
        )

    await _publish(redis, message_id, convo_id, "graph_end", None)
    await _publish(redis, message_id, convo_id, "response_done", "")
    return assistant_msg_id


async def _finalize_on_cancel(
    redis: aioredis.Redis,
    message_id: str,
    convo_id: int,
    req_id: str,
    assistant_chunks: list[str],
    active_node: str | None,
) -> None:
    """Best-effort terminal events when the task itself is cancelled."""
    try:
        if active_node:
            await _publish(redis, message_id, convo_id, "node_end", active_node)
        final_response = "".join(assistant_chunks).strip()
        if final_response:
            await _publish(
                redis, message_id, convo_id, "response_chunk", INTERRUPTED_SUFFIX
            )
            await _persist_assistant_response(
                convo_id, final_response + INTERRUPTED_SUFFIX, req_id
            )
        await _publish(redis, message_id, convo_id, "graph_end", None)
        await _publish(redis, message_id, convo_id, "response_done", "")
    except Exception:
        log.exception("[%s] finalize-on-cancel failed", req_id)


async def _handle_generation_failure(
    redis: aioredis.Redis,
    message_id: str,
    convo_id: int,
    active_node: str | None,
) -> None:
    if active_node:
        await _publish(redis, message_id, convo_id, "node_end", active_node)
    await _publish(redis, message_id, convo_id, "graph_end", None)
    await _publish(
        redis,
        message_id,
        convo_id,
        "error",
        "Could not generate a response right now. Please try again.",
    )
    await _publish(redis, message_id, convo_id, "response_done", "")


# ---------------------------------------------------------------------------
# DB helpers (own session)
# ---------------------------------------------------------------------------


async def _persist_assistant_response(
    convo_id: int,
    final_response: str,
    req_id: str,
) -> int | None:
    try:
        async with AsyncSessionLocal() as db:
            msg = await add_message(
                db=db,
                conversation_id=convo_id,
                role="assistant",
                content=final_response,
            )
            return msg.id
    except Exception:
        log.warning("[%s] failed to save assistant message", req_id)
        return None


async def _load_langchain_messages(
    db: AsyncSession,
    convo_id: int,
    user_message: str,
) -> list | None:
    recent_msgs = await get_conversation_with_messages_limited(
        conversation_id=convo_id,
        db=db,
        number_of_messages=llm_settings.number_of_messages_to_contextualize,
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


async def _publish_conversation_not_found(
    redis: aioredis.Redis, message_id: str, convo_id: int
) -> None:
    await _publish(redis, message_id, convo_id, "thinking_end", None)
    await _publish(redis, message_id, convo_id, "graph_end", None)
    await _publish(redis, message_id, convo_id, "error", "Conversation not found.")
    await _publish(redis, message_id, convo_id, "response_done", "")


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


async def _cleanup(redis: aioredis.Redis, convo_id: int, message_id: str) -> None:
    try:
        await clear_active_generation(redis, convo_id)
        await clear_interrupt(redis, message_id)
    except Exception:
        log.exception("cleanup failed for convo=%s msg=%s", convo_id, message_id)
