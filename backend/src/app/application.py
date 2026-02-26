from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.core.config.logger import get_logger
from app.api.v1.api import api_router as api_router_v1
from app.db.init_db import init_db

logger = get_logger("APP")

version = "v1"
description = """
A REST API for a  movie recommendation system with LLM.
This API provides endpoints for managing conversations and messages.
"""
version_prefix = f"/api/{version}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


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

app.include_router(api_router_v1, prefix=version_prefix)
