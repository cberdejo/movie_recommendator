"""
LLM singletons
This is to avoid creating a new LLM instance for each message.
"""

from langchain_openai import ChatOpenAI

from app.core.settings import llmsettings

llm_primary = ChatOpenAI(
    base_url=llmsettings.openai_base_url,
    model="primary-llm",
    api_key="sk-no-key-needed",
    temperature=0.7,
    max_retries=2,
)
llm_secondary = ChatOpenAI(
    base_url=llmsettings.openai_base_url,
    model="secondary-llm",
    api_key="sk-no-key-needed",
    temperature=0.0,
    max_retries=2,
)
