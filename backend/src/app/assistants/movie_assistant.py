"""
LangGraph assistant for movie recommendations with semantic search.
"""

import logging
import operator
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langchain_openai import ChatOpenAI

from app.core.config.settings import qdrantsettings, llmsettings
from app.prompts import (
    CONTEXTUALIZE_SYSTEM_PROMPT,
    CONTEXTUALIZE_USER_PROMPT,
    GENERATE_GENERAL_PROMPT,
    GENERATE_PROMPT,
    ROUTER_PROMPT,
)
from app.services.retriever import HybridSearcher


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    """State for the movie recommendation agent."""

    messages: Annotated[list[AnyMessage], operator.add]
    question: str
    reformulated_question: str
    documents: list[str]
    generation: str
    decision: str


# Primary LLM configuration (most intelligent model - for main generation)
llm_primary = ChatOpenAI(
    base_url=llmsettings.openai_base_url,
    model="primary-llm",
    api_key="sk-no-key-needed",
    temperature=0.7,
    max_retries=2,
)
# Secondary LLM configuration (for contextualization)
llm_secondary = ChatOpenAI(
    base_url=llmsettings.openai_base_url,
    model="secondary-llm",
    api_key="sk-no-key-needed",
    temperature=0.0,
    max_retries=2,
)


# HybridSearcher instance
searcher = HybridSearcher(
    url=qdrantsettings.qdrant_endpoint, collection_name=qdrantsettings.qdrant_collection
)


def format_history(messages: list[AnyMessage]) -> str:
    """
    Convert the list of messages into formatted text.

    Args:
        messages: List of message objects

    Returns:
        Formatted string with conversation history
    """
    flat_messages = []
    for m in messages:
        if isinstance(m, list):
            flat_messages.extend(m)
        else:
            flat_messages.append(m)

    if len(flat_messages) < 2:
        return "No previous history."

    history_messages = flat_messages[:-1]

    formatted = []
    for msg in history_messages:
        role = "Assistant"
        content = ""

        if hasattr(msg, "type"):
            role = "User" if msg.type == "human" else "Assistant"
            content = msg.content
        elif isinstance(msg, dict):
            msg_type = msg.get("type") or msg.get("role")
            role = "User" if msg_type in ["human", "user"] else "Assistant"
            content = msg.get("content", "")
        formatted.append(f"{role}: {content}")

    # Join last 6 messages for context
    return "\n".join(formatted[-llmsettings.number_of_messages_to_contextualize:])


async def contextualize_question(state: AgentState):
    """
    Rewrite the user's question based on conversation history to make it self-contained.
    Solves issues like 'make it shorter' or 'explain that'.

    Args:
        state: Current agent state

    Returns:
        Updated state with reformulated question
    """
    # Extract the last user message
    last_message = state["messages"][-1]
    if isinstance(last_message, tuple):
        raw_question = last_message[1]
    elif isinstance(last_message, HumanMessage):
        raw_question = last_message.content
    elif isinstance(last_message, dict):
        raw_question = last_message.get("content", "")
    else:
        raw_question = str(last_message)

    history_str = format_history(state["messages"])

    if "No previous history" in history_str:
        # If no history, the question is as-is
        return {"reformulated_question": raw_question, "question": raw_question}

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", CONTEXTUALIZE_SYSTEM_PROMPT),
            ("human", CONTEXTUALIZE_USER_PROMPT),
        ]
    )

    chain = prompt | llm_secondary | StrOutputParser()
    reformulated = await chain.ainvoke(
        {"chat_history": history_str, "question": raw_question}
    )

    logger.info(f"Original Question: '{raw_question}' | Reformulated: '{reformulated}'")

    return {"reformulated_question": reformulated, "question": raw_question}


def router(state: AgentState):
    """
    Classify the question using the REFORMULATED question.

    Args:
        state: Current agent state

    Returns:
        Updated state with decision
    """
    question = state["reformulated_question"]

    prompt = ChatPromptTemplate.from_template(ROUTER_PROMPT)

    chain = prompt | llm_secondary | StrOutputParser()
    decision = chain.invoke({"question": question})

    decision = decision.strip().upper().replace(".", "")
    if "RETRIEVE" not in decision:
        decision = "GENERAL"

    logger.info(f"Intent detected: {decision} (Input: '{question}')")

    return {"decision": decision}


async def retrieve(state: AgentState):
    """
    Retrieve documents using the REFORMULATED question.

    Args:
        state: Current agent state

    Returns:
        Updated state with retrieved documents
    """
    query = state["reformulated_question"]

    results = await searcher.search(text=query, rerank=True)

    logger.info(f"Searching documents for: '{query}'")
    logger.info(f"Documents retrieved: {len(results)}")

    if results:
        snippet_1 = results[0].get("page-content", "")[:100]
        snippet_2 = (
            results[1].get("page-content", "")[:100] if len(results) > 1 else "N/A"
        )
        logger.info(f"Top 1 Snippet: {snippet_1}...")
        logger.debug(f"Top 2 Snippet: {snippet_2}...")
    else:
        logger.warning("WARNING! No relevant documents found.")

    docs_content = [doc.get("page-content", "") for doc in results]

    return {"documents": docs_content}


async def generate(state: AgentState):
    """
    Generate technical response about movies using the reformulated question.

    Args:
        state: Current agent state

    Returns:
        Updated state with generation and messages
    """
    question = state["reformulated_question"]
    documents = state["documents"]
    chat_history = format_history(state["messages"])

    context_str = "\n\n---\n\n".join(documents)

    prompt = ChatPromptTemplate.from_template(GENERATE_PROMPT)

    chain = prompt | llm_primary | StrOutputParser()
    response = await chain.ainvoke(
        {"context": context_str, "question": question, "chat_history": chat_history}
    )

    return {"generation": response, "messages": [AIMessage(content=response)]}


async def generate_general(state: AgentState):
    """
    Handle general chat using the reformulated question.

    Args:
        state: Current agent state

    Returns:
        Updated state with generation and messages
    """
    question = state["reformulated_question"]
    chat_history = format_history(state["messages"])

    prompt = ChatPromptTemplate.from_template(GENERATE_GENERAL_PROMPT)
    chain = prompt | llm_primary | StrOutputParser()
    response = await chain.ainvoke({"question": question, "chat_history": chat_history})

    return {"generation": response, "messages": [AIMessage(content=response)]}


def route_decision(state: AgentState):
    """
    Route based on the decision.

    Args:
        state: Current agent state

    Returns:
        Next node name
    """
    if state["decision"] == "RETRIEVE":
        return "retrieve"
    else:
        return "generate_general"


def build_app():
    """
    Build and compile the LangGraph application.

    Returns:
        Compiled LangGraph application
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("contextualize", contextualize_question)
    workflow.add_node("router", router)
    workflow.add_node("retrieve", retrieve)
    workflow.add_node("generate", generate)
    workflow.add_node("generate_general", generate_general)

    workflow.add_edge(START, "contextualize")
    workflow.add_edge("contextualize", "router")

    workflow.add_conditional_edges(
        "router",
        route_decision,
        {
            "retrieve": "retrieve",
            "generate_general": "generate_general",
        },
    )

    workflow.add_edge("retrieve", "generate")
    workflow.add_edge("generate", END)
    workflow.add_edge("generate_general", END)

    return workflow.compile()
