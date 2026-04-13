# QWEN.md — MemRAG Chatbot

## Project Overview

**MemRAG Chatbot** is a multimodal AI research assistant with RAG (Retrieval-Augmented Generation) and long-term memory. It enables users to upload PDFs, chat with document content, transcribe meetings via voice, and maintain structured wiki knowledge bases — all with AI that remembers context across sessions.

**Live:** https://d3qrt08bgfyl3d.cloudfront.net

### Core Capabilities
- **Chat streaming** — SSE token-by-token responses
- **PDF RAG** — Semantic search across uploaded documents with citations
- **Voice transcription** — Real-time meeting transcription via Soniox STT
- **Long-term memory** — mem0 persists important information across sessions
- **Multimodal input** — Text + images (Gemini Vision) + audio
- **Multi-session** — Each `(user_id, session_id)` is an isolated conversation
- **Auto wiki synthesis** — AI-generated structured wiki pages after each ingestion event

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 18, TypeScript, Vite, TailwindCSS, Zustand, React Query, ReactFlow |
| **Backend** | FastAPI, Python 3.11, Google ADK, Gemini 2.5 Flash |
| **AI Memory** | mem0 (long-term), ADK DynamoDBSessionService (short-term) |
| **Vector DB** | Qdrant (768-dim embeddings via gemini-embedding-001) |
| **Databases** | DynamoDB (sessions, meetings), PostgreSQL (auth, users) |
| **File Storage** | AWS S3 (PDF uploads + frontend static files) |
| **CDN / Proxy** | AWS CloudFront (FE serving + API reverse proxy) |
| **Infrastructure** | AWS ECS (EC2 launch type), Terraform |
| **CI/CD** | GitHub Actions (2 pipelines: backend + frontend) |

---

## Architecture

```
User Browser
     │ HTTPS
     ▼
CloudFront (d3qrt08bgfyl3d.cloudfront.net)
     │
     ├── /* ──────────► S3 Bucket (React SPA)
     │
     └── /api/* ──────► EC2 :8000 (FastAPI)
                              │
                    ┌─────────┴──────────┐
                    │   ECS Task         │
                    │  ┌─────────────┐   │
                    │  │  backend    │   │
                    │  │  FastAPI    │──►│── Gemini API
                    │  │  :8000      │   │── mem0
                    │  └─────────────┘   │── S3 (PDFs)
                    │  ┌─────────────┐   │
                    │  │  qdrant     │   │
                    │  │  :6333      │   │
                    │  └─────────────┘   │
                    └────────────────────┘
```

`/api/*` is proxied by CloudFront to EC2 → FE and BE share origin → no CORS needed.

### Backend Architecture

**Request Flow:**
```
HTTP Request → FastAPI Router (api/v1/) → Service Layer → Repository / ADK Agent → Response
```

**Multi-Agent System:** Root Agent (gemini-2.5-flash) with 9 tools:
- `search_documents`, `search_meeting_transcripts`
- `list_user_documents`, `list_meetings`
- `retrieve_memories`, `store_memory`
- `read_wiki_index`, `read_wiki_page`, `list_wiki_pages`

**Key Design Patterns:**
- **ADK Runner** uses `lru_cache` singleton — one instance per process
- **Database clients** (`get_qdrant_client`, `get_mem0_client`, etc.) use `lru_cache` — single instance per process
- **Services** receive dependencies via constructor — no global calls inside methods
- **ContextFilterPlugin** on Root Agent performs context summarization when conversation exceeds `max_context_messages`
- **Wiki auto-synthesis** runs in background after PDF upload or transcript stop

---

## Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── agents/          # Google ADK agents, plugins, tools
│   │   ├── api/v1/          # FastAPI routers
│   │   ├── core/            # Config, database clients, logging
│   │   ├── exceptions/      # Global exception handlers
│   │   ├── models/          # SQLAlchemy models
│   │   ├── repositories/    # Qdrant, mem0, wiki data layer
│   │   ├── schemas/         # Pydantic models
│   │   ├── services/        # Business logic (Chat, RAG, Memory, Wiki, Soniox)
│   │   ├── utils/           # Gemini embeddings, helpers
│   │   └── main.py
│   ├── tests/
│   ├── pyproject.toml       # uv, ruff, pytest config
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── api/             # axios client, SSE streaming
│   │   ├── components/      # React components
│   │   ├── hooks/           # React Query hooks
│   │   ├── services/        # AudioCaptureService
│   │   ├── store/           # Zustand state
│   │   ├── types/           # TypeScript types
│   │   └── utils/           # Helpers
│   ├── package.json
│   └── vite.config.ts
├── infrastructure/          # Terraform (AWS)
├── docs/                    # Architecture, CI/CD, specs
├── scripts/                 # Utility scripts
├── docker-compose.yml       # Qdrant + DynamoDB + PostgreSQL + Backend
└── .github/workflows/       # CI/CD pipelines
```

---

## Commands

### Quick Start

```bash
# Clone and setup
git clone <repo-url> && cd proj2
cp backend/.env.example backend/.env
# Add GEMINI_API_KEY to .env

# Start all services (Qdrant + DynamoDB + PostgreSQL + Backend)
docker compose up -d

# View logs
docker compose logs backend -f

# Rebuild after code changes
docker compose build backend && docker compose up -d
```

Backend: http://localhost:8000 | API docs: http://localhost:8000/docs

### Backend (standalone)

```bash
cd backend
uv sync
uv run python -m app.main
```

### Frontend (standalone)

```bash
cd frontend
npm ci
npm run dev        # http://localhost:5173 (Vite proxies /api → :8000)
npm run build      # tsc + vite build → dist/
npm run lint       # eslint (0 warnings allowed)
```

### Testing

```bash
cd backend

# Run all tests
uv run pytest tests/ -v

# With coverage
uv run pytest tests/ --cov=app --cov-report=term-missing

# Run specific test
uv run pytest tests/test_chat.py::test_chat_basic -v
```

Tests use `app.dependency_overrides` to mock all external clients — no API keys or running services needed.

### Linting & Formatting

```bash
# Backend
cd backend && uv run ruff format . && uv run ruff check .

# Frontend
cd frontend && npm run lint
```

---

## Environment Variables

Create `backend/.env` (see `.env.example`):

```env
# Required
GEMINI_API_KEY=your-key-here

# CORS — JSON array format (required)
ALLOWED_ORIGINS=["http://localhost:5173"]

# Qdrant (overridden by docker-compose when running Docker)
QDRANT_URL=http://localhost:6333

# DynamoDB (overridden by docker-compose when running Docker)
DYNAMODB_ENDPOINT_URL=http://localhost:8001

# PostgreSQL (overridden by docker-compose when running Docker)
DATABASE_URL=postgresql+asyncpg://memrag:memrag@localhost:5432/memrag

# Storage: "local" or "s3"
STORAGE_BACKEND=local

# S3 (only needed when STORAGE_BACKEND=s3)
S3_BUCKET=
S3_REGION=ap-southeast-2
S3_ACCESS_KEY_ID=
S3_SECRET_ACCESS_KEY=

# Soniox (voice transcription)
SONIOX_API_KEY=your-soniox-key
SONIOX_MODEL=stt-rt-preview
SONIOX_TARGET_LANG=vi
```

### Key Config (tunable via `.env`)
| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_CONTEXT_MESSAGES` | 20 | Max messages before summarization |
| `SUMMARY_THRESHOLD` | 22 | Trigger summary at this message count |
| `SUMMARY_KEEP_RECENT` | 10 | Keep recent messages after summary |
| `SCORE_THRESHOLD` | 0.6 | Filter out low-scoring RAG results |
| `MEMORY_SEARCH_LIMIT` | 15 | Search scope for memory |
| `WIKI_ENABLED` | true | Enable wiki auto-synthesis |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/chat` | Chat (blocking) |
| `POST` | `/api/v1/chat/stream` | Chat (SSE streaming) |
| `POST` | `/api/v1/documents/upload` | Upload PDF |
| `GET` | `/api/v1/documents` | List documents |
| `DELETE` | `/api/v1/documents/{id}` | Delete document |
| `GET` | `/api/v1/memory` | View long-term memories |
| `DELETE` | `/api/v1/memory/{id}` | Delete memory |
| `POST` | `/api/v1/transcription/start` | Start meeting transcription |
| `POST` | `/api/v1/transcription/audio/{id}` | Send audio chunk (PCM16) |
| `GET` | `/api/v1/transcription/stream/{id}` | SSE transcription results |
| `POST` | `/api/v1/transcription/stop/{id}` | Stop transcription |
| `GET` | `/api/v1/sessions` | List sessions |
| `DELETE` | `/api/v1/sessions/{id}` | Delete session |

**Authentication:** Header `X-User-ID` (defaults to `"default_user"`). All data is scoped per `user_id`.

---

## CI/CD

### Backend Pipeline (push to `main`, `backend/**` changes)
1. **Lint** — ruff format + check
2. **Test** — pytest with coverage
3. **Build & Push** — Docker image → ECR
4. **Deploy** — ECS rolling update (wait for stability)

### Frontend Pipeline (push to `main`, `frontend/**` changes)
1. **Build** — tsc + vite build
2. **Deploy** — S3 sync + CloudFront invalidate

---

## Git Conventions

Use **Conventional Commits**: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`

Example: `feat: add voice transcription to RAG pipeline`

---

## Development Notes

### Important Patterns
- `Part.from_text()` in google-genai is **keyword-only**: use `Part.from_text(text=...)`
- `ALLOWED_ORIGINS` must be a JSON array: `["http://localhost:5173"]` (not comma-separated)
- DynamoDB requires `float` ↔ `Decimal` conversion
- Changing embedding dimension requires full Qdrant reset: `docker compose down -v && docker compose up -d`
- Wiki auto-synthesis runs in background — does not block responses

### Database Clients
All clients use `lru_cache` — single instance per process:
- `get_qdrant_client()` / `get_async_qdrant_client()`
- `get_mem0_client()`
- `get_dynamodb_resource()`
- `get_runner()` (ADK runner)

### Testing
- HTTP tests use `app.dependency_overrides` (not `patch()`)
- Fixtures in `conftest.py` register overrides automatically
- Tests apply via `pytestmark = pytest.mark.usefixtures("mock_qdrant_client")`
- For unit tests, inject mocks directly into service constructors
- Async mocks: use `AsyncMock` for session service methods; async generators for `runner.run_async`

### Reset Qdrant Data
```bash
docker compose down -v && docker compose up -d
```
⚠️ This deletes ALL vector data.

---

## Key Documentation Files

- `docs/multi-agent-architecture.md` — 3-tier agents, AgentTool communication, context management
- `docs/cicd-flow.md` — CI/CD pipeline details
- `docs/spec.md` — Product spec
- `CLAUDE.md` — Deep dive into architecture, design decisions, working with Claude
