"""DynamoDB repository cho meetings và utterances.

Single-table design (memrag-meetings):
  - Meeting metadata : PK=USER#{user_id}    SK=MEETING#{meeting_id}
  - Utterance record : PK=MEETING#{meeting_id}  SK=UTTERANCE#{ts_ms:016d}#{seq:04d}
"""

from datetime import datetime, timezone
from decimal import Decimal

import structlog

logger = structlog.get_logger(__name__)


def _to_decimal(value: float | int | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _from_decimal(value) -> float | None:
    if value is None:
        return None
    return float(value)


class MeetingRepository:
    def __init__(self, table) -> None:
        self._table = table

    # ── Meeting metadata ─────────────────────────────────────────────────────

    def create_meeting(
        self,
        *,
        meeting_id: str,
        user_id: str,
        title: str,
    ) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        item = {
            "PK": f"USER#{user_id}",
            "SK": f"MEETING#{meeting_id}",
            "meeting_id": meeting_id,
            "user_id": user_id,
            "title": title,
            "status": "recording",
            "speakers": [],
            "languages": [],
            "utterance_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        self._table.put_item(Item=item)
        return item

    def get_meeting(self, *, meeting_id: str, user_id: str) -> dict | None:
        resp = self._table.get_item(Key={"PK": f"USER#{user_id}", "SK": f"MEETING#{meeting_id}"})
        return resp.get("Item")

    def update_meeting_status(
        self,
        *,
        meeting_id: str,
        user_id: str,
        status: str,
        duration_ms: int | None = None,
        speakers: list[str] | None = None,
        languages: list[str] | None = None,
        utterance_count: int | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        expr_names = {"#st": "status", "#ua": "updated_at"}
        expr_values = {":st": status, ":ua": now}
        set_parts = ["#st = :st", "#ua = :ua"]

        if duration_ms is not None:
            set_parts.append("duration_ms = :dm")
            expr_values[":dm"] = duration_ms
        if speakers is not None:
            set_parts.append("speakers = :sp")
            expr_values[":sp"] = speakers
        if languages is not None:
            set_parts.append("languages = :lg")
            expr_values[":lg"] = languages
        if utterance_count is not None:
            set_parts.append("utterance_count = :uc")
            expr_values[":uc"] = utterance_count

        self._table.update_item(
            Key={"PK": f"USER#{user_id}", "SK": f"MEETING#{meeting_id}"},
            UpdateExpression="SET " + ", ".join(set_parts),
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
        )

    def list_meetings(self, *, user_id: str) -> list[dict]:
        resp = self._table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
            ExpressionAttributeValues={
                ":pk": f"USER#{user_id}",
                ":sk_prefix": "MEETING#",
            },
        )
        items = resp.get("Items", [])
        # Convert Decimal fields
        for item in items:
            if "duration_ms" in item:
                item["duration_ms"] = int(item["duration_ms"])
            if "utterance_count" in item:
                item["utterance_count"] = int(item["utterance_count"])
        return items

    def delete_meeting(self, *, meeting_id: str, user_id: str) -> None:
        self._table.delete_item(Key={"PK": f"USER#{user_id}", "SK": f"MEETING#{meeting_id}"})

    # ── Utterances ────────────────────────────────────────────────────────────

    def save_utterance(
        self,
        *,
        meeting_id: str,
        user_id: str,
        seq: int,
        speaker: str,
        text: str,
        translated_text: str | None = None,
        language: str | None = None,
        confidence: float | None = None,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> dict:
        now = datetime.now(timezone.utc)
        ts_ms = int(now.timestamp() * 1000)
        sk = f"UTTERANCE#{ts_ms:016d}#{seq:04d}"
        item: dict = {
            "PK": f"MEETING#{meeting_id}",
            "SK": sk,
            "meeting_id": meeting_id,
            "user_id": user_id,
            "speaker": speaker,
            "text": text,
            "created_at": now.isoformat(),
        }
        if translated_text:
            item["translated_text"] = translated_text
        if language:
            item["language"] = language
        if confidence is not None:
            item["confidence"] = _to_decimal(confidence)
        if start_ms is not None:
            item["start_ms"] = start_ms
        if end_ms is not None:
            item["end_ms"] = end_ms

        self._table.put_item(Item=item)
        return item

    def list_utterances(self, *, meeting_id: str) -> list[dict]:
        resp = self._table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
            ExpressionAttributeValues={
                ":pk": f"MEETING#{meeting_id}",
                ":sk_prefix": "UTTERANCE#",
            },
        )
        items = resp.get("Items", [])
        for item in items:
            if "confidence" in item:
                item["confidence"] = _from_decimal(item["confidence"])
            if "start_ms" in item and item["start_ms"] is not None:
                item["start_ms"] = int(item["start_ms"])
            if "end_ms" in item and item["end_ms"] is not None:
                item["end_ms"] = int(item["end_ms"])
        return items
