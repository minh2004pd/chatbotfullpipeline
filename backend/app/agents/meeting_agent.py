"""
MeetingAgent — sub-agent chuyên tra cứu transcript cuộc họp.

Chạy với retrieval_model (nhẹ hơn root agent) vì chỉ cần:
  1. Nhận query từ root agent
  2. Gọi search_meeting_transcripts (có thể thử lại với query khác nếu rỗng)
  3. Trả raw kết quả về root agent để tổng hợp
"""

from functools import lru_cache

from google.adk.agents import LlmAgent
from google.genai import types as genai_types

from app.agents.tools.meeting_search_tool import search_meeting_transcripts
from app.core.llm_config import get_llm_config


@lru_cache
def get_meeting_agent() -> LlmAgent:
    config = get_llm_config()
    return LlmAgent(
        name="meeting_retrieval_agent",
        model=config.llm.retrieval_model,
        description="Tra cứu transcript các cuộc họp đã được ghi âm và index vào hệ thống.",
        instruction=config.prompts.meeting_agent_instruction,
        tools=[search_meeting_transcripts],
        generate_content_config=genai_types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=4096,
        ),
    )
