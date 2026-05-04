"""
Text utility functions for common string operations.
"""


def truncate_with_ellipsis(
    text: str, max_length: int = 30, ellipsis: str = "..."
) -> str:
    """
    Truncate a string to max_length, adding ellipsis if truncated.

    Args:
        text: The string to truncate.
        max_length: Maximum length before truncation (default: 30).
        ellipsis: String to append when truncated (default: "...").

    Returns:
        Truncated string with ellipsis if needed, or original string if within limit.

    Examples:
        >>> truncate_with_ellipsis("Hello World", 20)
        'Hello World'
        >>> truncate_with_ellipsis("Hello World This Is Long", 10)
        'Hello Wor...'
    """
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length] + ellipsis


def build_conversation_title(message: str, default: str = "New Conversation") -> str:
    """
    Build a conversation title from the initial message.

    Creates a short title from the first 30 characters of the message,
    with fallback to a default if the message is empty.

    Args:
        message: The initial user message.
        default: Default title if message is empty (default: "New Conversation").

    Returns:
        A title suitable for the conversation.
    """
    base = (message or "").strip()
    if not base:
        return default
    return truncate_with_ellipsis(base, max_length=30)
