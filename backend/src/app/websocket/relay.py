"""
Relay Redis stream events to a WebSocket connection.

The relay is the only piece bound to the WebSocket connection: cancelling it
stops forwarding without touching the underlying generation task.
"""

import asyncio

import redis.asyncio as aioredis
from fastapi import WebSocket
from starlette.websockets import WebSocketState

from app.core.logger import log
from app.schemas.ws_schemas import WSResponse
from app.services.stream_bus import is_terminal, read_stream
from app.websocket.protocol import send_response
from app.websocket.session import ChatSession


async def relay_stream_to_websocket(
    websocket: WebSocket,
    redis: aioredis.Redis,
    session: ChatSession,
    message_id: str,
    from_id: str = "0-0",
) -> None:
    """
    Continuously read events from Redis and send them to the client.

    Stops when:
      - a terminal event (`response_done` / `error`) is forwarded;
      - the WebSocket disconnects;
      - the task is cancelled by the handler.
    """
    session.active_message_id = message_id
    session.last_stream_id = from_id

    try:
        while True:
            if websocket.client_state != WebSocketState.CONNECTED:
                return

            try:
                entries = await read_stream(
                    redis=redis,
                    message_id=message_id,
                    from_id=session.last_stream_id,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("relay: read_stream failed")
                await asyncio.sleep(0.5)
                continue

            if not entries:
                continue

            for entry_id, fields in entries:
                event_type = fields.get("type", "")
                content = fields.get("content", "")
                raw_conversation_id = fields.get("conversation_id")
                conversation_id = (
                    int(raw_conversation_id)
                    if raw_conversation_id and raw_conversation_id.isdigit()
                    else None
                )
                response = WSResponse(
                    type=event_type,
                    content=content,
                    stream_id=entry_id,
                    message_id=message_id,
                    conversation_id=conversation_id,
                )
                await send_response(websocket, response)
                session.last_stream_id = entry_id

                if is_terminal(event_type):
                    if event_type == "response_done":
                        session.reset_stream(None)
                    return

    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("relay: unexpected failure (message_id=%s)", message_id)
