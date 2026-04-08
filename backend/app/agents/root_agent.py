"""
Root Agent — orchestrator, tổng hợp kết quả từ các sub-agents.

Kiến trúc multi-agent:
  Root Agent (gemini-2.5-flash — reasoning mạnh nhất)
      ├── AgentTool → DocsAgent    (gemini-2.0-flash, search documents)
      ├── AgentTool → MeetingAgent (gemini-2.0-flash, search meetings)
      ├── retrieve_memories        (direct tool — nhẹ, không cần sub-agent)
      └── store_memory             (direct tool)

Gemini hỗ trợ parallel function calls:
  Root agent có thể gọi DocsAgent + MeetingAgent + retrieve_memories cùng lúc.
  ADK execute chúng concurrently → latency = max(t_docs, t_meeting, t_mem).
"""

from functools import lru_cache

from google.adk.agents import LlmAgent
from google.adk.tools.agent_tool import AgentTool
from google.genai import types as genai_types

from app.agents.docs_agent import get_docs_agent
from app.agents.meeting_agent import get_meeting_agent
from app.agents.plugins.context_filter_plugin import (
    context_filter_after_model,
    context_filter_before_model,
)
from app.agents.tools.mem0_tools import retrieve_memories, store_memory
from app.core.llm_config import get_llm_config


@lru_cache
def get_root_agent() -> LlmAgent:
    config = get_llm_config()
    return LlmAgent(
        name="memrag_root_agent",
        model=config.llm.model,
        description="MemRAG Chatbot - AI assistant với RAG và long-term memory",
        instruction=config.prompts.system_instruction,
        tools=[
            # skip_summarization=True: trả nguyên văn kết quả sub-agent về Root
            # để Root tự tổng hợp — không để ADK summarize mất chi tiết
            AgentTool(agent=get_docs_agent(), skip_summarization=True),
            AgentTool(agent=get_meeting_agent(), skip_summarization=True),
            retrieve_memories,
            store_memory,
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
