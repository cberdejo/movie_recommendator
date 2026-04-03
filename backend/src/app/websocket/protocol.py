"""
WebSocket protocol helpers: parsing, response building and safe sending.
"""

import json

from fastapi import WebSocket
from pydantic import ValidationError
from starlette.websockets import WebSocketState

from app.schemas.ws_schemas import WSResponse


def build_error_response(
    message: str,
    error_code: str,
    retryable: bool = True,
) -> WSResponse:
    """Create a normalised error payload for WebSocket clients."""
    return WSResponse(
        type="error",
        content=message,
        error_code=error_code,
        retryable=retryable,
    )


def request_validation_error(err: ValidationError | json.JSONDecodeError) -> WSResponse:
    """Map payload validation / JSON errors to a safe client response."""
    return build_error_response(
        message="Invalid websocket request payload.",
        error_code="invalid_request",
        retryable=True,
    )


async def send_if_open(websocket: WebSocket, text: str) -> None:
    """Send *text* only when the WebSocket is still connected.

    Silently drops the frame on any transport error so callers never
    need to guard against a closed socket themselves.
    """
    if websocket.client_state != WebSocketState.CONNECTED:
        return
    try:
        await websocket.send_text(text)
    except Exception:
        # Covers WebSocketDisconnect, RuntimeError("websocket is not connected"),
        # and any other transport-level error.
        return


async def send_response(websocket: WebSocket, response: WSResponse) -> None:
    """Serialise *response* and deliver it via send_if_open."""
    await send_if_open(websocket, response.model_dump_json())
