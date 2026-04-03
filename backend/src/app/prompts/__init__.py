"""Prompts for movie assistant."""

from app.prompts.contextualize import (
    CONTEXTUALIZE_SYSTEM_PROMPT,
    CONTEXTUALIZE_USER_PROMPT,
)
from app.prompts.generate_retrieve import GENERATE_RETRIEVE_PROMPT
from app.prompts.generate_general import GENERATE_GENERAL_PROMPT
from app.prompts.router import ROUTER_PROMPT
from app.prompts.generate_reask import REASK_USER_PROMPT
from app.prompts.summarize import SUMMARIZE_SYSTEM_PROMPT

__all__ = [
    "CONTEXTUALIZE_SYSTEM_PROMPT",
    "CONTEXTUALIZE_USER_PROMPT",
    "ROUTER_PROMPT",
    "GENERATE_RETRIEVE_PROMPT",
    "GENERATE_GENERAL_PROMPT",
    "REASK_USER_PROMPT",
    "SUMMARIZE_SYSTEM_PROMPT",
]
