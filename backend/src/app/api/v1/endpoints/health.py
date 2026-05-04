import httpx
from fastapi import APIRouter

from app.core.logger import log
from app.core.redis import ping_redis
from app.core.settings import llm_settings

router = APIRouter()


@router.get("/", summary="Health Check")
async def health_check():
    """
    Health check endpoint to verify the API, LLM and Redis services.

    Returns:
        dict: Status information
    """
    llm_status = "connected"

    try:
        base_url = llm_settings.openai_base_url.rstrip("/")
        health_url = (
            f"{base_url[:-3]}/models"
            if base_url.endswith("/v1")
            else f"{base_url}/models"
        )

        async with httpx.AsyncClient() as client:
            response = await client.get(health_url, timeout=5.0)
            response.raise_for_status()
    except Exception as e:
        llm_status = "disconnected"
        log.error("llm_health_check_failed", error=str(e))

    redis_status = "connected" if await ping_redis() else "disconnected"

    status = "ok"
    if llm_status == "disconnected" or redis_status == "disconnected":
        status = "degraded"

    message = "API is running"
    if status == "degraded":
        bad = []
        if llm_status == "disconnected":
            bad.append("LLM")
        if redis_status == "disconnected":
            bad.append("Redis")
        message += f" but {', '.join(bad)} health check failed"

    return {
        "status": status,
        "message": message,
        "llm": llm_status,
        "redis": redis_status,
    }
