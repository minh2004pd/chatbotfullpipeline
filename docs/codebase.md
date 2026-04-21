# Codebase Architecture — MemRAG Chatbot

> Cập nhật lần cuối: 2026-04-21
> Tham chiếu tài liệu chi tiết: [spec.md](spec.md) | [wiki.md](wiki.md) | [memory.md](memory.md) | [auth.md](auth.md) | [soniox-plan.md](soniox-plan.md)

---

## 1. Tổng quan hệ thống

**MemRAG** là AI Research Assistant chatbot với:
- **RAG** (Retrieval-Augmented Generation) từ PDF documents
- **Long-term memory** (mem0) cho personalization
- **Realtime meeting transcription** (Soniox STT)
- **Wiki knowledge base** tự động tổng hợp từ documents + transcripts
- **Knowledge Graph** visualization (React Flow)

**Tech Stack:**
- Backend: **FastAPI** + **Google ADK** (Agent Development Kit) + **Gemini 2.5-flash**
- Frontend: **React 18** + **Vite** + **TypeScript** + **TailwindCSS** + **Zustand**
- Vector DB: **Qdrant** (RAG + mem0 + meetings)
- Session/Meeting storage: **AWS DynamoDB**
- Auth: **PostgreSQL** + **JWT** + Google OAuth
- File storage: **Local filesystem** (dev) / **S3** (production)
- Wiki storage: **Local filesystem** (dev) / **S3** (production)
- Infrastructure: **Terraform** → AWS ECS Fargate + ALB + RDS + DynamoDB + S3

---

## 2. Kiến trúc tổng thể

```
┌─────────────────────────────────────────────────────────────────┐
│  FRONTEND (React + Vite + TypeScript)                           │
│  Port 5173 (dev) / S3 + CloudFront (prod)                       │
│  Zustand stores → API clients → Components                     │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP/SSE/WebSocket
┌──────────────────────────▼──────────────────────────────────────┐
│  BACKEND (FastAPI + Google ADK)                                  │
│  Port 8000 / ECS Fargate (prod)                                  │
│                                                                  │
│  ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌────────────────┐   │
│  │ Chat API│  │Docs API  │  │Wiki API │  │Transcription   │   │
│  │ (SSE)   │  │(upload)  │  │(graph)  │  │API (WebSocket) │   │
│  └────┬────┘  └────┬─────┘  └────┬────┘  └───────┬────────┘   │
│       │            │             │                │             │
│  ┌────▼────────────▼─────────────▼────────────────▼──────────┐ │
│  │  ADK Agent (gemini-2.5-flash) + 9 Tools                   │ │
│  │  ContextFilterPlugin (auto-summarization)                  │ │
│  └────┬──────┬──────┬──────┬──────┬──────┬───────────────────┘ │
│       │      │      │      │      │      │                     │
│  ┌────▼─┐┌───▼──┐┌──▼───┐┌─▼────┐┌▼─────┐┌▼──────┐           │
│  │Qdrant││mem0  ││Wiki  ││Dynamo││S3/   ││Soniox │           │
│  │(RAG) ││(mem) ││(FS)  ││ DB   ││Local ││(STT)  │           │
│  └──────┘└──────┘└──────┘└──────┘└──────┘└───────┘           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Backend — Cấu trúc thư mục

```
backend/
├── app/
│   ├── main.py                      # FastAPI app factory, lifespan, middleware, routers
│   │
│   ├── agents/                      # Google ADK Agent system
│   │   ├── root_agent.py            # LlmAgent (gemini-2.5-flash) + 9 tools
│   │   ├── docs_agent.py            # Sub-agent cho documents (chưa dùng, reserved)
│   │   ├── meeting_agent.py         # Sub-agent cho meetings (chưa dùng, reserved)
│   │   ├── plugins/
│   │   │   └── context_filter_plugin.py  # Auto-summarize khi >22 messages, inject summary
│   │   └── tools/
│   │       ├── utils.py             # get_user_id(tool_context) helper
│   │       ├── qdrant_search_tool.py    # search_documents — RAG search trong PDF
│   │       ├── files_retrieval_tool.py  # list_user_documents — liệt kê files đã upload
│   │       ├── meeting_search_tool.py   # search_meeting_transcripts + list_meetings
│   │       ├── wiki_tools.py        # read_wiki_index + read_wiki_page + list_wiki_pages
│   │       ├── mem0_tools.py        # retrieve_memories + store_memory
│   │       └── pdf_ingestion_tool.py    # (legacy, không dùng trong root_agent)
│   │
│   ├── api/v1/                      # REST API endpoints
│   │   ├── chat.py                  # POST /chat, POST /chat/stream (SSE)
│   │   ├── documents.py             # POST /documents/upload, GET /documents, DELETE
│   │   ├── memory.py                # POST /memory/search, GET /memory, DELETE
│   │   ├── sessions.py              # GET /sessions, GET /sessions/{id}/messages, DELETE
│   │   ├── transcription.py         # WebSocket /transcription/*, meetings CRUD
│   │   ├── wiki.py                  # GET /wiki/graph, GET /wiki/pages/{cat}/{slug}
│   │   └── auth.py                  # POST /auth/register, /login, /logout, /refresh, Google OAuth
│   │
│   ├── core/                        # Configuration & infrastructure
│   │   ├── config.py                # Settings (Pydantic BaseSettings, .env loader)
│   │   ├── llm_config.py           # AgentConfig loader (YAML → Pydantic models)
│   │   ├── llm_config.yaml         # LLM/embedding/prompts/RAG config (single source of truth)
│   │   ├── database.py              # Qdrant/DynamoDB/mem0 client factories + ensure_collections
│   │   ├── database_auth.py         # PostgreSQL (SQLAlchemy async) for auth
│   │   ├── dependencies.py          # FastAPI DI wiring (repos → services → endpoints)
│   │   ├── security.py              # JWT encode/decode helpers
│   │   ├── csrf.py                  # CSRF middleware (skipped in debug)
│   │   ├── indexing_status.py       # In-memory wiki indexing status tracker
│   │   ├── logger.py                # structlog configuration
│   │   └── storages/                # File storage abstraction
│   │       ├── __init__.py          # get_storage() factory (local vs S3)
│   │       ├── base_storage.py      # StorageBackend ABC
│   │       ├── local_storage.py     # LocalStorage implementation
│   │       └── s3_storage.py        # S3Storage implementation (presigned URLs)
│   │
│   ├── repositories/                # Data access layer
│   │   ├── qdrant_repo.py           # QdrantRepository — upsert/search/delete vectors
│   │   ├── mem0_repo.py             # Mem0Repository — add/search/delete memories
│   │   ├── meeting_repo.py          # MeetingRepository — DynamoDB CRUD for meetings
│   │   └── wiki_repo.py             # WikiRepository — read/write wiki pages (local/S3)
│   │
│   ├── services/                    # Business logic layer
│   │   ├── chat_service.py          # ChatService — orchestrate ADK runner + SSE streaming
│   │   ├── rag_service.py           # RAGService — PDF chunking + embedding + Qdrant upsert
│   │   ├── document_service.py      # DocumentService — upload PDF → RAG ingest + wiki trigger
│   │   ├── memory_service.py        # MemoryService — thin wrapper over Mem0Repository
│   │   ├── wiki_service.py          # WikiService — 4-phase pipeline (MAP→REDUCE→SYNTHESIZE→FINALIZE)
│   │   ├── soniox_service.py        # SonioxService — WebSocket → Soniox STT → realtime transcript
│   │   ├── transcript_rag_service.py # TranscriptRAGService — ingest transcript → Qdrant
│   │   ├── dynamo_session_service.py # DynamoDBSessionService — ADK session persistence
│   │   └── auth_service.py          # AuthService — register/login/JWT/Google OAuth
│   │
│   ├── schemas/                     # Pydantic request/response models
│   │   ├── chat.py                  # ChatRequest, ChatResponse, Citation
│   │   ├── document.py              # DocumentResponse, UploadResponse
│   │   ├── memory.py                # MemorySearchRequest, MemoryResponse
│   │   ├── session.py               # SessionResponse
│   │   ├── transcription.py         # MeetingResponse, TranscriptionStatus, utterance models
│   │   ├── user.py                  # UserResponse
│   │   └── wiki.py                  # WikiGraphData, WikiGraphNode, WikiGraphEdge, WikiPage
│   │
│   ├── models/                      # SQLAlchemy ORM models
│   │   └── user.py                  # User model (PostgreSQL) — id, email, password_hash, etc.
│   │
│   ├── utils/
│   │   ├── gemini_utils.py          # get_genai_client(), _with_retry() cho Gemini API calls
│   │   ├── file_utils.py            # PDF text extraction, file hash, validation
│   │   └── wiki_utils.py            # parse_frontmatter, slug extraction helpers
│   │
│   └── exceptions/
│       └── handlers.py              # Global exception handlers (422, 500)
│
├── tests/                           # pytest test suite (~24 files)
│   ├── conftest.py                  # Fixtures: mock clients, services, FastAPI test app
│   ├── test_wiki_service.py         # Largest test file (~40KB) — wiki pipeline tests
│   ├── test_auth.py                 # Auth endpoints + JWT + Google OAuth
│   ├── test_dynamo_session_service.py # DynamoDB session CRUD
│   └── ...                          # test_chat, test_documents, test_memory, etc.
│
├── pyproject.toml                   # Python 3.11+, dependencies, ruff/pytest config
├── Dockerfile                       # Production container build
└── wiki/                            # Local wiki storage (dev)
    └── {user_id}/                   # Per-user wiki directory
```

---

## 4. Frontend — Cấu trúc thư mục

```
frontend/src/
├── App.tsx                          # Root component (AuthGuard → AppLayout)
├── main.tsx                         # React entry point (QueryClientProvider + App)
├── index.css                        # Global styles + TailwindCSS imports
│
├── api/                             # Axios API clients
│   ├── client.ts                    # Axios instance, JWT refresh interceptor, CSRF
│   ├── chat.ts                      # sendMessage(), streamChat() — SSE streaming
│   ├── documents.ts                 # uploadDocument(), listDocuments(), deleteDocument()
│   ├── memory.ts                    # searchMemories(), getAllMemories(), deleteMemory()
│   ├── sessions.ts                  # listSessions(), getSessionMessages(), deleteSession()
│   ├── transcription.ts             # startMeeting(), sendAudio(), streamTranscript()
│   ├── wiki.ts                      # getWikiGraph(), getWikiPage()
│   └── auth.ts                      # login(), register(), logout(), refreshToken()
│
├── components/
│   ├── auth/
│   │   ├── AuthGuard.tsx            # Route protection (redirect to login if unauthenticated)
│   │   └── LoginPage.tsx            # Login/Register form + Google OAuth button
│   ├── layout/
│   │   ├── AppLayout.tsx            # Main layout: sidebar + content area + panels
│   │   └── Sidebar.tsx              # Navigation sidebar (sessions, documents, meetings, wiki, memory)
│   ├── chat/
│   │   ├── ChatWindow.tsx           # Main chat view (MessageBubble list + input)
│   │   ├── MessageBubble.tsx        # Single message (Markdown + KaTeX + code highlighting + wiki links)
│   │   ├── MessageInput.tsx         # Chat input (text + image upload + voice)
│   │   ├── SessionList.tsx          # Chat session list in sidebar
│   │   └── CitationCard.tsx         # RAG citation display
│   ├── documents/
│   │   ├── DocumentPanel.tsx        # Document list panel (upload + list + delete + wiki status)
│   │   └── UploadZone.tsx           # Drag & drop PDF upload zone
│   ├── transcription/
│   │   ├── TranscriptionPanel.tsx   # Live transcription view (utterances + controls)
│   │   └── MeetingControls.tsx      # Start/stop meeting, status indicator
│   ├── wiki/
│   │   ├── WikiGraphPanel.tsx       # React Flow knowledge graph (dagre layout, filters, minimap)
│   │   ├── WikiNodeCard.tsx         # Custom React Flow node (color by type, backlink count)
│   │   └── WikiPageDrawer.tsx       # Side drawer: wiki page content (Markdown + Math + links)
│   ├── memory/
│   │   └── MemoryPanel.tsx          # Memory list (search + view + delete memories)
│   └── ui/
│       └── ToastContainer.tsx       # Toast notification system
│
├── hooks/                           # React Query + custom hooks
│   ├── useChat.ts                   # Chat logic: send message, SSE streaming, wiki access events
│   ├── useDocuments.ts              # Upload, list, delete documents (React Query mutations)
│   ├── useSessions.ts              # Session CRUD (list, load, delete, create new)
│   ├── useTranscription.ts          # WebSocket audio capture + transcript streaming
│   ├── useWikiGraph.ts              # React Query hook for wiki graph data
│   ├── useGraphLayout.ts            # Web Worker dagre layout computation
│   └── useMemory.ts                 # Memory search + list + delete
│
├── store/                           # Zustand state management
│   ├── authStore.ts                 # Auth state: user, isAuthenticated, login/logout actions
│   └── chatStore.ts                 # Chat state: messages, sessions, userId, activePanel
│
├── services/
│   └── AudioCaptureService.ts       # Web Audio API → PCM capture for Soniox
│
├── types/
│   └── index.ts                     # TypeScript interfaces (Message, Document, Meeting, WikiGraph, etc.)
│
├── utils/
│   ├── debounce.ts                  # Debounce utility
│   ├── fixMalformedTables.ts        # Fix broken Markdown tables from LLM output
│   ├── wikiGraphLayout.ts           # Dagre layout helper
│   └── wikiNodeColors.ts            # Color mapping per wiki node type
│
├── styles/
│   └── katex-dark.css               # KaTeX dark mode styling
│
└── workers/
    └── graphLayout.worker.ts        # Web Worker for dagre graph computation (off main thread)
```

---

## 5. Dependency Graph (Backend)

```
                    ┌──────────────────────────────────┐
                    │         API Endpoints             │
                    │  (chat, documents, wiki, etc.)    │
                    └───────────┬──────────────────────┘
                                │ FastAPI Depends()
                    ┌───────────▼──────────────────────┐
                    │        dependencies.py            │
                    │  (DI wiring, Annotated shortcuts)  │
                    └──┬────┬────┬────┬────┬────┬──────┘
                       │    │    │    │    │    │
            ┌──────────▼┐ ┌▼────▼┐ ┌▼────▼┐ ┌▼─────────┐
            │ChatService│ │RAG   │ │Wiki  │ │Auth      │
            │           │ │Svc   │ │Svc   │ │Service   │
            └─────┬─────┘ └──┬───┘ └──┬───┘ └────┬─────┘
                  │          │        │           │
            ┌─────▼─────┐   │   ┌────▼────┐  ┌───▼──────┐
            │ADK Runner │   │   │WikiRepo │  │PostgreSQL│
            │(root_agent│   │   │(FS/S3)  │  │(users)   │
            │+9 tools)  │   │   └─────────┘  └──────────┘
            └─────┬─────┘   │
                  │     ┌────▼─────┐
            ┌─────▼──┐  │QdrantRepo│
            │DynamoDB │  │(vectors) │
            │Sessions │  └────┬─────┘
            └────────┘       │
                         ┌───▼────┐
                         │Qdrant  │
                         │Server  │
                         └────────┘
```

### Annotated Dependency Shortcuts (dependencies.py)

| Shortcut | Type | Dùng trong |
|----------|------|------------|
| `UserIDDep` | `str` | Mọi endpoint cần auth |
| `ChatServiceDep` | `ChatService` | chat.py |
| `RAGServiceDep` | `RAGService` | documents.py |
| `DocumentServiceDep` | `DocumentService` | documents.py |
| `MemoryServiceDep` | `MemoryService` | memory.py |
| `SessionServiceDep` | `DynamoDBSessionService` | sessions.py |
| `WikiServiceDep` | `WikiService` | wiki.py |
| `WikiRepoDep` | `WikiRepository` | wiki.py |
| `SettingsDep` | `Settings` | everywhere |

---

## 6. ADK Agent — 9 Tools

| Tool | File | Mục đích |
|------|------|----------|
| `search_documents` | `qdrant_search_tool.py` | RAG search trong PDF documents |
| `list_user_documents` | `files_retrieval_tool.py` | Liệt kê files đã upload |
| `search_meeting_transcripts` | `meeting_search_tool.py` | RAG search trong meeting transcripts |
| `list_meetings` | `meeting_search_tool.py` | Liệt kê danh sách meetings |
| `read_wiki_index` | `wiki_tools.py` | Đọc bản đồ tri thức wiki (entry point) |
| `read_wiki_page` | `wiki_tools.py` | Đọc nội dung 1 trang wiki cụ thể |
| `list_wiki_pages` | `wiki_tools.py` | Liệt kê pages trong 1 category wiki |
| `retrieve_memories` | `mem0_tools.py` | Tìm long-term memory (personalization) |
| `store_memory` | `mem0_tools.py` | Lưu thông tin cá nhân vào memory |

**Agent strategy**: Wiki first → RAG fallback → Memory for personalization.

---

## 7. Data Flow — Các luồng chính

### 7.1 Chat Flow
```
User message → POST /chat/stream (SSE)
  → ChatService.chat_stream()
    → _ensure_session() [DynamoDB]
    → ContextFilterPlugin.before_model() [auto-summarize if >22 msgs]
    → ADK Runner.run_async() [Gemini 2.5-flash]
      → Agent tự chọn tools (wiki → RAG → memory)
    → SSE stream response chunks to frontend
```

### 7.2 Document Upload Flow
```
PDF file → POST /documents/upload
  → DocumentService.upload_pdf()
    → file_utils.extract_text_from_pdf()
    → StorageBackend.save() [S3/local]
    → RAGService.ingest_document()
      → chunk text → embed (gemini-embedding-001) → Qdrant upsert
    → asyncio.create_task(WikiService.update_wiki_from_document())  [fire-and-forget]
      → 4-phase pipeline: MAP → REDUCE → SYNTHESIZE → FINALIZE
```

### 7.3 Meeting Transcription Flow
```
Start meeting → POST /transcription/start
  → MeetingRepository.create_meeting() [DynamoDB]
  
Audio stream → WS /transcription/audio/{meeting_id}
  → SonioxService → Soniox STT WebSocket → utterances
  → MeetingRepository.save_utterance() [DynamoDB]
  
Stop meeting → POST /transcription/stop/{meeting_id}
  → TranscriptRAGService.ingest() [Qdrant vectors]
  → asyncio.create_task(WikiService.update_wiki_from_transcript())
```

### 7.4 Wiki Pipeline (4-Phase)
```
Phase 1 MAP:    raw text → chunks → LLM extract entities/topics/summary (parallel)
Phase 2 REDUCE: merge + deduplicate by slug → limit counts
Phase 3 SYNTH:  per page → LLM synthesize (merge existing + new) → write (parallel)
Phase 4 FINAL:  update related pages → rebuild index.md → rebuild link_index.json → log
```

### 7.5 Context Filter (Auto-Summarization)
```
Before each LLM call:
  if message_count > 22 (summary_threshold):
    if no existing summary → blocking _generate_summary() [gemini-2.0-flash]
    if has existing summary → inject old summary + fire-and-forget re-summarize
  Inject: [summary_msg, ack] + recent 10 messages → LLM
```

---

## 8. Database Schema

### DynamoDB — Sessions (`memrag_sessions`)
| Key | Type | Format |
|-----|------|--------|
| PK (pk) | String | `{app_name}#{user_id}` |
| SK (session_id) | String | UUID hex |
| Attributes | — | title, state, events (JSON), created_at, updated_at, message_count |

### DynamoDB — Meetings (`memrag-meetings`)
| Key | Type | Format |
|-----|------|--------|
| PK | String | `USER#{user_id}` (metadata) or `MEETING#{meeting_id}` (utterances) |
| SK | String | `MEETING#{meeting_id}` or `UTTERANCE#{timestamp}#{sequence}` |

### Qdrant Collections
| Collection | Dimension | Dùng cho |
|------------|-----------|----------|
| `rag_documents` | 768 | PDF document chunks |
| `mem0_memories` | 768 | Long-term user memories (mem0) |
| `meetings` | 768 | Meeting transcript chunks |

### PostgreSQL — Users
| Column | Type | Mô tả |
|--------|------|-------|
| id | UUID (PK) | User identifier |
| email | String (unique) | Login email |
| display_name | String | Display name |
| password_hash | String (nullable) | bcrypt hash (null for Google OAuth) |
| google_id | String (nullable) | Google OAuth subject |
| is_active | Boolean | Account status |

---

## 9. Config — Environment Variables

Config đọc từ `.env` qua `pydantic-settings` (`config.py`) và `llm_config.yaml`.

### Quan trọng nhất:
| Variable | File | Mô tả |
|----------|------|-------|
| `GEMINI_API_KEY` | config.py | Google Gemini API key |
| `QDRANT_URL` | config.py | Qdrant server URL |
| `STORAGE_BACKEND` | config.py | `local` hoặc `s3` |
| `DATABASE_URL` | config.py | PostgreSQL connection string |
| `JWT_SECRET_KEY` | config.py | JWT signing key (required in prod) |
| `WIKI_ENABLED` | config.py | Toggle wiki auto-synthesis |
| `DEBUG` | config.py | Enable dev mode (X-User-ID header) |

### LLM Config (`llm_config.yaml` — single source of truth):
| Section | Key fields |
|---------|------------|
| `llm` | model (gemini-2.5-flash), temperature, max_output_tokens |
| `embedding` | model (gemini-embedding-001), dimension (768) |
| `prompts` | system_instruction, wiki_topic_extract_prompt, wiki_synthesis_prompt |
| `rag` | chunk_size (1000), chunk_overlap (200), top_k_results (5) |

---

## 10. Infrastructure (Terraform)

```
infrastructure/
├── main.tf              # AWS provider, region
├── variables.tf         # Input variables
├── terraform.tfvars     # Variable values (secrets)
├── vpc.tf               # VPC, subnets, NAT gateway, IGW
├── security_groups.tf   # SG rules (ALB, ECS, RDS, Qdrant)
├── ecs.tf               # ECS cluster, backend task/service (Fargate)
├── ecs_qdrant.tf        # Qdrant ECS task/service (Fargate + EFS)
├── alb.tf               # Application Load Balancer + HTTPS
├── ecr.tf               # ECR repository for backend Docker image
├── rds.tf               # PostgreSQL RDS instance
├── dynamodb.tf          # DynamoDB tables (sessions + meetings)
├── s3_frontend.tf       # S3 bucket + CloudFront for frontend
├── iam.tf               # IAM roles/policies for ECS tasks
├── service_discovery.tf # Cloud Map service discovery (qdrant.memrag.local)
├── autoscaling.tf       # ECS auto-scaling policies
├── outputs.tf           # ALB DNS, RDS endpoint, ECR URL
└── scripts/
    ├── deploy-all.sh    # Full deployment (infra + backend + frontend)
    ├── deploy-backend.sh # Build Docker → push ECR → update ECS
    ├── deploy-frontend.sh # Build Vite → sync S3 → invalidate CloudFront
    └── infra.sh         # Terraform plan/apply wrapper
```

---

## 11. Testing

```bash
# Chạy toàn bộ tests
cd backend && uv run pytest

# Chạy với coverage
cd backend && uv run pytest --cov=app --cov-report=term-missing

# Chạy 1 file cụ thể
cd backend && uv run pytest tests/test_wiki_service.py -v
```

**Test files quan trọng:**
| File | Lines | Mô tả |
|------|-------|-------|
| `test_wiki_service.py` | ~40KB | Wiki pipeline tests (lớn nhất) |
| `test_auth.py` | ~11KB | Auth endpoints + JWT + OAuth |
| `test_dynamo_session_service.py` | ~12KB | Session CRUD |
| `test_core_security.py` | ~13KB | Security utilities |
| `conftest.py` | ~6KB | Shared fixtures |

---

## 12. Quy ước Code

- **Python**: Python 3.11+, ruff formatter/linter (line-length 100), structlog logging
- **TypeScript**: Strict mode, ESLint, Vite + React 18
- **Naming**: snake_case (Python), camelCase (TypeScript)
- **Async**: Tất cả services/repos hỗ trợ async (`async def` + `await`)
- **DI Pattern**: FastAPI `Depends()` → `dependencies.py` wiring
- **Singleton**: `@lru_cache` cho clients (Qdrant, DynamoDB, mem0, wiki_repo)
- **Error handling**: structlog warning/error + graceful fallback (không crash)
- **User isolation**: Mọi data operation đều scoped by `user_id`

---

## 13. Quy định phát triển (Development Rules)

Để duy trì chất lượng codebase và đảm bảo quy trình deploy ổn định:

1.  **Testing**:
    -   Khi sửa bug hoặc thêm tính năng: Bắt buộc chạy lại toàn bộ test suite (`cd backend && uv run pytest`).
    -   Khi thêm tính năng mới: Phải viết bổ sung test case (unit/integration) tương ứng.
2.  **Documentation**:
    -   Cập nhật `docs/` ngay khi thay đổi logic/tính năng.
    -   Cập nhật `CLAUDE.md` nếu thay đổi kiến trúc hoặc tool.
    -   Cập nhật `README.md` nếu thay đổi tech stack hoặc quy trình cài đặt.
3.  **Code Style**: Luôn chạy `ruff format` cho Python và `eslint --fix` cho TypeScript trước khi commit.
