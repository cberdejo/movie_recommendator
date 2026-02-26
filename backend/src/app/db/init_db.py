import asyncio

from app.db.session import async_engine
from sqlmodel import SQLModel

from app.entities import Conversation, Message


async def init_db() -> None:
    """
    Initializes the database by creating all tables defined in the SQLModel metadata.
    This asynchronous function establishes a connection to the database using the async engine,
    and runs the table creation statements. It should be called at application startup to ensure
    that the database schema is up to date.
    Returns:
        None
    """

    async with async_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
