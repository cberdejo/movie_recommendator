"""
Async Redis client. A single shared connection pool is created at import time;
callers obtain a Redis instance via get_redis().
"""

from typing import Annotated, TypeAlias

import redis.asyncio as aioredis
from fastapi import Depends

from app.core.settings import redissettings

_pool = aioredis.ConnectionPool.from_url(redissettings.redis_url, decode_responses=True)


def get_redis() -> aioredis.Redis:
    """Return a Redis client backed by the shared connection pool."""
    return aioredis.Redis(connection_pool=_pool)


RedisClient: TypeAlias = Annotated[aioredis.Redis, Depends(get_redis)]


async def ping_redis() -> bool:
    """Best-effort connectivity check used by /health and startup."""
    try:
        client = get_redis()
        return bool(await client.ping())
    except Exception:
        return False
