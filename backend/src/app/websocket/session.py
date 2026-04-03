"""
WebSocket chat session state and shared constants.
"""

import asyncio
from dataclasses import dataclass, field

from sqlmodel.ext.asyncio.session import AsyncSession

from app.assistants.movie_assistant import build_app
from app.crud.conversation_crud import update_message_content

INTERRUPTED_SUFFIX = "\n\n[message interrupted by the user]"

GRAPH_NODES = frozenset(
    {
        "router",
        "retrieve",
        "contextualize",
        "generate_retrieve",
        "generate_general",
        "reask_user",
    }
)

CONVERSATION_MODEL_LABEL = "movie agent v1"

app_graph = build_app()


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


@dataclass
class ChatSession:
    """All mutable state for a WebSocket connection.

    - convo_id: active conversation.
    - generation_task: running asyncio generation task.
    - summarize_task: background summarization task for the previous turn.
    - current_msg_id: DB id of the previous turn's user message (to be updated).
    - current_msg_id_assistant: DB id of the previous turn's assistant message (to be updated).
    - interrupt_event: shared interrupt signal with the generation task.
    - client_disconnected: disables WS sends after disconnect (DB writes still happen).
    - consecutive_reasks: number of consecutive reask_user nodes.
    """

    convo_id: int | None = None
    generation_task: asyncio.Task | None = None
    summarize_task: asyncio.Task | None = None
    current_msg_id: int | None = None
    current_msg_id_assistant: int | None = None
    interrupt_event: asyncio.Event = field(default_factory=asyncio.Event)
    client_disconnected: bool = False
    consecutive_reasks: int = 0

    async def cancel_generation(self) -> None:
        """Cancel the running generation task if any."""
        if self.generation_task and not self.generation_task.done():
            self.interrupt_event.set()
            self.generation_task.cancel()
            try:
                await self.generation_task
            except (asyncio.CancelledError, Exception):
                pass
        self.generation_task = None

    async def collect_summarization(self, db: AsyncSession) -> None:
        """
        Await the background summarization result and flush it to the DB.
        Called at the start of each new turn so the previous turn's messages
        are updated before new history is loaded.
        """
        if self.summarize_task is None:
            return
        if self.summarize_task.done():
            try:
                user_summary, assistant_summary = self.summarize_task.result()
                if self.current_msg_id:
                    await update_message_content(db, self.current_msg_id, user_summary)
                if self.current_msg_id_assistant:
                    await update_message_content(
                        db, self.current_msg_id_assistant, assistant_summary
                    )
            except Exception:
                pass  # fallback: content stays as raw, which is correct
        else:
            self.summarize_task.cancel()

        self.summarize_task = None
        self.current_msg_id = None
        self.current_msg_id_assistant = None

    def reset_interrupt(self) -> None:
        self.interrupt_event.clear()
