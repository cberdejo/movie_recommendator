from fastapi import APIRouter, WebSocket, Depends
from sqlmodel.ext.asyncio.session import AsyncSession
from app.db.session import get_session
from app.crud.ws_movies import ws_handler_movies

router = APIRouter()


@router.websocket("/movies")
async def ws_movies_endpoint(
    websocket: WebSocket, db: AsyncSession = Depends(get_session)
):
    await ws_handler_movies(websocket, db=db)
