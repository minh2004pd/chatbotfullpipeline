"""
Root Agent — single agent với tất cả tools trực tiếp.

Agent dùng gemini-2.5-flash để reasoning + tự gọi tools:
  - search_documents          : tìm trong tài liệu PDF/file
  - search_meeting_transcripts: tìm trong transcript cuộc họp
  - list_user_documents       : liệt kê file đã upload
  - list_meetings             : liệt kê danh sách cuộc họp đã ghi âm
  - read_wiki_index           : xem bản đồ tri thức wiki (index.md)
  - read_wiki_page            : đọc nội dung trang wiki cụ thể
  - list_wiki_pages           : liệt kê pages trong category wiki
  - retrieve_memories         : lấy long-term memory
  - store_memory              : lưu long-term memory
"""

from functools import lru_cache

from google.adk.agents import LlmAgent
from google.genai import types as genai_types

from app.agents.plugins.context_filter_plugin import (
    context_filter_after_model,
    context_filter_before_model,
)
from app.agents.tools.files_retrieval_tool import list_user_documents
from app.agents.tools.meeting_search_tool import list_meetings, search_meeting_transcripts
from app.agents.tools.mem0_tools import retrieve_memories, store_memory
from app.agents.tools.qdrant_search_tool import search_documents
from app.agents.tools.wiki_tools import list_wiki_pages, read_wiki_index, read_wiki_page
from app.core.llm_config import get_llm_config


@lru_cache
def get_root_agent() -> LlmAgent:
    config = get_llm_config()
    return LlmAgent(
        name="memrag_root_agent",
        model=config.llm.model,
        description="MemRAG - AI assistant with RAG, knowledge base, and long-term memory",
        instruction=config.prompts.system_instruction,
        tools=[
            search_documents,
            search_meeting_transcripts,
            list_user_documents,
            list_meetings,
            read_wiki_index,
            read_wiki_page,
            list_wiki_pages,
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
