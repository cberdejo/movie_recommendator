"""Prompts for movie assistant."""

from app.prompts.contextualize import (
    CONTEXTUALIZE_SYSTEM_PROMPT,
    CONTEXTUALIZE_USER_PROMPT,
)
from app.prompts.generate import GENERATE_PROMPT
from app.prompts.generate_general import GENERATE_GENERAL_PROMPT
from app.prompts.router import ROUTER_PROMPT

__all__ = [
    "CONTEXTUALIZE_SYSTEM_PROMPT",
    "CONTEXTUALIZE_USER_PROMPT",
    "ROUTER_PROMPT",
    "GENERATE_PROMPT",
    "GENERATE_GENERAL_PROMPT",
]
