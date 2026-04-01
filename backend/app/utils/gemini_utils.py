"""Utilities cho Google Gemini API (embedding, v.v.)."""

from functools import lru_cache

import structlog
from google import genai
from google.genai import types as genai_types

from app.core.config import get_settings
from app.core.llm_config import get_llm_config

logger = structlog.get_logger(__name__)


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


def get_query_embedding(text: str) -> list[float]:
    """Embed một câu query (task_type=RETRIEVAL_QUERY)."""
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
    return result.embeddings[0].values


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
