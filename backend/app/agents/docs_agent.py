"""
DocsAgent — sub-agent chuyên tra cứu tài liệu PDF/file.

Chạy với retrieval_model (nhẹ hơn root agent) vì chỉ cần:
  1. Nhận query từ root agent
  2. Gọi search_documents / list_user_documents
  3. Trả raw kết quả về root agent để tổng hợp
"""

from functools import lru_cache

from google.adk.agents import LlmAgent
from google.genai import types as genai_types

from app.agents.tools.files_retrieval_tool import list_user_documents
from app.agents.tools.qdrant_search_tool import search_documents
from app.core.llm_config import get_llm_config


@lru_cache
def get_docs_agent() -> LlmAgent:
    config = get_llm_config()
    return LlmAgent(
        name="docs_retrieval_agent",
        model=config.llm.retrieval_model,
        description="Tra cứu nội dung tài liệu PDF và file đã được upload vào hệ thống.",
        instruction=config.prompts.docs_agent_instruction,
        tools=[search_documents, list_user_documents],
        generate_content_config=genai_types.GenerateContentConfig(
            temperature=0.1,  # retrieval cần deterministic, không cần creative
            max_output_tokens=4096,
        ),
    )
