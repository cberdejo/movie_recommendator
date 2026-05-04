from typing import Literal

from pydantic import BaseModel, model_validator, field_validator

from app.utils.type_parser import parse_int


WSRequestType = Literal[
    "start_conversation",
    "resume_conversation",
    "resume_stream",
    "message",
    "interrupt",
]


class WSRequest(BaseModel):
    type: WSRequestType
    message: str | None = None
    model: str | None = None
    convo_id: int | None = None
    message_id: str | None = None
    from_id: str | None = None

    _coerce_convo_id = field_validator("convo_id", mode="before")(parse_int)

    @model_validator(mode="after")
    def validate_payload_by_type(self) -> "WSRequest":
        if self.type in {"start_conversation", "message"} and self.message is None:
            raise ValueError("message is required for this request type")
        if self.type == "resume_conversation" and self.convo_id is None:
            raise ValueError("convo_id is required for resume_conversation")
        if self.type == "resume_stream" and self.message_id is None:
            raise ValueError("message_id is required for resume_stream")
        return self


class WSResponse(BaseModel):
    type: str
    content: object | None = None
    error_code: str | None = None
    retryable: bool | None = None
    stream_id: str | None = None
    message_id: str | None = None
    conversation_id: int | None = None
