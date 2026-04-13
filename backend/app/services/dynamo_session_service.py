"""DynamoDB-backed session service cho Google ADK."""

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import structlog
from google.adk.events.event import Event
from google.adk.sessions.base_session_service import BaseSessionService, GetSessionConfig
from google.adk.sessions.session import Session

logger = structlog.get_logger(__name__)


def _floats_to_decimal(obj: Any) -> Any:
    """Đệ quy convert float → Decimal để lưu DynamoDB (không hỗ trợ float)."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _floats_to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_floats_to_decimal(i) for i in obj]
    return obj


def _decimals_to_float(obj: Any) -> Any:
    """Đệ quy convert Decimal → float khi đọc từ DynamoDB."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _decimals_to_float(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimals_to_float(i) for i in obj]
    return obj


def _extract_text(event: Event) -> str | None:
    """Lấy text thuần từ event content (bỏ qua function call/response parts)."""
    if not event.content or not event.content.parts:
        return None
    texts = [p.text for p in event.content.parts if p.text]
    return " ".join(texts).strip() or None


class DynamoDBSessionService(BaseSessionService):
    """
    Session service backed by DynamoDB.

    Schema DynamoDB:
      PK:  pk           = "{app_name}#{user_id}"
      SK:  session_id   = "<uuid>"
    Attributes: title, state (Map), events (JSON string), created_at, updated_at,
                last_update_time (Decimal), message_count (int), app_name, user_id.
    """

    def __init__(self, table, app_name: str = "memrag") -> None:
        self._table = table  # boto3 Table resource
        self._app_name = app_name
        # Giữ app/user-scoped state in-memory (code hiện tại không dùng prefix app:/user:)
        self._app_state: dict[str, dict[str, Any]] = {}
        self._user_state: dict[str, dict[str, dict[str, Any]]] = {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _pk(self, app_name: str, user_id: str) -> str:
        return f"{app_name}#{user_id}"

    def _extract_title(self, event: Event) -> str | None:
        """Lấy text từ user event làm title (≤120 chars)."""
        if event.author != "user":
            return None
        text = _extract_text(event)
        if not text:
            return None
        return text[:120]

    @staticmethod
    def _strip_inline_images(raw_events: list[dict]) -> list[dict]:
        """Xóa inline image data trước khi lưu vào DynamoDB để tránh vượt giới hạn 400KB.
        Image part được thay bằng text placeholder '[Image: mime_type]'.
        """
        import copy

        result = []
        for event in raw_events:
            content = event.get("content") or {}
            parts = content.get("parts") or []
            if not any(p.get("inline_data") for p in parts):
                result.append(event)
                continue
            new_parts = []
            for part in parts:
                if part.get("inline_data"):
                    mime = (part["inline_data"] or {}).get("mime_type", "image")
                    new_parts.append({"text": f"[Image: {mime}]"})
                else:
                    new_parts.append(part)
            new_event = copy.deepcopy(event)
            new_event["content"]["parts"] = new_parts
            result.append(new_event)
        return result

    def _serialize_events(self, events: list[Event]) -> str:
        """Serialize list[Event] → JSON string, chỉ giữ user message và model text response.

        Tool call/response events bị loại bỏ hoàn toàn trước khi lưu DynamoDB
        để tránh vượt giới hạn 400KB.
        """
        raw = [e.model_dump(mode="json") for e in events]
        raw = self._strip_inline_images(raw)
        raw = self._filter_to_conversation_events(raw)
        return json.dumps(raw)

    @staticmethod
    def _filter_to_conversation_events(raw_events: list[dict]) -> list[dict]:
        """Chỉ giữ events chứa user text hoặc model text response.

        Loại bỏ: function_call, function_response (tool outputs) — quá lớn và không cần thiết
        để reconstruct conversation history.
        """
        result = []
        for event in raw_events:
            parts = (event.get("content") or {}).get("parts") or []
            has_tool = any(p.get("function_call") or p.get("function_response") for p in parts)
            if has_tool:
                continue
            has_text = any(p.get("text") for p in parts)
            if has_text:
                result.append(event)
        return result

    def _deserialize_events(self, events_json: str) -> list[Event]:
        """Deserialize JSON string → list[Event]."""
        raw = json.loads(events_json)
        result = []
        for item in raw:
            try:
                result.append(Event.model_validate(item))
            except Exception as exc:
                logger.warning("event_deserialize_failed", error=str(exc))
        return result

    def _session_to_item(self, session: Session, title: str, created_at: str) -> dict:
        """Convert Session → DynamoDB item."""
        now = datetime.now(timezone.utc).isoformat()
        user_message_count = sum(1 for e in session.events if e.author == "user")
        return {
            "pk": self._pk(session.app_name, session.user_id),
            "session_id": session.id,
            "app_name": session.app_name,
            "user_id": session.user_id,
            "title": title,
            "state": _floats_to_decimal(session.state),
            "events": self._serialize_events(session.events),
            "created_at": created_at,
            "updated_at": now,
            "last_update_time": Decimal(str(session.last_update_time)),
            "message_count": user_message_count,
        }

    def _item_to_session(self, item: dict) -> Session:
        """Convert DynamoDB item → Session."""
        events = self._deserialize_events(item.get("events", "[]"))
        state = _decimals_to_float(item.get("state", {}))
        return Session(
            id=item["session_id"],
            app_name=item["app_name"],
            user_id=item["user_id"],
            state=state,
            events=events,
            last_update_time=float(item.get("last_update_time", 0.0)),
        )

    def _get_item(self, app_name: str, user_id: str, session_id: str) -> dict | None:
        """Đọc raw item từ DynamoDB."""
        response = self._table.get_item(
            Key={"pk": self._pk(app_name, user_id), "session_id": session_id}
        )
        return response.get("Item")

    # ------------------------------------------------------------------
    # BaseSessionService interface
    # ------------------------------------------------------------------

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: dict | None = None,
        session_id: str | None = None,
    ) -> Session:
        sid = session_id or uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        session = Session(
            id=sid,
            app_name=app_name,
            user_id=user_id,
            state=state or {},
            events=[],
            last_update_time=0.0,
        )
        item = self._session_to_item(session, title="New Chat", created_at=now)
        self._table.put_item(Item=item)
        logger.info("session_created", session_id=sid, user_id=user_id)
        return session

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: GetSessionConfig | None = None,
    ) -> Session | None:
        item = self._get_item(app_name, user_id, session_id)
        if item is None:
            return None
        session = self._item_to_session(item)

        # Merge app/user state (giống InMemorySessionService)
        app_state = self._app_state.get(app_name, {})
        user_state = self._user_state.get(app_name, {}).get(user_id, {})
        for k, v in app_state.items():
            session.state[f"app:{k}"] = v
        for k, v in user_state.items():
            session.state[f"user:{k}"] = v

        # Apply filters nếu có
        if config:
            if config.num_recent_events is not None:
                session.events = session.events[-config.num_recent_events :]
            if config.after_timestamp is not None:
                session.events = [e for e in session.events if e.timestamp > config.after_timestamp]

        return session

    async def list_sessions(self, *, app_name: str, user_id: str):
        """Trả về danh sách sessions của user (chỉ metadata, không có events)."""
        from google.adk.sessions.base_session_service import ListSessionsResponse

        response = self._table.query(
            KeyConditionExpression="pk = :pk",
            ExpressionAttributeValues={":pk": self._pk(app_name, user_id)},
            ProjectionExpression="session_id, title, created_at, updated_at, message_count",
        )
        sessions = []
        for item in response.get("Items", []):
            # Tạo Session stub (không load events để tiết kiệm bandwidth)
            sessions.append(
                Session(
                    id=item["session_id"],
                    app_name=app_name,
                    user_id=user_id,
                    state={},
                    events=[],
                )
            )
        return ListSessionsResponse(sessions=sessions)

    async def delete_session(self, *, app_name: str, user_id: str, session_id: str) -> None:
        self._table.delete_item(Key={"pk": self._pk(app_name, user_id), "session_id": session_id})
        logger.info("session_deleted", session_id=session_id, user_id=user_id)

    async def update_session_state(
        self, *, app_name: str, user_id: str, session_id: str, state: dict
    ) -> None:
        """Cập nhật toàn bộ session state trong DynamoDB."""
        self._table.update_item(
            Key={"pk": self._pk(app_name, user_id), "session_id": session_id},
            UpdateExpression="SET #state = :state",
            ExpressionAttributeNames={"#state": "state"},
            ExpressionAttributeValues={":state": json.dumps(state)},
        )
        logger.info("session_state_updated", session_id=session_id, user_id=user_id)

    async def append_event(self, session: Session, event: Event) -> Event:
        # Gọi super() để xử lý state delta, temp state, và append vào session.events
        event = await super().append_event(session=session, event=event)

        # Lấy hoặc cập nhật title
        item = self._get_item(session.app_name, session.user_id, session.id)
        current_title = item.get("title", "New Chat") if item else "New Chat"
        created_at = (
            item.get("created_at", datetime.now(timezone.utc).isoformat())
            if item
            else datetime.now(timezone.utc).isoformat()
        )

        if current_title == "New Chat":
            new_title = self._extract_title(event)
            if new_title:
                current_title = new_title

        # Cập nhật session lên DynamoDB — _serialize_events chỉ lưu user/model text events
        dynamo_item = self._session_to_item(session, title=current_title, created_at=created_at)
        self._table.put_item(Item=dynamo_item)

        # Sync app/user state changes từ event state_delta
        state_delta = event.actions.state_delta if event.actions else {}
        for key, value in state_delta.items():
            if key.startswith("app:"):
                self._app_state.setdefault(session.app_name, {})[key[4:]] = value
            elif key.startswith("user:"):
                self._user_state.setdefault(session.app_name, {}).setdefault(session.user_id, {})[
                    key[5:]
                ] = value

        return event

    # ------------------------------------------------------------------
    # API helpers (không thuộc ADK interface — dùng cho session endpoints)
    # ------------------------------------------------------------------

    def list_sessions_with_metadata(self, *, app_name: str, user_id: str) -> list[dict]:
        """Query DynamoDB lấy metadata sessions (không load events)."""
        response = self._table.query(
            KeyConditionExpression="pk = :pk",
            ExpressionAttributeValues={":pk": self._pk(app_name, user_id)},
            ProjectionExpression="session_id, title, created_at, updated_at, message_count",
        )
        items = response.get("Items", [])
        # Sắp xếp mới nhất trước
        items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return items

    def get_session_messages(self, *, app_name: str, user_id: str, session_id: str) -> dict | None:
        """Trả về title + danh sách messages (user + model text only) của session."""
        item = self._get_item(app_name, user_id, session_id)
        if item is None:
            return None
        events = self._deserialize_events(item.get("events", "[]"))
        messages = []
        for e in events:
            if e.author not in ("user", "memrag_root_agent"):
                continue
            text = _extract_text(e)
            if not text:
                continue
            role = "user" if e.author == "user" else "model"
            messages.append(
                {
                    "role": role,
                    "content": text,
                    "timestamp": datetime.fromtimestamp(e.timestamp, tz=timezone.utc).isoformat(),
                }
            )
        return {
            "session_id": session_id,
            "title": item.get("title", "New Chat"),
            "messages": messages,
        }
