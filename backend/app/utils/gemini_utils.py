"""Utilities cho Google Gemini API (embedding, query expansion, v.v.)."""

import asyncio
import random
from functools import lru_cache

import structlog
from google import genai
from google.genai import types as genai_types

from app.core.config import get_settings
from app.core.llm_config import get_llm_config

logger = structlog.get_logger(__name__)

# Cache kích thước 256 cho query embeddings — cùng query không embed lại
_QUERY_EMBEDDING_CACHE_SIZE = 256

# Retry config cho 429 RESOURCE_EXHAUSTED / 503 UNAVAILABLE
_RETRY_MAX_ATTEMPTS = 6
_RETRY_BASE_DELAY = 1.0  # seconds
_RETRY_MAX_DELAY = 60.0  # seconds cap — 503 cần thời gian dài hơn để recover


async def _with_retry(coro_fn, *args, **kwargs):
    """
    Chạy async function với exponential backoff khi gặp 429.
    Jitter ngẫu nhiên tránh thundering herd khi nhiều requests cùng retry.
    """
    last_exc = None
    for attempt in range(_RETRY_MAX_ATTEMPTS):
        try:
            return await coro_fn(*args, **kwargs)
        except Exception as exc:
            err_str = str(exc)
            is_retryable = (
                "429" in err_str
                or "RESOURCE_EXHAUSTED" in err_str
                or "500" in err_str
                or "INTERNAL" in err_str
                or "503" in err_str
                or "UNAVAILABLE" in err_str
            )
            if not is_retryable:
                raise  # Lỗi khác → không retry
            last_exc = exc
            # 500/503 cần delay cao hơn 429 vì server-side error thường cần thêm thời gian
            base = (
                3.0
                if (
                    "500" in err_str
                    or "INTERNAL" in err_str
                    or "503" in err_str
                    or "UNAVAILABLE" in err_str
                )
                else _RETRY_BASE_DELAY
            )
            delay = min(base * (2**attempt) + random.uniform(0, 1), _RETRY_MAX_DELAY)
            logger.warning(
                "gemini_api_retry",
                attempt=attempt + 1,
                max_attempts=_RETRY_MAX_ATTEMPTS,
                delay_s=round(delay, 2),
                error=err_str[:120],
            )
            await asyncio.sleep(delay)

    raise last_exc


@lru_cache
def get_genai_client() -> genai.Client:
    settings = get_settings()
    return genai.Client(api_key=settings.gemini_api_key)


def get_embedding(text: str) -> list[float]:
    """Embed một đoạn text bằng Gemini embedding model (RETRIEVAL_DOCUMENT)."""
    config = get_llm_config()
    client = get_genai_client()

    result = client.models.embed_content(
        model=config.embedding.model,
        contents=text[: config.rag.max_doc_length],
        config=genai_types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=config.embedding.dimension,
        ),
    )
    return result.embeddings[0].values


@lru_cache(maxsize=_QUERY_EMBEDDING_CACHE_SIZE)
def get_query_embedding(text: str) -> tuple[float, ...]:
    """
    Embed một câu query (RETRIEVAL_QUERY). Cache LRU 256 entries.
    Returns tuple (hashable) để tương thích với lru_cache.
    """
    config = get_llm_config()
    client = get_genai_client()

    result = client.models.embed_content(
        model=config.embedding.model,
        contents=text[: config.rag.max_query_length],
        config=genai_types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=config.embedding.dimension,
        ),
    )
    return tuple(result.embeddings[0].values)


async def expand_query(query: str, n: int = 1) -> list[str]:
    """
    Tạo N cách diễn đạt khác nhau cho query gốc (query expansion).
    Default n=1 để tránh quá nhiều concurrent LLM calls với multi-agent.
    Retry tự động khi gặp 429 RESOURCE_EXHAUSTED.
    Returns list rỗng nếu thất bại (graceful degradation).
    """
    if n <= 0:
        return []

    config = get_llm_config()
    client = get_genai_client()

    prompt = (
        f"Tạo {n} cách diễn đạt khác nhau cho câu hỏi sau để tìm kiếm "
        "thông tin trong vector database. Chỉ liệt kê câu hỏi, mỗi câu một dòng, "
        "không đánh số, không giải thích.\n\n"
        f"Câu gốc: {query}"
    )

    async def _call():
        return await client.aio.models.generate_content(
            model=config.llm.summary_model,
            contents=prompt,
        )

    try:
        response = await _with_retry(_call)
        lines = [line.strip() for line in (response.text or "").splitlines() if line.strip()]
        return lines[:n]
    except Exception as exc:
        logger.warning("query_expansion_failed", error=str(exc))
        return []  # graceful degradation — dùng query gốc


def get_embeddings_batch(texts: list[str], batch_size: int | None = None) -> list[list[float]]:
    """Embed nhiều đoạn text theo batch (RETRIEVAL_DOCUMENT)."""
    config = get_llm_config()
    client = get_genai_client()
    all_embeddings: list[list[float]] = []

    effective_batch_size = batch_size or config.embedding.batch_size

    for i in range(0, len(texts), effective_batch_size):
        batch = [t[: config.rag.max_doc_length] for t in texts[i : i + effective_batch_size]]
        result = client.models.embed_content(
            model=config.embedding.model,
            contents=batch,
            config=genai_types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=config.embedding.dimension,
            ),
        )
        for emb in result.embeddings:
            all_embeddings.append(emb.values)
        logger.info("batch_embedded", batch_index=i, count=len(batch))

    return all_embeddings
