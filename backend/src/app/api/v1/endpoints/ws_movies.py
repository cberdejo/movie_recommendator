from fastapi import APIRouter, WebSocket, Depends
from sqlmodel.ext.asyncio.session import AsyncSession
from app.db.session import get_session
from app.websocket.handler import ws_handler_movies

router = APIRouter()


@router.websocket("/movies")
async def ws_movies_endpoint(
    websocket: WebSocket, db: AsyncSession = Depends(get_session)
):
    """
    This endpoint is a WebSocket endpoint for movie recommendations.
    Args:
        websocket: The WebSocket connection.
        db: The database session.
    Returns:
        A 200 OK response if the WebSocket connection is accepted.
        A 500 Internal Server Error response if there is an error accepting the WebSocket connection.
    """
    await ws_handler_movies(websocket, db=db)
