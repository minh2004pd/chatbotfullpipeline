# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MemRAG Chatbot — multimodal AI chatbot với RAG (PDF), long-term memory, và **realtime transcription** (Soniox). Stack: Google ADK + Gemini + mem0 + Qdrant + FastAPI + Soniox.

## Commands

All commands run from `backend/` using `uv`:

```bash
# Install dependencies
uv sync

# Run all tests
uv run pytest tests/ -v

# Run a single test file
uv run pytest tests/test_chat.py -v

# Run a single test
uv run pytest tests/test_chat.py::test_chat_basic -v

# Run with coverage
uv run pytest tests/ --cov=app --cov-report=term-missing

# Start dev server (requires .env with GEMINI_API_KEY)
uv run python -m app.main
```

Frontend commands run from `frontend/` using `npm`:

```bash
npm ci              # install dependencies (clean install)
npm run dev         # dev server on :5173 (proxies /api → :8000)
npm run build       # tsc + vite build → dist/
npm run lint        # eslint (0 warnings allowed)
```

Docker (from project root):
```bash
docker compose up -d        # start all services
docker compose build backend # rebuild after code changes
docker compose logs backend -f
docker compose down
```

## Architecture

### Request Flow
```
HTTP Request → FastAPI Router (api/v1/) → Service Layer → Repository / ADK Agent → Response
```

### Key Design Decisions

**ADK Agent** (`agents/root_agent.py`): Uses `lru_cache` on `get_runner()` — singleton per process. The `Runner` takes `app_name="memrag"` and `DynamoDBSessionService`. Sessions are created per `(user_id, session_id)` pair via `_ensure_session()` before each `runner.run_async()` call. `get_runner()` is defined in `core/dependencies.py` (not in `root_agent.py`) to avoid circular imports.

**Streaming** (`services/chat_service.py`): `chat_stream` passes `RunConfig(streaming_mode=StreamingMode.SSE)` to `runner.run_async()` — this enables token-level streaming from Gemini. Import: `from google.adk.agents.run_config import RunConfig, StreamingMode`. Yield on `event.partial` (not `event.is_final_response()`) to get incremental chunks.

**Tools vs Services**: The 4 ADK tools (`qdrant_search_tool`, `mem0_tools`, `files_retrieval_tool`, `pdf_ingestion_tool`) are called by the agent during inference. The `RAGService` and `MemoryService` are called directly by HTTP endpoints (upload, list, delete). Both paths share the same repositories.

**ContextFilterPlugin** (`agents/plugins/context_filter_plugin.py`): Implemented as an **async** `before_model_callback` on `LlmAgent`. Có 2 chế độ:
- **Truncation** (đơn giản): khi `max_context_messages < len(contents) < summary_threshold` → giữ N messages cuối.
- **Summarization** (tự động): khi `len(contents) >= summary_threshold` (default 30) hoặc đã có summary → gọi Gemini tóm tắt messages cũ, lưu `conversation_summary` + `summary_covered_count` vào ADK session state (tự persist DynamoDB), inject `[summary_msg + summary_ack] + recent_messages` vào `llm_request.contents`. Re-summarize khi có thêm `summary_threshold - summary_keep_recent` messages mới. Frontend vẫn load full history từ DynamoDB — chỉ BE dùng summary.

**Database clients** (`core/database.py`): All clients (`get_qdrant_client`, `get_async_qdrant_client`, `get_mem0_client`, `get_dynamodb_resource`) use `lru_cache` — single instance per process. `ensure_collections()` và `ensure_dynamo_table()` đều được gọi at app startup trong `lifespan`.

**Session Persistence** (`services/dynamo_session_service.py`): `DynamoDBSessionService` extends ADK `BaseSessionService`, lưu sessions vào DynamoDB. DynamoDB table key: `PK={app_name}#{user_id}`, `SK=session_id`. Title auto-extracted từ first user message trong `append_event()`. `float` ↔ `Decimal` conversion bắt buộc cho DynamoDB. Docker local dùng `amazon/dynamodb-local` trên port 8001; production dùng AWS DynamoDB (IAM role hoặc env vars). API endpoints: `GET /api/v1/sessions`, `GET /api/v1/sessions/{id}`, `DELETE /api/v1/sessions/{id}`.

**Embeddings** (`utils/gemini_utils.py`): Uses `google.genai.Client` (NOT deprecated `google.generativeai`). Batch embedding in groups of 20 chunks. Uses `RETRIEVAL_DOCUMENT` task type for indexing and `RETRIEVAL_QUERY` task type for search queries. Embedding dimension is 768 (`gemini-embedding-001`).

**Authentication**: User identity comes from the `X-User-ID` request header (`get_user_id()` in `dependencies.py`), defaulting to `"default_user"` if absent. All data (Qdrant vectors, mem0 memories) is scoped per `user_id`.

**Multimodal**: `ChatRequest` accepts optional `image_base64` + `image_mime_type`. `ChatService` builds a multi-part `Content` object (text + inline image) before calling `runner.run_async()`.

**Exception handlers** (`exceptions/handlers.py`): Global FastAPI handlers for `ValueError` → 400, `FileNotFoundError` → 404, and catch-all `Exception` → 500.

**Soniox Transcription** (`services/soniox_service.py`): Module-level `_sessions` dict (singleton per process) quản lý active WebSocket connections tới Soniox API. Flow: `POST /transcription/start` → mở WS + background receiver task + tạo meeting record → `POST /transcription/audio/{id}` (binary PCM16 chunks) → `GET /transcription/stream/{id}` (SSE) → `POST /transcription/stop/{id}` lưu utterances vào DynamoDB + ingest Qdrant. Dùng `websockets.asyncio.client` (v14+ API). ADK tool `search_meeting_transcripts` cho phép agent search trong transcript.

**Meeting Storage**: DynamoDB table `memrag-meetings` (single-table design) — `PK=USER#{user_id}, SK=MEETING#{id}` cho metadata; `PK=MEETING#{id}, SK=UTTERANCE#{ts}#{seq}` cho utterances. Qdrant collection `meetings` lưu chunked transcript embeddings (time-window 60s hoặc max 300 words/chunk). `ensure_meetings_table()` tạo table tự động khi startup.

**Frontend Audio Capture** (`services/AudioCaptureService.ts`): Dùng AudioWorklet (inline blob) resample → 16kHz PCM16. Hỗ trợ 3 nguồn: `mic` (getUserMedia), `system` (getDisplayMedia), `both` (AudioContext merge). Chunks gửi tới backend qua `POST /api/v1/transcription/audio/{id}`. `TranscriptionPanel` toggle bằng Mic icon ở header.

### Environment & Config

- `ALLOWED_ORIGINS` in `.env` must be JSON array format: `["http://localhost:5173"]` (not comma-separated)
- Docker: config comes entirely from env vars (docker-compose `env_file: .env`). No `.env` file is baked into the image.
- `QDRANT_URL` is overridden to `http://qdrant:6333` by docker-compose `environment` block, overriding `.env`'s `http://localhost:6333`.
- `DYNAMODB_ENDPOINT_URL=http://dynamodb-local:8000` được set trong docker-compose `environment` block (local). Để trống = real AWS DynamoDB.
- **CloudFront reverse proxy**: Production CloudFront distribution routes `/api/*` → EC2 backend (HTTP :8000) and `/*` → S3 frontend. FE is built with `VITE_API_BASE_URL=""` so axios uses relative URLs — same-origin, no CORS needed. `compress=false` on the `/api/*` behavior prevents buffering SSE streams at the edge.
- **Context summarization config** (tunable via `.env`): `SUMMARY_THRESHOLD=30`, `SUMMARY_KEEP_RECENT=10`, `MAX_CONTEXT_MESSAGES=20`.
- **Soniox config** (local `.env`): `SONIOX_API_KEY=xxx`, `SONIOX_MODEL=stt-rt-preview` (default), `SONIOX_TARGET_LANG=vi` (default). Không cần thay đổi docker-compose — Soniox là external API.

### Dependency Injection

Full FastAPI DI wiring lives in `app/dependencies.py`. The graph:
```
get_qdrant_client()        [lru_cache] → get_qdrant_repo() → get_rag_service() → get_document_service()
get_mem0_client()          [lru_cache] → get_mem0_repo()   → get_memory_service()
get_dynamodb_resource()    [lru_cache] → get_dynamo_session_service() [lru_cache] ─┐
get_runner()               [lru_cache] ────────────────────────────────────────────┼─ get_chat_service()
get_settings()             [lru_cache] ────────────────────────────────────────────┘
                                          get_dynamo_session_service() ─────────────── SessionServiceDep (sessions router)
```

Routers use `Annotated` shorthands: `ChatServiceDep`, `DocumentServiceDep`, etc. Services receive all deps via constructor — no global calls inside methods.

### Testing

**HTTP tests** use `app.dependency_overrides` (not `patch()`):
```python
app.dependency_overrides[get_qdrant_client] = lambda: mock_client
```
Fixtures in `conftest.py` register overrides automatically. Tests apply them via `pytestmark = pytest.mark.usefixtures("mock_qdrant_client")` — no fixture parameter needed in test functions.

**Unit tests** (test_rag_service.py) inject mocks directly into service constructors:
```python
service = RAGService(qdrant_repo=MagicMock(spec=QdrantRepository), settings=get_settings())
```

Key async mock rules:
- `session_service.get_session` / `create_session` → `AsyncMock`
- `runner.run_async` → `async def fake(**kwargs): yield event` (async generator)

## Working with Claude

- Propose a plan before implementing; explain tradeoffs when suggesting changes.
- Vietnamese comments and responses are fine.
- Changing embedding dimension requires a full Qdrant reset: `docker compose down -v && docker compose up -d` (all data lost).
