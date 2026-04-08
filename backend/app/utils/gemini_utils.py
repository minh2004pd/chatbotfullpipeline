"""Utilities cho Google Gemini API (embedding, v.v.)."""

from functools import lru_cache

import structlog
from google import genai
from google.genai import types as genai_types

from app.core.config import get_settings
from app.core.llm_config import get_llm_config

logger = structlog.get_logger(__name__)

# Cache kích thước 256 cho query embeddings — cùng một query không embed lại
# Nhất là trong summarization, cùng một session có thể gọi search_documents nhiều lần
_QUERY_EMBEDDING_CACHE_SIZE = 256


@lru_cache
def get_genai_client() -> genai.Client:
    settings = get_settings()
    return genai.Client(api_key=settings.gemini_api_key)


def get_embedding(text: str) -> list[float]:
    """Embed một đoạn text bằng Gemini embedding model."""
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
    Embed một câu query (task_type=RETRIEVAL_QUERY).
    Kết quả được cache — cùng query không embed lại.
    Returns tuple (hashable) thay vì list.
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
    # Trả về tuple (hashable) để có thể cache; caller chuyển thành list nếu cần
    return tuple(result.embeddings[0].values)


async def expand_query(query: str, n: int = 3) -> list[str]:
    """
    Tạo N cách diễn đạt khác nhau cho query gốc (query expansion).
    Giúp retrieval bắt được nhiều chunk liên quan hơn dù user diễn đạt khác cách.
    Dùng model nhẹ (summary_model) để tối ưu latency.
    Returns danh sách queries mở rộng (không bao gồm query gốc).
    """
    config = get_llm_config()
    client = get_genai_client()

    prompt = (
        f"Tạo {n} cách diễn đạt khác nhau cho câu hỏi sau để tìm kiếm "
        "thông tin trong vector database. Chỉ liệt kê câu hỏi, mỗi câu một dòng, "
        "không đánh số, không giải thích.\n\n"
        f"Câu gốc: {query}"
    )

    try:
        response = await client.aio.models.generate_content(
            model=config.llm.summary_model,
            contents=prompt,
        )
        lines = [line.strip() for line in (response.text or "").splitlines() if line.strip()]
        return lines[:n]
    except Exception as exc:
        logger.warning("query_expansion_failed", error=str(exc))
        return []


def get_embeddings_batch(texts: list[str], batch_size: int | None = None) -> list[list[float]]:
    """Embed nhiều đoạn text theo batch."""
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
