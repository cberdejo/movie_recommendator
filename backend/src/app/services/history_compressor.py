"""
Compresses a user/assistant message pair when either exceeds a token threshold.
"""

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.logger import log
from app.core.settings import llm_settings
from app.prompts import SUMMARIZE_SYSTEM_PROMPT
from app.services.llm import llm_secondary


def _count_tokens(text: str) -> int:
    """Count tokens for a plain string using the secondary LLM tokenizer."""
    return llm_secondary.get_num_tokens(text)


async def _summarize(text: str) -> str:
    """Summarize a single message. Returns original on error."""
    try:
        prompt = ChatPromptTemplate.from_template(SUMMARIZE_SYSTEM_PROMPT)
        chain = prompt | llm_secondary | StrOutputParser()
        result = await chain.ainvoke({"message": text})
        log.info(
            "summarized: %d → %d tokens",
            _count_tokens(text),
            _count_tokens(result),
        )
        return result.strip() or text
    except Exception:
        log.exception("summarize failed, keeping original")
        return text


async def compress_pair(
    user_message: str,
    assistant_message: str,
    token_threshold: int | None = None,
) -> tuple[str, str]:
    """
    Summarize user and/or assistant message if either exceeds the token threshold.

    Args:
        user_message: Raw user message string.
        assistant_message: Full assistant response string.
        token_threshold: Max tokens before summarizing. Defaults to settings value.

    Returns:
        Tuple of (user_message, assistant_message), each possibly summarized.
    """
    threshold = token_threshold or llm_settings.message_token_threshold

    compressed_user = (
        await _summarize(user_message)
        if _count_tokens(user_message) > threshold
        else user_message
    )
    compressed_assistant = (
        await _summarize(assistant_message)
        if _count_tokens(assistant_message) > threshold
        else assistant_message
    )

    return compressed_user, compressed_assistant
