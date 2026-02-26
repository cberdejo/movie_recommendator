from pydantic import BaseModel, ConfigDict, Field, field_serializer
from datetime import datetime
from enum import Enum


class CreateConversationRequest(BaseModel):
    model: str
    message: str


class CreateConversationResponse(BaseModel):
    ID: int = None
    Title: str
    model: str


class ErrorResponse(BaseModel):
    message: str


class MessageRead(BaseModel):
    id: int = Field(serialization_alias="ID")
    conversation_id: int = Field(serialization_alias="ConversationID")
    role: str = Field(serialization_alias="Role")
    content: str = Field(serialization_alias="Content")
    raw_content: str = Field(serialization_alias="RawContent")
    thinking: str | None = Field(serialization_alias="Thinking")
    thinking_time: float | None = Field(serialization_alias="ThinkingTime")
    created_at: datetime = Field(serialization_alias="CreatedAt")

    @field_serializer("created_at")
    def _dt_to_str(self, v: datetime) -> str:
        return v.isoformat()


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int = Field(serialization_alias="ID")
    title: str = Field(serialization_alias="Title")
    use_case: str = Field(serialization_alias="UseCase")
    created_at: datetime = Field(serialization_alias="CreateAt")
    updated_at: datetime = Field(serialization_alias="UpdatedAt")

    # Serializes dates as ISO 8601 strings; adjust here if you need a different format
    @field_serializer("created_at", "updated_at")
    def _dt_to_str(self, v: datetime) -> str:
        return v.isoformat()


class ConversationExtendedRead(ConversationRead):
    messages: list[MessageRead] | None = Field(serialization_alias="Messages")

    # Serializes dates as ISO 8601 strings; adjust here if you need a different format
    @field_serializer("created_at", "updated_at")
    def _dt_to_str(self, v: datetime) -> str:
        return v.isoformat()


class RoleEnum(str, Enum):
    user = "user"
    assistant = "assistant"
