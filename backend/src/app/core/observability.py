"""
Optional Langfuse observability bootstrap.

Returns the singleton Langfuse client when keys are configured; returns None
otherwise so dev environments without credentials boot cleanly.
"""

from typing import Optional

from app.core.logger import log
from app.core.settings import observability_settings


def init_langfuse() -> Optional[object]:
    """Initialise the Langfuse client. Returns None if disabled."""
    if not observability_settings.enabled:
        log.info("langfuse_disabled")
        return None

    try:
        from langfuse import Langfuse, get_client
    except ImportError:
        log.warning("langfuse_import_failed")
        return None

    Langfuse(
        host=observability_settings.host or None,
        public_key=observability_settings.public_key,
        secret_key=observability_settings.secret_key,
        sample_rate=observability_settings.sample_rate,
    )
    client = get_client()
    try:
        if client.auth_check():
            log.info(
                "langfuse_connected",
                host=observability_settings.host,
                sample_rate=observability_settings.sample_rate,
            )
        else:
            log.warning("langfuse_auth_failed", host=observability_settings.host)
    except Exception:
        log.exception("langfuse_init_error")
        return None
    return client


def shutdown_langfuse(client: Optional[object]) -> None:
    if client is None:
        return
    try:
        client.flush()
    except Exception:
        log.exception("langfuse_flush_failed")
