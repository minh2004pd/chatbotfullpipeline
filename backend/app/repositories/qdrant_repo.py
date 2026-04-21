import uuid

import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
)

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


class QdrantRepository:
    def __init__(self, client: QdrantClient):
        self.client = client
        self.settings = get_settings()
        self.collection = self.settings.qdrant_collection_rag

    def upsert_chunks(
        self,
        chunks: list[str],
        embeddings: list[list[float]],
        document_id: str,
        filename: str,
        user_id: str,
        file_hash: str = "",
    ) -> int:
        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=embedding,
                payload={
                    "text": chunk,
                    "document_id": document_id,
                    "filename": filename,
                    "user_id": user_id,
                    "chunk_index": idx,
                    "file_hash": file_hash,
                },
            )
            for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings))
        ]

        self.client.upsert(collection_name=self.collection, points=points)
        logger.info("chunks_upserted", document_id=document_id, count=len(points))
        return len(points)

    def search(
        self,
        query_vector: list[float],
        user_id: str | None = None,
        top_k: int = 5,
        score_threshold: float = 0.0,
    ) -> list[dict]:
        query_filter = None
        if user_id:
            query_filter = Filter(
                must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
            )

        results = self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            query_filter=query_filter,
            limit=top_k,
            score_threshold=score_threshold,
            with_payload=True,
        ).points

        return [
            {
                "text": r.payload["text"],
                "document_id": r.payload["document_id"],
                "filename": r.payload["filename"],
                "score": r.score,
            }
            for r in results
        ]

    def list_documents(self, user_id: str) -> list[dict]:
        """Return unique documents for a user."""
        results, _ = self.client.scroll(
            collection_name=self.collection,
            scroll_filter=Filter(
                must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
            ),
            with_payload=True,
            limit=1000,
        )

        seen: dict[str, dict] = {}
        for point in results:
            doc_id = point.payload["document_id"]
            if doc_id not in seen:
                seen[doc_id] = {
                    "document_id": doc_id,
                    "filename": point.payload["filename"],
                    "user_id": point.payload["user_id"],
                }

        return list(seen.values())

    def find_by_hash(self, user_id: str, file_hash: str) -> dict | None:
        """Check if a file with the same hash already exists for this user."""
        results, _ = self.client.scroll(
            collection_name=self.collection,
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                    FieldCondition(key="file_hash", match=MatchValue(value=file_hash)),
                ]
            ),
            with_payload=True,
            limit=1,
        )
        if results:
            p = results[0].payload
            return {
                "document_id": p["document_id"],
                "filename": p["filename"],
                "user_id": p["user_id"],
            }
        return None

    def delete_document(self, document_id: str) -> None:
        self.client.delete(
            collection_name=self.collection,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
                )
            ),
        )
        logger.info("document_deleted", document_id=document_id)

    def count_chunks(self, document_id: str) -> int:
        result = self.client.count(
            collection_name=self.collection,
            count_filter=Filter(
                must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
            ),
            exact=True,
        )
        return result.count
