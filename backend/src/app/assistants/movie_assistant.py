"""
LangGraph assistant for movie recommendations with semantic search.
"""

import json
import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from qdrant_client import models

from app.core.logger import log
from app.core.settings import llm_settings, qdrant_settings
from app.prompts import (
    CONTEXTUALIZE_SYSTEM_PROMPT,
    CONTEXTUALIZE_USER_PROMPT,
    GENERATE_GENERAL_PROMPT,
    GENERATE_RETRIEVE_PROMPT,
    REASK_USER_PROMPT,
    ROUTER_PROMPT,
)
from app.services.llm import llm_primary, llm_secondary
from app.services.retriever import HybridSearcher

# ---------------------------------------------------------------------------
# Retrieval quality thresholds
# Tune these values against your Qdrant collection's score distribution.
# ---------------------------------------------------------------------------
MAX_REASK_COUNT = 1  # Maximum number of re-ask attempts before forcing generation
RETRIEVAL_SCORE_THRESHOLD = (
    0.5  # minimum acceptable best-result score — tune to your collection
)


# HybridSearcher singleton
searcher = HybridSearcher(
    url=qdrant_settings.qdrant_endpoint,
    collection_name=qdrant_settings.collection,
)


# ---------------------------------------------------------------------------
# Agent state
# ---------------------------------------------------------------------------


class AgentState(TypedDict):
    """
    State threaded through every node of the graph.
    messages: The list of messages.
    contextualized_question: The contextualized question.
    decision: The decision of the router.
    media_type: The media type of the question.
    documents: The list of documents.
    generation: The generation of the question.
    needs_reask: The needs reask of the question.

    """

    messages: Annotated[list[AnyMessage], operator.add]
    contextualized_question: str
    decision: str  # "contextualize" | "generate_general"
    media_type: str  # "movie" | "series" | "any"
    documents: list[str]
    generation: str
    needs_reask: bool
    reask_count: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def format_history(messages: list[AnyMessage]) -> str:
    """Flatten and format recent messages as a readable history string.

    This will return something like this:
        User: What is the capital of France?
        Assistant: The capital of France is Paris.
        User: What is the capital of Germany?
        Assistant: The capital of Germany is Berlin.


    """
    flat: list[AnyMessage] = []
    for m in messages:
        if isinstance(m, list):
            flat.extend(m)
        else:
            flat.append(m)

    if len(flat) < 2:
        return "No previous history."

    window = flat[:-1][-llm_settings.number_of_messages_to_contextualize :]
    lines = []
    for msg in window:
        if hasattr(msg, "type"):
            role = "User" if msg.type == "human" else "Assistant"
            content = msg.content
        elif isinstance(msg, dict):
            msg_type = msg.get("type") or msg.get("role", "")
            role = "User" if msg_type in ("human", "user") else "Assistant"
            content = msg.get("content", "")
        else:
            role, content = "Unknown", str(msg)
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _extract_last_human_message(messages: list[AnyMessage]) -> str:
    """Extract the last human message from the list of messages."""
    last = messages[-1]
    if isinstance(last, HumanMessage):
        return last.content
    if isinstance(last, tuple):
        return last[1]
    if isinstance(last, dict):
        return last.get("content", "")
    return str(last)


def _retrieval_quality_ok(results: list[dict[str, Any]]) -> bool:
    """Return True when the best reranker score meets the minimum threshold."""
    if not results:
        return False
    log.info(
        "retrieve: %d docs  rerank_scores=%s",
        len(results),
        [round(r.get("score", 0), 3) for r in results[:5]],
    )
    return results[0].get("score", 0.0) >= RETRIEVAL_SCORE_THRESHOLD


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------


async def router_node(state: AgentState) -> dict:
    """
    Classify the question into intent + media_type in one LLM call.

    Runs after ``contextualize_question``: the router sees the standalone
    rewritten query (conversation context merged), not only the raw last turn.
    """
    question = state.get("contextualized_question") or _extract_last_human_message(
        state["messages"]
    )
    prompt = ChatPromptTemplate.from_template(ROUTER_PROMPT)
    chain = prompt | llm_secondary | StrOutputParser()
    raw = await chain.ainvoke({"question": question})

    decision = "GENERAL"
    media_type = "any"

    try:
        parsed = json.loads(raw.strip())
        intent = parsed.get("intent", "GENERAL").strip().upper()
        decision = "RETRIEVE" if "RETRIEVE" in intent else "GENERAL"
        media_type = parsed.get("media_type", "any").strip().lower()
        if media_type not in ("movie", "series", "any"):
            media_type = "any"
    except Exception:
        if "RETRIEVE" in raw.strip().upper():
            decision = "RETRIEVE"
        log.warning("router: could not parse JSON %r, using defaults", raw)

    log.info(
        "router: intent=%s  media_type=%s  contextualized_question=%r",
        decision,
        media_type,
        question,
    )
    return {"decision": decision, "media_type": media_type}


async def contextualize_question(state: AgentState) -> dict:
    """
    Summarize the conversation to be a single question.
    """
    messages = state["messages"]
    raw_question = _extract_last_human_message(messages)
    try:
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", CONTEXTUALIZE_SYSTEM_PROMPT),
                ("human", CONTEXTUALIZE_USER_PROMPT),
            ]
        )
        chain = prompt | llm_secondary | StrOutputParser()
        result = await chain.ainvoke(
            {"chat_history": format_history(messages), "question": raw_question}
        )
        contextualized_question = result.strip() or raw_question
        log.info("contextualize_question: %r → %r", raw_question, result)
        return {
            "contextualized_question": contextualized_question,
            "rewrote": contextualized_question != raw_question,
        }
    except Exception:
        log.exception("contextualize_question failed, falling back to raw question")
        return {"contextualized_question": raw_question, "rewrote": False}


async def retrieve(state: AgentState) -> dict:
    """
    Hybrid search with optional media-type pre-filter.

    Sets ``needs_reask=True`` when the best reranker score falls below
    RETRIEVAL_SCORE_THRESHOLD so the graph can route to ``reask_user``
    instead of attempting a generation with poor context.
    """

    media_type = state.get("media_type", "any")
    qdrant_filter = _build_media_filter(media_type)

    log.info(
        "retrieve: query=%r  media_type=%s",
        state["contextualized_question"],
        media_type,
    )
    results = await searcher.search(
        text=state["contextualized_question"], rerank=True, filter=qdrant_filter
    )

    quality_ok = _retrieval_quality_ok(results)
    best_score = results[0].get("score", 0.0) if results else 0.0
    log.info(
        "retrieve: %d docs  best_score=%.3f  quality_ok=%s",
        len(results),
        best_score,
        quality_ok,
    )

    docs_content = [doc.get("page-content", "") for doc in results]
    return {"documents": docs_content, "needs_reask": not quality_ok}


async def generate_retrieve(state: AgentState) -> dict:
    """Generate a movie-specific response using retrieved documents."""
    query = _extract_last_human_message(state["messages"])
    context_str = "\n\n---\n\n".join(state["documents"])
    chat_history = format_history(state["messages"])

    prompt = ChatPromptTemplate.from_template(GENERATE_RETRIEVE_PROMPT)
    chain = prompt | llm_primary | StrOutputParser()
    response = await chain.ainvoke(
        {
            "context": context_str,
            "question": query,
            "chat_history": chat_history,
        }
    )
    return {
        "generation": response,
        "messages": [AIMessage(content=response)],
        "reask_count": 0,
    }


async def generate_general(state: AgentState) -> dict:
    """Handle general (non-retrieval) conversation turns."""
    question = _extract_last_human_message(state["messages"])
    chat_history = format_history(state["messages"])

    prompt = ChatPromptTemplate.from_template(GENERATE_GENERAL_PROMPT)
    chain = prompt | llm_primary | StrOutputParser()
    response = await chain.ainvoke({"question": question, "chat_history": chat_history})
    return {
        "generation": response,
        "messages": [AIMessage(content=response)],
        "reask_count": 0,
    }


async def reask_user(state: AgentState) -> dict:
    """
    Ask the user for more details when retrieval quality is too low.

    Uses the secondary LLM to produce a natural clarifying question that
    prompts the user for specifics (actor, genre, year, mood, etc.).
    This node ends the current turn; the user's next message will contain
    the missing context and trigger a fresh retrieve → generate cycle.
    """
    question = _extract_last_human_message(state["messages"])

    prompt = ChatPromptTemplate.from_template(REASK_USER_PROMPT)
    chain = prompt | llm_primary | StrOutputParser()

    try:
        response = await chain.ainvoke({"question": question})
        response = response.strip()
    except Exception:
        log.exception("reask_user: LLM call failed, using generic fallback")
        response = (
            "I couldn't find enough information to answer your question well. "
            "Could you give me more details? For example: the title, a specific actor "
            "or director, the genre, or roughly when it was released?"
        )

    log.info("reask_user: question=%r  reask=%r", question, response)
    return {
        "generation": response,
        "messages": [AIMessage(content=response)],
        "reask_count": state.get("reask_count", 0) + 1,
    }


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def route_decision(state: AgentState) -> str:
    """Route to retrieve or generate_general based on the decision."""
    return "retrieve" if state["decision"] == "RETRIEVE" else "generate_general"


def route_after_retrieve(state: AgentState) -> str:
    """Route to generate_retrieve or reask_user based on the state."""
    if not state.get("needs_reask"):
        return "generate_retrieve"
    # If the user has been reasked more than 2 times, route to generate_retrieve.
    if state.get("reask_count", 0) >= MAX_REASK_COUNT:
        return "generate_retrieve"
    return "reask_user"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_media_filter(media_type: str) -> models.Filter | None:
    """Build a Qdrant must-filter for the indexed media type payload field."""
    if media_type == "any":
        return None
    return models.Filter(
        must=[
            models.FieldCondition(
                key="metadata.media_type",
                match=models.MatchValue(value=media_type),
            )
        ]
    )


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def build_app():
    """
    Build and compile the LangGraph workflow.

    Graph topology:
                    START
                    │
            [contextualize]
                    │
                [router]
                  ╱     ╲
            RETRIEVE    GENERAL
                │            ╲
        [retrieve]    [generate_general]
            ╱     ╲             │
        OK     POOR             │
        ╱           ╲           │
        [generate_retrieve] [reask_user]
                ╲        ╱        │
                    END ←─────────╯

    Contextualize runs first so the router classifies a single self-contained
    query (short follow-ups like titles after a re-ask inherit full intent).

    """
    workflow = StateGraph(AgentState)

    workflow.add_node("router", router_node)
    workflow.add_node("contextualize", contextualize_question)
    workflow.add_node("retrieve", retrieve)
    workflow.add_node("generate_retrieve", generate_retrieve)
    workflow.add_node("generate_general", generate_general)
    workflow.add_node("reask_user", reask_user)

    workflow.add_edge(START, "contextualize")
    workflow.add_edge("contextualize", "router")
    workflow.add_conditional_edges(
        "router",
        route_decision,
        {"retrieve": "retrieve", "generate_general": "generate_general"},
    )
    workflow.add_conditional_edges(
        "retrieve",
        route_after_retrieve,
        {"generate_retrieve": "generate_retrieve", "reask_user": "reask_user"},
    )

    workflow.add_edge("generate_retrieve", END)
    workflow.add_edge("generate_general", END)
    workflow.add_edge("reask_user", END)

    return workflow.compile()
