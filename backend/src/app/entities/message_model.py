from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Column, DateTime, Float, Text, Enum as SAEnum, func
from sqlmodel import SQLModel, Field, Relationship

from app.schemas.conversation_schema import RoleEnum

if TYPE_CHECKING:
    from app.entities.conversation_model import Conversation


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: Optional[int] = Field(default=None, primary_key=True)

    conversation_id: int = Field(
        foreign_key="conversations.id",
        index=True,
        nullable=False,
    )

    role: RoleEnum = Field(
        sa_column=Column(
            SAEnum(RoleEnum, name="role_enum"),
            nullable=False,
        )
    )

    content: str = Field(sa_column=Column(Text, nullable=False))
    raw_content: str = Field(sa_column=Column(Text, nullable=False))

    thinking: Optional[str] = Field(default=None)
    thinking_time: Optional[float] = Field(default=None, sa_column=Column(Float))
    summary: str | None = None

    created_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), server_default=func.now(), nullable=False
        )
    )

    # inversa
    conversation: Optional["Conversation"] = Relationship(back_populates="messages")
