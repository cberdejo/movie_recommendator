import httpx

from fastapi import APIRouter

from app.core.config.logger import get_logger
from app.core.config.settings import llmsettings


logger = get_logger(__name__)

router = APIRouter()


@router.get("/", summary="Health Check")
async def health_check():
    """
    Health check endpoint to verify the API and LLM service are running.

    Returns:
        dict: Status information
    """
    llm_status = "connected"

    # Check LLM backend (OpenAI, OpenCode, or custom OpenAI-compatible API)
    try:
        config = llmsettings.get_primary_llm_config()
        # Construct health endpoint from base_url
        health_url = config["base_url"].rstrip("/v1") + "/models"

        async with httpx.AsyncClient() as client:
            response = await client.get(health_url, timeout=5.0)
            response.raise_for_status()
    except Exception as e:
        llm_status = "disconnected"
        logger.error(f"LLM health check failed: {e}")

    status = "ok"
    if llm_status == "disconnected":
        status = "degraded"

    message = "API is running"
    if status == "degraded":
        message += " but LLM health check failed"

    return {
        "status": status,
        "message": message,
        "llm": llm_status,
    }
