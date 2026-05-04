"""
Redis Streams-based event bus for chat generation.

The generation task publishes events with publish_event(); the WebSocket relay
reads them with read_stream(). Streams are namespaced by message_id so a single
generation has a stable, replayable timeline.

Auxiliary keys:
- active:generation:{conversation_id} -> message_id (so resume_conversation can
  discover an in-flight stream).
- interrupt:{message_id} -> "1" (asynchronous interrupt flag the producer polls).
"""

import json
from typing import Any, Iterable

import redis.asyncio as aioredis

from app.core.settings import redis_settings

# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------


def build_stream_key(message_id: str) -> str:
    return f"{redis_settings.stream_key_prefix}{message_id}"


def _active_key(conversation_id: int | str) -> str:
    return f"active:generation:{conversation_id}"


def _interrupt_key(message_id: str) -> str:
    return f"interrupt:{message_id}"


# ---------------------------------------------------------------------------
# Event publication
# ---------------------------------------------------------------------------


def _serialize_content(content: Any) -> str:
    """Redis Streams require string fields. Pass strings through; JSON the rest."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(content)


async def publish_event(
    redis: aioredis.Redis,
    message_id: str,
    event_type: str,
    content: Any = None,
    conversation_id: int | str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Append an event to the stream and (re)set its TTL. Returns the entry id."""
    fields: dict[str, str] = {
        "type": event_type,
        "content": _serialize_content(content),
    }
    if conversation_id is not None:
        fields["conversation_id"] = str(conversation_id)
    if extra:
        for k, v in extra.items():
            fields[k] = _serialize_content(v)

    key = build_stream_key(message_id)
    entry_id = await redis.xadd(key, fields)
    await redis.expire(key, redis_settings.stream_ttl)
    return entry_id


# ---------------------------------------------------------------------------
# Event consumption
# ---------------------------------------------------------------------------


async def read_stream(
    redis: aioredis.Redis,
    message_id: str,
    from_id: str = "0-0",
    block_ms: int | None = None,
    count: int = 100,
) -> list[tuple[str, dict[str, str]]]:
    """
    Read events from a stream starting *after* from_id ("0-0" reads from
    the beginning). Returns a list of (entry_id, fields) tuples, possibly empty.
    """
    if block_ms is None:
        block_ms = redis_settings.stream_read_block_ms

    key = build_stream_key(message_id)
    result = await redis.xread({key: from_id}, block=block_ms, count=count)
    if not result:
        return []

    # XREAD returns: [[stream_key, [(entry_id, {fields}), ...]]]
    out: list[tuple[str, dict[str, str]]] = []
    for _stream, entries in result:
        for entry_id, fields in entries:
            out.append((entry_id, fields))
    return out


async def read_history(
    redis: aioredis.Redis,
    message_id: str,
    from_id: str = "-",
    to_id: str = "+",
) -> list[tuple[str, dict[str, str]]]:
    """Read the entire (already-written) history of a stream with XRANGE."""
    key = build_stream_key(message_id)
    return await redis.xrange(key, min=from_id, max=to_id)


async def stream_exists(redis: aioredis.Redis, message_id: str) -> bool:
    """Return True when a stream key still exists in Redis."""
    return bool(await redis.exists(build_stream_key(message_id)))


# ---------------------------------------------------------------------------
# Active generation registry
# ---------------------------------------------------------------------------


async def mark_active_generation(
    redis: aioredis.Redis,
    conversation_id: int | str,
    message_id: str,
) -> None:
    await redis.set(
        _active_key(conversation_id),
        message_id,
        ex=redis_settings.active_generation_ttl,
    )


async def get_active_generation(
    redis: aioredis.Redis, conversation_id: int | str
) -> str | None:
    return await redis.get(_active_key(conversation_id))


async def clear_active_generation(
    redis: aioredis.Redis, conversation_id: int | str
) -> None:
    await redis.delete(_active_key(conversation_id))


# ---------------------------------------------------------------------------
# Interrupt flag
# ---------------------------------------------------------------------------


async def request_interrupt(redis: aioredis.Redis, message_id: str) -> None:
    await redis.set(_interrupt_key(message_id), "1", ex=redis_settings.interrupt_ttl)


async def is_interrupted(redis: aioredis.Redis, message_id: str) -> bool:
    val = await redis.get(_interrupt_key(message_id))
    return val == "1"


async def clear_interrupt(redis: aioredis.Redis, message_id: str) -> None:
    await redis.delete(_interrupt_key(message_id))


# ---------------------------------------------------------------------------
# Terminal events
# ---------------------------------------------------------------------------

TERMINAL_EVENTS: frozenset[str] = frozenset({"response_done", "error"})


def is_terminal(event_type: str) -> bool:
    return event_type in TERMINAL_EVENTS


def fields_to_response(fields: dict[str, str]) -> dict[str, Any]:
    """Normalise stream fields into the WSResponse-shaped dict expected by the
    relay. `content` is left as a string; the frontend already handles the
    JSON-encoded variants (e.g. node_output)."""
    return {
        "type": fields.get("type", ""),
        "content": fields.get("content", ""),
    }


def collect_assistant_text(entries: Iterable[tuple[str, dict[str, str]]]) -> str:
    """Join all response_chunk contents from a sequence of stream entries."""
    parts: list[str] = []
    for _entry_id, fields in entries:
        if fields.get("type") == "response_chunk":
            parts.append(fields.get("content", ""))
    return "".join(parts)
