"""
LLM singletons
This is to avoid creating a new LLM instance for each message.
"""

from langchain_openai import ChatOpenAI

from app.core.settings import llm_settings

llm_primary = ChatOpenAI(
    base_url=llm_settings.openai_base_url,
    model=llm_settings.primary_model,
    api_key="sk-no-key-needed",
    temperature=llm_settings.primary_temperature,
    max_retries=llm_settings.max_retries,
)
llm_secondary = ChatOpenAI(
    base_url=llm_settings.openai_base_url,
    model=llm_settings.secondary_model,
    api_key="sk-no-key-needed",
    temperature=llm_settings.secondary_temperature,
    max_retries=llm_settings.max_retries,
)
