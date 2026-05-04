from datetime import datetime, timezone

from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.entities import Conversation, Message
from app.schemas.conversation_schema import RoleEnum


async def create_conversation(
    title: str, model: str, use_case: str, db: AsyncSession
) -> Conversation:
    """
    Create a new conversation.

    Args:
        title: The title of the conversation.
        model: The model to use for the conversation.
        use_case: The use case for the conversation.
        db: The database session.

    Returns:
        The created conversation.
    Raises:
        SQLAlchemyError: If there is an error creating the conversation.
    """

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
    """
    Add a message to a conversation.

    Args:
        db: The database session.
        conversation_id: The ID of the conversation.
        role: The role of the message.
        content: The content of the message.
        raw_content: The raw content of the message.
        thinking: The thinking of the message.
        thinking_time: The thinking time of the message.

    Returns:
        The added message.
    Raises:
        SQLAlchemyError: If there is an error adding the message.
    """
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
    convo = await db.get(Conversation, conversation_id)
    if convo:
        convo.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(msg)
    return msg


async def update_message_content(
    db: AsyncSession,
    message_id: int,
    content: str,
) -> None:
    """Update only the contextualized content of a message, keeping raw_content intact."""
    msg = await db.get(Message, message_id)
    if msg:
        msg.content = content
        await db.commit()


async def get_conversation(
    conversation_id: int, db: AsyncSession
) -> Conversation | None:
    """
    Get a conversation with messages.

    Args:
        conversation_id: The ID of the conversation.
        db: The database session.
        number_of_messages: The number of messages to get.

    Returns:
        The conversation with messages.
    Raises:
        SQLAlchemyError: If there is an error getting the conversation with messages.
    """
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    result = await db.exec(stmt)
    return result.one_or_none()


async def get_conversation_with_messages(
    conversation_id: int, db: AsyncSession, number_of_messages: int = 10
) -> Conversation | None:
    """
    Get a conversation with messages.

    Args:
        conversation_id: The ID of the conversation.
        db: The database session.
        number_of_messages: The number of messages to get.

    Returns:
        The conversation with messages.
    Raises:
        SQLAlchemyError: If there is an error getting the conversation with messages.
    """
    stmt = (
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(selectinload(Conversation.messages))
    )
    result = await db.exec(stmt)
    convo = result.one_or_none()

    if convo and convo.messages:
        # Ensure chronological order: oldest first.
        # Use id as primary sort key (autoincremental = insertion order),
        # with created_at as tie-breaker. This avoids issues where timestamps
        # might be out of order due to clock skew or transaction timing.
        convo.messages = sorted(
            convo.messages,
            key=lambda m: (m.id or 0, m.created_at or datetime.min)
        )

    return convo


async def get_conversation_with_messages_limited(
    conversation_id: int, db: AsyncSession, number_of_messages: int = 10
) -> list[Message] | None:
    """
    Get a conversation with only the latest number_of_messages loaded.
    """
    convo_stmt = select(Conversation.id).where(Conversation.id == conversation_id)
    convo_result = await db.exec(convo_stmt)
    convo_id = convo_result.one_or_none()
    if convo_id is None:
        return None

    msg_stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id.desc())
        .limit(number_of_messages)
    )
    msg_result = await db.exec(msg_stmt)
    return list(reversed(msg_result.all()))


async def list_conversations(
    db: AsyncSession, use_case: str | None = None
) -> list[Conversation]:
    """
    List conversations.

    Args:
        db: The database session.
        use_case: The use case for the conversations.

    Returns:
        The list of conversations.
    Raises:
        SQLAlchemyError: If there is an error listing the conversations.
    """
    stmt = select(Conversation)
    if use_case:
        stmt = stmt.where(Conversation.use_case == use_case)
    stmt = stmt.order_by(Conversation.updated_at.desc())
    result = await db.exec(stmt)
    return result.all()


async def update_conversation_title(
    conversation_id: int, title: str, db: AsyncSession
) -> Conversation | None:
    convo = await db.get(Conversation, conversation_id)
    if convo:
        convo.title = title.strip() or convo.title
        await db.commit()
        await db.refresh(convo)
        return convo
    return None


async def delete_conversation(conversation_id: int, db: AsyncSession) -> bool:
    convo = await db.get(Conversation, conversation_id)
    if convo:
        await db.delete(convo)
        await db.commit()
        return True
    return False
