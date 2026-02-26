"""
Main API router for the application.

This module sets up the primary FastAPI router, includes sub-routers for different API endpoints,
and provides utility endpoints such as health checks. All API routes should be registered here
either directly or via sub-routers.
"""

from fastapi import APIRouter


from app.api.v1.endpoints.conversations_routes import router as conversations_router
from app.api.v1.endpoints.ws_movies import router as ws_movies_router
from app.api.v1.endpoints.health import router as health_router

api_router = APIRouter()


# Include sub-routers
api_router.include_router(health_router, prefix="/health", tags=["Health"])
api_router.include_router(
    conversations_router, prefix="/conversations", tags=["Conversations"]
)
api_router.include_router(ws_movies_router, prefix="/ws", tags=["Movies"])
