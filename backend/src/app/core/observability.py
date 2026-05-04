"""
Optional Langfuse observability bootstrap.

Returns the singleton Langfuse client when keys are configured; returns None
otherwise so dev environments without credentials boot cleanly.
"""

from typing import Optional

from app.core.logger import log
from app.core.settings import observabilitysettings


def init_langfuse() -> Optional[object]:
    """Initialise the Langfuse client. Returns None if disabled."""
    if not observabilitysettings.enabled:
        log.info("langfuse_disabled")
        return None

    try:
        from langfuse import Langfuse, get_client
    except ImportError:
        log.warning("langfuse_import_failed")
        return None

    Langfuse(
        host=observabilitysettings.langfuse_host or None,
        public_key=observabilitysettings.langfuse_public_key,
        secret_key=observabilitysettings.langfuse_secret_key,
        sample_rate=observabilitysettings.langfuse_sample_rate,
    )
    client = get_client()
    try:
        if client.auth_check():
            log.info(
                "langfuse_connected",
                host=observabilitysettings.langfuse_host,
                sample_rate=observabilitysettings.langfuse_sample_rate,
            )
        else:
            log.warning(
                "langfuse_auth_failed", host=observabilitysettings.langfuse_host
            )
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
