"""
WebSocket chat session state and shared constants.
"""

import asyncio
from dataclasses import dataclass

from sqlmodel.ext.asyncio.session import AsyncSession

from app.assistants.movie_assistant import build_app
from app.core.logger import log
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
    """Mutable state for a WebSocket connection.

    With the Redis stream-bus refactor, generation lives in its own task and
    survives WebSocket disconnects. A separate relay task forwards stream
    events to the active socket; only the relay is bound to the connection.

    - convo_id: active conversation.
    - active_message_id: id of the in-flight generation (Redis namespace).
    - relay_task: forwards Redis events to the WebSocket; tied to the socket.
    - summarize_task: background summarization task for the previous turn.
    - current_msg_id: DB id of the previous turn's user message (to be updated).
    - current_msg_id_assistant: DB id of the previous turn's assistant message.
    - last_stream_id: last Redis entry id forwarded to the client (for replay).
    - client_disconnected: disables WS sends after disconnect.
    - consecutive_reasks: number of consecutive reask_user nodes.
    """

    convo_id: int | None = None
    active_message_id: str | None = None
    relay_task: asyncio.Task | None = None
    summarize_task: asyncio.Task | None = None
    current_msg_id: int | None = None
    current_msg_id_assistant: int | None = None
    last_stream_id: str = "0-0"
    client_disconnected: bool = False
    consecutive_reasks: int = 0

    # ------------------------------------------------------------------
    # Relay lifecycle
    # ------------------------------------------------------------------

    async def cancel_relay(self) -> None:
        """Cancel the running relay task (does NOT cancel generation)."""
        task = self.relay_task
        self.relay_task = None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    # ------------------------------------------------------------------
    # Summarization handoff (unchanged from previous design)
    # ------------------------------------------------------------------

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
                log.exception("summarization: failed to compress messages")
                # fallback: content stays as raw, which is correct
        else:
            self.summarize_task.cancel()

        self.summarize_task = None
        self.current_msg_id = None
        self.current_msg_id_assistant = None

    # ------------------------------------------------------------------
    # Stream-id bookkeeping
    # ------------------------------------------------------------------

    def reset_stream(self, message_id: str | None) -> None:
        self.active_message_id = message_id
        self.last_stream_id = "0-0"
