from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.entities import Conversation, Message
from app.schemas.conversation_schema import RoleEnum


async def create_conversation(
    title: str, model: str, use_case: str, db: AsyncSession
) -> Conversation:
    convo = Conversation(title=title, model=model, use_case=use_case)
    db.add(convo)
    await db.commit()
    await db.refresh(convo)
    return convo


async def add_message(
    db: AsyncSession,
    conversation_id: int,
    role: RoleEnum | str,
    content: str,
    raw_content: str | None = None,
    thinking: str | None = None,
    thinking_time: float | None = None,
) -> Message:
    raw = raw_content or content

    msg = Message(
        conversation_id=conversation_id,
        role=RoleEnum(role),
        content=content,
        raw_content=raw,
        thinking=thinking,
        thinking_time=thinking_time,
    )
    db.add(msg)
    # touch updated_at
    await db.exec(select(Conversation).where(Conversation.id == conversation_id))
    await db.commit()
    await db.refresh(msg)
    return msg


async def get_conversation(
    conversation_id: int, db: AsyncSession
) -> Conversation | None:
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    result = await db.exec(stmt)
    return result.one_or_none()


async def get_conversation_with_messages(
    conversation_id: int, db: AsyncSession
) -> Conversation | None:
    stmt = (
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(selectinload(Conversation.messages))
    )
    result = await db.exec(stmt)
    return result.one_or_none()


async def list_conversations(
    db: AsyncSession, use_case: str | None = None
) -> list[Conversation]:
    stmt = select(Conversation)
    if use_case:
        stmt = stmt.where(Conversation.use_case == use_case)
    stmt = stmt.order_by(Conversation.updated_at.desc())
    result = await db.exec(stmt)
    return result.all()


async def delete_conversation(conversation_id: int, db: AsyncSession) -> bool:
    convo = await db.get(Conversation, conversation_id)
    if convo:
        await db.delete(convo)
        await db.commit()
        return True
    return False
