"""
Root Agent - Google ADK Agent với đầy đủ tools và ContextFilterPlugin.
"""

from functools import lru_cache

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

from app.core.llm_config import get_llm_config
from app.agents.tools.qdrant_search_tool import search_documents
from app.agents.tools.mem0_tools import retrieve_memories, store_memory
from app.agents.tools.files_retrieval_tool import list_user_documents
from app.agents.plugins.context_filter_plugin import (
    context_filter_before_model,
    context_filter_after_model,
)


@lru_cache
def get_session_service() -> InMemorySessionService:
    return InMemorySessionService()


@lru_cache
def get_root_agent() -> LlmAgent:
    config = get_llm_config()
    return LlmAgent(
        name="memrag_root_agent",
        model=config.llm.model,
        description="MemRAG Chatbot - AI assistant with RAG and long-term memory",
        instruction=config.prompts.system_instruction,
        tools=[
            search_documents,
            retrieve_memories,
            store_memory,
            list_user_documents,
        ],
        generate_content_config=genai_types.GenerateContentConfig(
            temperature=config.llm.temperature,
            top_p=config.llm.top_p,
            top_k=config.llm.top_k,
            max_output_tokens=config.llm.max_output_tokens,
        ),
        before_model_callback=context_filter_before_model,
        after_model_callback=context_filter_after_model,
    )


@lru_cache
def get_runner() -> Runner:
    return Runner(
        agent=get_root_agent(),
        app_name="memrag",
        session_service=get_session_service(),
    )
