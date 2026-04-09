"""
LLM Config loader — đọc và cache config từ file YAML.

Hỗ trợ override path qua env var LLM_CONFIG_PATH.
"""

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

# ── Pydantic models ──────────────────────────────────────────


class LLMSettings(BaseModel):
    model: str = "gemini-2.5-flash"
    summary_model: str = "gemini-2.0-flash"  # summarization (flash-lite đã deprecated)
    temperature: float = 0.7
    top_p: float = 0.95
    top_k: int = 40
    max_output_tokens: int = 8192


class EmbeddingSettings(BaseModel):
    model: str = "gemini-embedding-001"
    dimension: int = 768
    batch_size: int = 20


class PromptsSettings(BaseModel):
    system_instruction: str = ""
    wiki_topic_extract_prompt: str = ""
    wiki_synthesis_prompt: str = ""


class RAGSettings(BaseModel):
    chunk_size: int = 1000
    chunk_overlap: int = 200
    top_k_results: int = 5
    max_doc_length: int = 8192
    max_query_length: int = 2048


class AgentConfig(BaseModel):
    llm: LLMSettings = LLMSettings()
    embedding: EmbeddingSettings = EmbeddingSettings()
    prompts: PromptsSettings = PromptsSettings()
    rag: RAGSettings = RAGSettings()


# ── Loader ───────────────────────────────────────────────────

_DEFAULT_CONFIG_PATH = Path(__file__).parent / "llm_config.yaml"


@lru_cache
def get_llm_config() -> AgentConfig:
    """Load YAML config, cache kết quả.

    Override đường dẫn bằng env var ``LLM_CONFIG_PATH``.
    """
    config_path = Path(os.getenv("LLM_CONFIG_PATH", str(_DEFAULT_CONFIG_PATH)))

    if not config_path.exists():
        # Fallback về defaults nếu file không tồn tại
        return AgentConfig()

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    return AgentConfig(**raw)
