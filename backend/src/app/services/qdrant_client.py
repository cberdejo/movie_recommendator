from qdrant_client import AsyncQdrantClient, QdrantClient

from app.core.config.settings import qdrantsettings


def get_qdrant_client() -> QdrantClient:
    """
    Create a synchronous Qdrant client using central app settings.

    This is intended for offline scripts such as app.db.populate_movies_qdrant.
    """
    if qdrantsettings.qdrant_api_key:
        return QdrantClient(
            url=qdrantsettings.qdrant_endpoint,
            api_key=qdrantsettings.qdrant_api_key,
        )

    return QdrantClient(
        host=qdrantsettings.qdrant_host,
        port=int(qdrantsettings.qdrant_port),
    )


def get_async_qdrant_client() -> AsyncQdrantClient:
    """
    Create an asynchronous Qdrant client using central app settings.

    This can be reused by services that need async access to Qdrant.
    """
    if qdrantsettings.qdrant_api_key:
        return AsyncQdrantClient(
            url=qdrantsettings.qdrant_endpoint,
            api_key=qdrantsettings.qdrant_api_key,
        )

    return AsyncQdrantClient(url=qdrantsettings.qdrant_endpoint)
