"""TranscriptRAGService — chunk transcript và ingest vào Qdrant collection 'meetings'.

Chunking strategy: gom utterances theo time window (mặc định 60s) hoặc tới N từ,
sau đó embed batch và upsert vào Qdrant với deterministic point ID = meeting_id + chunk_index.
"""

import hashlib

import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from app.core.config import get_settings
from app.utils.gemini_utils import get_embeddings_batch

logger = structlog.get_logger(__name__)

_CHUNK_WINDOW_SEC = 60  # gom utterances trong 60s thành 1 chunk
_MAX_CHUNK_WORDS = 300  # tối đa 300 từ / chunk


class TranscriptRAGService:
    def __init__(self, qdrant_client: QdrantClient) -> None:
        self._client = qdrant_client
        self._settings = get_settings()
        self._collection = self._settings.qdrant_collection_meetings

    def ingest_utterances(
        self,
        *,
        meeting_id: str,
        user_id: str,
        title: str,
        utterances: list[dict],
    ) -> int:
        """Chunk utterances → embed → upsert Qdrant. Trả về số chunk đã ingest."""
        if not utterances:
            return 0

        chunks = self._chunk_utterances(utterances)
        if not chunks:
            return 0

        texts = [c["text"] for c in chunks]
        embeddings = get_embeddings_batch(texts)

        points = []
        for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            # Deterministic ID: meeting_id + chunk_index → tránh duplicate khi re-ingest
            point_id = hashlib.md5(f"{meeting_id}:{idx}".encode()).hexdigest()
            # Qdrant cần UUID-format hoặc uint64; dùng UUID hex
            point_id_uuid = f"{point_id[:8]}-{point_id[8:12]}-{point_id[12:16]}-{point_id[16:20]}-{point_id[20:]}"
            points.append(
                PointStruct(
                    id=point_id_uuid,
                    vector=embedding,
                    payload={
                        "text": chunk["text"],
                        "meeting_id": meeting_id,
                        "user_id": user_id,
                        "title": title,
                        "chunk_index": idx,
                        "start_ms": chunk.get("start_ms"),
                        "end_ms": chunk.get("end_ms"),
                        "speakers": chunk.get("speakers", []),
                    },
                )
            )

        self._client.upsert(collection_name=self._collection, points=points)
        logger.info("transcript_chunks_upserted", meeting_id=meeting_id, count=len(points))
        return len(points)

    def search(
        self,
        query_vector: list[float],
        user_id: str | None = None,
        top_k: int = 5,
        score_threshold: float = 0.0,
    ) -> list[dict]:
        """Tìm kiếm transcript chunks theo embedding vector."""
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        query_filter = None
        if user_id:
            query_filter = Filter(
                must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
            )

        results = self._client.query_points(
            collection_name=self._collection,
            query=query_vector,
            query_filter=query_filter,
            limit=top_k,
            score_threshold=score_threshold,
            with_payload=True,
        ).points

        return [
            {
                "text": r.payload.get("text", ""),
                "meeting_id": r.payload.get("meeting_id", ""),
                "title": r.payload.get("title", ""),
                "speakers": r.payload.get("speakers", []),
                "start_ms": r.payload.get("start_ms"),
                "end_ms": r.payload.get("end_ms"),
                "score": r.score,
            }
            for r in results
        ]

    def delete_meeting(self, meeting_id: str) -> None:
        """Xóa tất cả chunks của một meeting."""
        from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

        self._client.delete(
            collection_name=self._collection,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="meeting_id", match=MatchValue(value=meeting_id))]
                )
            ),
        )
        logger.info("meeting_chunks_deleted", meeting_id=meeting_id)

    # ── Chunking ──────────────────────────────────────────────────────────────

    @staticmethod
    def _chunk_utterances(utterances: list[dict]) -> list[dict]:
        """Gom utterances theo time window hoặc word limit."""
        chunks: list[dict] = []
        current_texts: list[str] = []
        current_speakers: set[str] = set()
        current_start_ms: int | None = None
        current_end_ms: int | None = None
        current_word_count = 0
        window_start_ms: int | None = None

        for utt in utterances:
            text = utt.get("text", "").strip()
            if not text:
                continue

            speaker = utt.get("speaker", "speaker_0")
            start_ms = utt.get("start_ms")
            end_ms = utt.get("end_ms")

            # Kiểm tra có vượt time window không
            if start_ms and window_start_ms:
                elapsed_sec = (start_ms - window_start_ms) / 1000
                if elapsed_sec >= _CHUNK_WINDOW_SEC:
                    if current_texts:
                        chunks.append(
                            {
                                "text": " ".join(current_texts),
                                "start_ms": current_start_ms,
                                "end_ms": current_end_ms,
                                "speakers": list(current_speakers),
                            }
                        )
                    current_texts = []
                    current_speakers = set()
                    current_start_ms = None
                    current_end_ms = None
                    current_word_count = 0
                    window_start_ms = start_ms

            words = len(text.split())
            if current_word_count + words > _MAX_CHUNK_WORDS and current_texts:
                chunks.append(
                    {
                        "text": " ".join(current_texts),
                        "start_ms": current_start_ms,
                        "end_ms": current_end_ms,
                        "speakers": list(current_speakers),
                    }
                )
                current_texts = []
                current_speakers = set()
                current_start_ms = None
                current_end_ms = None
                current_word_count = 0
                window_start_ms = start_ms

            current_texts.append(text)
            current_speakers.add(speaker)
            current_word_count += words
            if current_start_ms is None and start_ms:
                current_start_ms = start_ms
                window_start_ms = start_ms
            if end_ms:
                current_end_ms = end_ms

        if current_texts:
            chunks.append(
                {
                    "text": " ".join(current_texts),
                    "start_ms": current_start_ms,
                    "end_ms": current_end_ms,
                    "speakers": list(current_speakers),
                }
            )

        return chunks
