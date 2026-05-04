from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router as api_router_v1
from app.core.logger import log
from app.core.middleware import LogRequestMiddleware
from app.core.observability import init_langfuse, shutdown_langfuse
from app.core.redis import ping_redis
from app.db.init_db import init_db

version = "v1"
description = """
A REST API for a movie recommendation system with LLM.
This API provides endpoints for managing conversations and messages.
"""
version_prefix = f"/api/{version}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    redis_ok = await ping_redis()
    log.info("startup", redis_ok=redis_ok)
    langfuse_client = init_langfuse()
    app.state.langfuse = langfuse_client
    try:
        yield
    finally:
        shutdown_langfuse(langfuse_client)


app = FastAPI(
    description=description,
    version=version,
    docs_url=f"{version_prefix}/docs",
    contact={
        "name": "Christian Berdejo",
        "url": "https://github.com/cberdejo",
        "email": "cberdejo2205@gmail.com",
    },
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LogRequestMiddleware)

app.include_router(api_router_v1, prefix=version_prefix)
