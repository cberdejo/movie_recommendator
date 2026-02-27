"""
WebSocket handler for movie recommendations.
"""

import time

from fastapi import WebSocket, WebSocketDisconnect
from langchain_core.messages import AIMessage, HumanMessage
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.websockets import WebSocketState

from app.assistants.movie_assistant import build_app
from app.crud.conversation_crud import (
    create_conversation,
    add_message,
    get_conversation_with_messages,
)
from app.schemas.ws_schemas import WSRequest, WSResponse
from app.core.config.logger import get_logger

logger = get_logger("WS_MOVIES_HANDLER")


async def _send_if_open(websocket: WebSocket, text: str) -> None:
    """Send text on the WebSocket only if still open; ignore if client disconnected."""
    if websocket.client_state != WebSocketState.CONNECTED:
        return
    try:
        await websocket.send_text(text)
    except (WebSocketDisconnect, RuntimeError):
        pass


# Graph LangGraph: a single instance, all generation passes through it
app_graph = build_app()

# Model saved in history (LiteLLM; the real model is chosen by the assistant)
CONVERSATION_MODEL_LABEL = "litellm"


async def ws_handler_movies(websocket: WebSocket, db: AsyncSession):
    """WebSocket endpoint for movie recommendations use case."""
    await websocket.accept()
    current_convo_id: int | None = None

    try:
        while True:
            data = await websocket.receive_text()
            req = WSRequest.model_validate_json(data)

            if req.type == "start_conversation":
                title = (req.message or "")[:30] + (
                    "..." if len(req.message or "") > 30 else ""
                )
                convo = await create_conversation(
                    title=title,
                    model=CONVERSATION_MODEL_LABEL,
                    use_case="movies",
                    db=db,
                )
                current_convo_id = convo.id
                await add_message(
                    db=db,
                    conversation_id=convo.id,
                    role="user",
                    content=req.message or "",
                )
                await websocket.send_text(
                    WSResponse(
                        type="conversation_started", content=current_convo_id
                    ).model_dump_json()
                )

                await _generate_and_stream_langgraph(
                    websocket=websocket,
                    user_message=req.message or "",
                    convo_id=current_convo_id,
                    db=db,
                )

            elif req.type == "resume_conversation":
                current_convo_id = req.convo_id
                await websocket.send_text(
                    WSResponse(
                        type="conversation_resumed", content=current_convo_id or ""
                    ).model_dump_json()
                )

            elif req.type == "message":
                if not current_convo_id:
                    await websocket.send_text(
                        WSResponse(
                            type="error", content="No active conversation"
                        ).model_dump_json()
                    )
                    continue

                await add_message(
                    db=db,
                    conversation_id=current_convo_id,
                    role="user",
                    content=req.message or "",
                )

                await _generate_and_stream_langgraph(
                    websocket=websocket,
                    user_message=req.message or "",
                    convo_id=current_convo_id,
                    db=db,
                )

    except WebSocketDisconnect:
        return
    except Exception as e:
        await _send_if_open(
            websocket,
            WSResponse(type="error", content=f"Server error: {e}").model_dump_json(),
        )
        return


async def _generate_and_stream_langgraph(
    websocket: WebSocket,
    user_message: str,
    convo_id: int,
    db: AsyncSession,
):
    """Generate and stream the assistant's response using LangGraph and Postgres history."""
    req_id = f"movies-c{convo_id}-t{int(time.time() * 1000)}"
    start_ts = time.time()

    try:
        logger.info(
            "[%s] _generate_and_stream_langgraph: start (convo_id=%s)",
            req_id,
            convo_id,
        )

        # Tell frontend the assistant is "thinking" until first token
        await _send_if_open(
            websocket,
            WSResponse(type="thinking_start", content=None).model_dump_json(),
        )

        # 1. Retrieve the entire conversation history from the database.
        # the last message in this list will already be the current `user_message`.
        db_messages = await get_conversation_with_messages(
            conversation_id=convo_id, db=db
        )

        # 2. Format the messages so that LangChain understands them.
        langchain_messages = []
        for msg in db_messages.messages:
            if msg.role == "user":
                langchain_messages.append(HumanMessage(content=msg.content))
            elif msg.role in [
                "assistant",
                "model",
            ]:
                langchain_messages.append(AIMessage(content=msg.content))

        # If for some reason the query fails or comes empty (it shouldn't),
        # we ensure that at least the current message is sent.
        if not langchain_messages:
            langchain_messages = [HumanMessage(content=user_message)]

        inputs = {"messages": langchain_messages}

        assistant_chunks: list[str] = []
        final_response = ""
        thinking_end_sent = False

        # 4. Stream events from LangGraph
        async for event in app_graph.astream_events(inputs, config={}, version="v1"):
            kind = event["event"]

            if kind == "on_chat_model_stream":
                # Only stream tokens from generate and generate_general nodes
                node_name = event.get("metadata", {}).get("langgraph_node", "")

                if node_name in ["generate", "generate_general"]:
                    content = event["data"]["chunk"].content
                    if content:
                        if not thinking_end_sent:
                            thinking_end_sent = True
                            await _send_if_open(
                                websocket,
                                WSResponse(
                                    type="thinking_end", content=None
                                ).model_dump_json(),
                            )
                        assistant_chunks.append(content)
                        await _send_if_open(
                            websocket,
                            WSResponse(
                                type="response_chunk", content=content
                            ).model_dump_json(),
                        )

            # Capture final generation from state updates
            elif kind == "on_chain_end":
                node_name = event.get("name", "")
                if node_name in ["generate", "generate_general"]:
                    output = event.get("data", {}).get("output", {})
                    if isinstance(output, dict):
                        # Check for generation in output
                        if "generation" in output:
                            final_response = output["generation"]
                        # Also check messages for AIMessage content
                        elif "messages" in output:
                            messages = output["messages"]
                            if messages and hasattr(messages[-1], "content"):
                                final_response = messages[-1].content

        # If we didn't get final response from events, join chunks
        if not final_response:
            final_response = "".join(assistant_chunks).strip()

        if not thinking_end_sent:
            await _send_if_open(
                websocket,
                WSResponse(type="thinking_end", content=None).model_dump_json(),
            )

        if not final_response:
            msg = "No tokens received from the model."
            logger.error("[%s] %s", req_id, msg)
            await _send_if_open(
                websocket,
                WSResponse(type="error", content=msg).model_dump_json(),
            )
        else:
            # Save assistant message to database
            await add_message(
                db=db,
                conversation_id=convo_id,
                role="assistant",
                content=final_response,
            )

        await _send_if_open(
            websocket, WSResponse(type="done", content="").model_dump_json()
        )

        elapsed = time.time() - start_ts
        logger.info("[%s] Generation completed in %.2fs", req_id, elapsed)

    except Exception as e:
        logger.exception("[%s] LangGraph generation error", req_id)
        await _send_if_open(
            websocket,
            WSResponse(
                type="error", content=f"Generation error: {e}"
            ).model_dump_json(),
        )
