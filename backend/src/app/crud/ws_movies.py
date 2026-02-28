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
import json
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

GRAPH_NODES = {"contextualize", "router", "retrieve", "generate", "generate_general"}


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
        logger.info("[%s] _generate_and_stream_langgraph: start (convo_id=%s)", req_id, convo_id)

        await _send_if_open(websocket, '{"type": "thinking_start", "content": null}')

        db_messages = await get_conversation_with_messages(conversation_id=convo_id, db=db)

        langchain_messages = []
        for msg in db_messages.messages:
            if msg.role == "user":
                langchain_messages.append(HumanMessage(content=msg.content))
            elif msg.role in ["assistant", "model"]:
                langchain_messages.append(AIMessage(content=msg.content))

        if not langchain_messages:
            langchain_messages = [HumanMessage(content=user_message)]

        inputs = {"messages": langchain_messages}
        assistant_chunks: list[str] = []
        thinking_end_sent = False
        active_node: str | None = None

        await _send_if_open(
            websocket,
            json.dumps({"type": "graph_start", "content": None}),
        )

        async for event in app_graph.astream_events(inputs, config={}, version="v1"):
            kind = event["event"]
            meta = event.get("metadata", {})
            lg_node = meta.get("langgraph_node", "")

            if lg_node in GRAPH_NODES and lg_node != active_node:
                if active_node:
                    await _send_if_open(
                        websocket,
                        json.dumps({"type": "node_end", "content": active_node}),
                    )
                active_node = lg_node
                await _send_if_open(
                    websocket,
                    json.dumps({"type": "node_start", "content": active_node}),
                )

            if kind == "on_chain_end" and lg_node in GRAPH_NODES:
                output = event.get("data", {}).get("output", {})
                if isinstance(output, dict):
                    node_data = {}
                    if "reformulated_question" in output:
                        node_data["reformulated_question"] = output["reformulated_question"]
                    if "decision" in output:
                        node_data["decision"] = output["decision"]
                    if "documents" in output:
                        node_data["documents_count"] = len(output["documents"])
                    if node_data:
                        await _send_if_open(
                            websocket,
                            json.dumps({
                                "type": "node_output",
                                "content": json.dumps({"node": lg_node, **node_data}),
                            }),
                        )

            if kind == "on_chat_model_stream":
                node_name = meta.get("langgraph_node", "")

                if node_name in ["generate", "generate_general"]:
                    content = event["data"]["chunk"].content
                    if content:
                        if not thinking_end_sent:
                            thinking_end_sent = True
                            await _send_if_open(websocket, '{"type": "thinking_end", "content": null}')

                        assistant_chunks.append(content)
                        chunk_msg = json.dumps({"type": "response_chunk", "content": content})
                        await _send_if_open(websocket, chunk_msg)

        if active_node:
            await _send_if_open(
                websocket,
                json.dumps({"type": "node_end", "content": active_node}),
            )

        final_response = "".join(assistant_chunks).strip()

        if not thinking_end_sent:
            await _send_if_open(websocket, '{"type": "thinking_end", "content": null}')

        if not final_response:
            msg = "No tokens received from the model."
            logger.error("[%s] %s", req_id, msg)
            await _send_if_open(websocket, json.dumps({"type": "error", "content": msg}))
        else:
            await add_message(
                db=db,
                conversation_id=convo_id,
                role="assistant",
                content=final_response,
            )

        await _send_if_open(
            websocket,
            json.dumps({"type": "graph_end", "content": None}),
        )
        await _send_if_open(websocket, '{"type": "done", "content": ""}')

        elapsed = time.time() - start_ts
        logger.info("[%s] Generation completed in %.2fs", req_id, elapsed)

    except Exception as e:
        logger.exception("[%s] LangGraph generation error", req_id)
        if active_node:
            await _send_if_open(
                websocket,
                json.dumps({"type": "node_end", "content": active_node}),
            )
        await _send_if_open(
            websocket,
            json.dumps({"type": "graph_end", "content": None}),
        )
        error_payload = json.dumps({"type": "error", "content": f"Generation error: {e}"})
        await _send_if_open(websocket, error_payload)