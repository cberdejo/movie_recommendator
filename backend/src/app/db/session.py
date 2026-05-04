from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.settings import apisettings

async_engine = create_async_engine(apisettings.database_uri, echo=True, future=True)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session():
    async with AsyncSessionLocal() as session:
        yield session
