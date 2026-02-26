from app.utils.type_parser import parse_int
from pydantic import BaseModel
from pydantic import BaseModel, field_validator, ValidationError


class WSRequest(BaseModel):
    type: str
    message: str | None = None
    model: str | None = None
    convo_id: int | None = None

    _coerce_convo_id = field_validator("convo_id", mode="before")(parse_int)


class WSResponse(BaseModel):
    type: str
    content: object | None = None
