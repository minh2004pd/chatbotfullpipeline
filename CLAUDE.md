# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MemRAG Chatbot — multimodal AI chatbot với RAG (PDF) và long-term memory. Stack: Google ADK + Gemini + mem0 + Qdrant + FastAPI.

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

**ADK Agent** (`agents/root_agent.py`): Uses `lru_cache` on `get_runner()` and `get_session_service()` — singletons per process. The `Runner` takes `app_name="memrag"` and `InMemorySessionService`. Sessions are created per `(user_id, session_id)` pair via `_ensure_session()` before each `runner.run_async()` call.

**Streaming** (`services/chat_service.py`): `chat_stream` passes `RunConfig(streaming_mode=StreamingMode.SSE)` to `runner.run_async()` — this enables token-level streaming from Gemini. Import: `from google.adk.agents.run_config import RunConfig, StreamingMode`. Yield on `event.partial` (not `event.is_final_response()`) to get incremental chunks.

**Tools vs Services**: The 4 ADK tools (`qdrant_search_tool`, `mem0_tools`, `files_retrieval_tool`, `pdf_ingestion_tool`) are called by the agent during inference. The `RAGService` and `MemoryService` are called directly by HTTP endpoints (upload, list, delete). Both paths share the same repositories.

**ContextFilterPlugin** (`agents/plugins/context_filter_plugin.py`): Implemented as a `before_model_callback` on `LlmAgent`. Reads `max_context_messages` from ADK session state (set when session is created in `chat_service.py`).

**Database clients** (`core/database.py`): All clients (`get_qdrant_client`, `get_async_qdrant_client`, `get_mem0_client`) use `lru_cache` — single instance per process. `ensure_collections()` is called at app startup in `lifespan`.

**Embeddings** (`utils/gemini_utils.py`): Uses `google.genai.Client` (NOT deprecated `google.generativeai`). Batch embedding in groups of 20 chunks. Uses `RETRIEVAL_DOCUMENT` task type for indexing and `RETRIEVAL_QUERY` task type for search queries. Embedding dimension is 768 (`gemini-embedding-001`).

**Authentication**: User identity comes from the `X-User-ID` request header (`get_user_id()` in `dependencies.py`), defaulting to `"default_user"` if absent. All data (Qdrant vectors, mem0 memories) is scoped per `user_id`.

**Multimodal**: `ChatRequest` accepts optional `image_base64` + `image_mime_type`. `ChatService` builds a multi-part `Content` object (text + inline image) before calling `runner.run_async()`.

**Exception handlers** (`exceptions/handlers.py`): Global FastAPI handlers for `ValueError` → 400, `FileNotFoundError` → 404, and catch-all `Exception` → 500.

### Environment & Config

- `ALLOWED_ORIGINS` in `.env` must be JSON array format: `["http://localhost:5173"]` (not comma-separated)
- Docker: config comes entirely from env vars (docker-compose `env_file: .env`). No `.env` file is baked into the image.
- `QDRANT_URL` is overridden to `http://qdrant:6333` by docker-compose `environment` block, overriding `.env`'s `http://localhost:6333`.
- **CloudFront reverse proxy**: Production CloudFront distribution routes `/api/*` → EC2 backend (HTTP :8000) and `/*` → S3 frontend. FE is built with `VITE_API_BASE_URL=""` so axios uses relative URLs — same-origin, no CORS needed. `compress=false` on the `/api/*` behavior prevents buffering SSE streams at the edge.

### Dependency Injection

Full FastAPI DI wiring lives in `app/dependencies.py`. The graph:
```
get_qdrant_client() [lru_cache] → get_qdrant_repo() → get_rag_service() → get_document_service()
get_mem0_client()   [lru_cache] → get_mem0_repo()   → get_memory_service()
get_runner()        [lru_cache] ─┐
get_session_service()[lru_cache] ├─ get_chat_service()
get_settings()      [lru_cache] ─┘
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
