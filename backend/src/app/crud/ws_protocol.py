import json

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from starlette.websockets import WebSocketState

from app.schemas.ws_schemas import WSRequest, WSResponse


def parse_ws_request(payload: str) -> WSRequest:
    """Parse and validate a raw websocket payload."""
    return WSRequest.model_validate_json(payload)


def build_error_response(
    message: str,
    error_code: str,
    retryable: bool = True,
) -> WSResponse:
    """Create a normalized error payload for websocket clients."""
    return WSResponse(
        type="error",
        content=message,
        error_code=error_code,
        retryable=retryable,
    )


def request_validation_error(err: ValidationError | json.JSONDecodeError) -> WSResponse:
    """Map payload validation errors to a user-safe response."""
    return build_error_response(
        message="Invalid websocket request payload.",
        error_code="invalid_request",
        retryable=True,
    )


async def send_if_open(websocket: WebSocket, text: str) -> None:
    """Send text only if websocket remains connected."""
    if websocket.client_state != WebSocketState.CONNECTED:
        return
    try:
        await websocket.send_text(text)
    except (WebSocketDisconnect, RuntimeError):
        return


async def send_response(websocket: WebSocket, response: WSResponse) -> None:
    """Send a typed websocket response."""
    await send_if_open(websocket, response.model_dump_json())
