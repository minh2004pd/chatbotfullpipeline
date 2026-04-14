# MemRAG Chatbot — Spec hiện tại

> Tài liệu này mô tả **trạng thái thực tế** của hệ thống (không phải spec thiết kế ban đầu).
> Cập nhật lần cuối: 2026-04-09

---

## 1. Mô tả dự án

**MemRAG Chatbot** là chatbot cá nhân hóa đa phương thức (multimodal) xây dựng trên Google Agent Development Kit (ADK). Tính năng chính:

- Chat text/ảnh với Gemini, streaming SSE token-by-token
- Upload PDF để RAG (Retrieval-Augmented Generation)
- Long-term memory & personalization qua mem0
- Session persistence qua DynamoDB (sidebar history, resume)
- Auto-summarization context khi hội thoại dài
- **Realtime transcription** (Soniox STT) — voice → text → inject vào RAG

---

## 2. Tính năng chính

| Nhóm | Chi tiết |
|------|----------|
| **Chat** | Text + ảnh (base64 inline). Streaming SSE token-by-token qua `POST /api/v1/chat/stream`. Non-streaming qua `POST /api/v1/chat`. |
| **Authentication** | JWT (HS256) + httpOnly cookies. Đăng ký/đăng nhập email-password hoặc Google OAuth. Access token 15 phút, refresh token 7 ngày (rotation-based, unique jti per refresh). CSRF protection via `X-Requested-With` header. `X-User-ID` header chỉ active khi `DEBUG=true`. Xem `docs/auth.md`. |
| **RAG** | Upload PDF → chunk (LangChain TextSplitter, 1000/200 overlap) → embed (gemini-embedding-001, 768-dim) → Qdrant. Search qua `search_documents` ADK tool. Danh sách file qua `list_user_documents`. |
| **Long-term Memory** | mem0ai lưu facts/preferences/summary per user_id vào Qdrant collection `mem0_memories`. Tools: `store_memory`, `retrieve_memory`. |
| **Session Persistence** | `DynamoDBSessionService` extends ADK `BaseSessionService`. PK=`{app_name}#{user_id}`, SK=`session_id`. Title auto-extract từ first message. `GET /sessions`, `GET /sessions/{id}`, `DELETE /sessions/{id}`. |
| **Context Filter** | `ContextFilterPlugin` — async `before_model_callback`. Truncation khi `max_context_messages < len < summary_threshold`; auto-summarize (Gemini) khi `≥ summary_threshold` (default 30). Summary lưu vào ADK session state → persist DynamoDB. Frontend vẫn load full history. |
| **Realtime Transcription** | Soniox STT WebSocket. Flow: `POST /transcription/start` → `POST /transcription/audio/{id}` (binary PCM16) → `GET /transcription/stream/{id}` (SSE) → `POST /transcription/stop/{id}`. Agent có thể search transcript qua `search_meeting_transcripts` tool. |
| **Meeting Storage** | DynamoDB `memrag-meetings` (single-table). Metadata: `PK=USER#{user_id}, SK=MEETING#{id}`; utterances: `PK=MEETING#{id}, SK=UTTERANCE#{ts}#{seq}`. Qdrant collection `meetings` lưu transcript chunks (time-window 60s / max 300 words). Danh sách meeting qua `list_meetings` ADK tool; search nội dung qua `search_meeting_transcripts`. `GET /meetings`, `GET /meetings/{id}/transcript`, `DELETE /meetings/{id}`. |
| **Wiki Knowledge Base** | AI-generated structured wiki pages tự động xây dựng sau mỗi ingestion event (PDF upload / transcript stop). 3-tier pipeline: MAP (extract entities+topics) → REDUCE (deduplicate) → SYNTHESIZE (LLM merge content). Frontend React Flow knowledge graph visualization với filtering by source. Xem `docs/wiki.md`. |
| **File Storage** | S3 (production) hoặc local filesystem. Backend auto-switch qua `STORAGE_BACKEND` env var. Presigned URL 1h cho download. |
| **Multiuser** | User identity từ `X-User-ID` request header (default `"default_user"`). Tất cả data scoped per user_id. |

---

## 3. Tech Stack

| Layer | Công nghệ |
|-------|-----------|
| **LLM** | Gemini 2.5 Flash (google-adk ≥ 1.0.0) |
| **Embeddings** | `gemini-embedding-001` (768-dim), `google.genai.Client` (NOT `google.generativeai`) |
| **Agent Framework** | Google ADK — `LlmAgent` + `Runner` + `DynamoDBSessionService` |
| **Memory** | mem0ai ≥ 0.1.55 (long-term, per user) |
| **Vector DB** | Qdrant self-hosted — collections: `rag_documents`, `mem0_memories`, `meetings` |
| **Session DB** | AWS DynamoDB (prod) / `amazon/dynamodb-local` port 8001 (local) |
| **STT** | Soniox external API — WebSocket, `websockets.asyncio.client` v14+ |
| **Backend** | FastAPI 0.115+, Uvicorn, Python ≥ 3.11, `uv` package manager |
| **Logging** | structlog (structured JSON logs) |
| **Storage** | S3 (`chatbotdeploytestv1`) hoặc local `./uploads` |
| **Frontend** | React 18.3.1, Vite 5, TypeScript 5.5, TailwindCSS 3, React Query v5, Zustand 5, Axios 1.7 |
| **Audio** | AudioWorklet (inline blob) → 16kHz PCM16 mono → `POST /api/v1/transcription/audio/{id}` |
| **Infra** | EC2 t3.small, ECS (sidecar: backend + qdrant), ECR, S3, CloudFront, DynamoDB, SSM, CloudWatch |
| **CI/CD** | GitHub Actions — 2 workflows độc lập (backend: lint→test→ECR→ECS; frontend: build→S3→CF) |

---

## 4. Kiến trúc hệ thống

```
Người dùng (React SPA tại CloudFront)
       │ HTTPS (same-origin, không cần CORS)
       ▼
CloudFront ──/api/*──► EC2:8000 (FastAPI + Uvicorn)
           ──/*──────► S3 (React build)
                              │
                    ┌─────────┴────────────────────────────┐
                    │         FastAPI App                    │
                    │                                        │
                    │  ┌────────────────────────────────┐   │
                    │  │  Google ADK Runner (singleton)  │   │
                    │  │  ├── LlmAgent (Gemini 2.5 Flash)│   │
                    │  │  │   ├── ContextFilterPlugin    │   │
                    │  │  │   ├── search_documents       │   │
                    │  │  │   ├── search_meeting_transcripts│  │
                    │  │  │   ├── list_user_documents    │   │
                    │  │  │   ├── list_meetings          │   │
                    │  │  │   ├── retrieve_memories      │   │
                    │  │  │   └── store_memory           │   │
                    │  │  └── DynamoDBSessionService      │   │
                    │  └────────────────────────────────┘   │
                    │                                        │
                    │  Services: RAGService, MemoryService,  │
                    │  DocumentService, SonioxService,       │
                    │  TranscriptRAGService                  │
                    │                                        │
                    │  Repositories: QdrantRepository,       │
                    │  Mem0Repository, MeetingRepository     │
                    └────────────┬──────────────────────────┘
                                 │
              ┌──────────────────┼──────────────────────┐
              │                  │                        │
              ▼                  ▼                        ▼
         Qdrant :6333       DynamoDB               Soniox API
    (rag_documents,      (memrag_sessions,      (external WebSocket
     mem0_memories,       memrag-meetings)        STT realtime)
     meetings)
```

**Luồng chat:**
1. `POST /chat/stream` → `ChatService.chat_stream()` → `runner.run_async(RunConfig(SSE))` → `ContextFilterPlugin` (truncate/summarize) → LLM → stream `event.partial` → SSE chunks.
2. Mỗi turn ADK `append_event` → `DynamoDBSessionService` persist (title auto-extract từ first message).

**Luồng transcription:**
1. `POST /transcription/start` → `SonioxService.start_session()` → mở WS Soniox + background receiver task.
2. Frontend AudioWorklet (16kHz PCM16) → `POST /transcription/audio/{id}` mỗi 500ms (max 2 concurrent).
3. `GET /transcription/stream/{id}` SSE → nhận `partial`/`final` events.
4. `POST /transcription/stop/{id}` → lưu utterances DynamoDB + embed → Qdrant `meetings`.

---

## 5. API Endpoints

### Chat
| Method | Path | Mô tả |
|--------|------|-------|
| POST | `/api/v1/chat` | Chat đồng bộ (text + ảnh optional) |
| POST | `/api/v1/chat/stream` | Chat streaming SSE |

### Documents (RAG)
| Method | Path | Mô tả |
|--------|------|-------|
| POST | `/api/v1/documents/upload` | Upload PDF (max theo `MAX_UPLOAD_SIZE_MB`) |
| GET | `/api/v1/documents` | List tài liệu của user |
| DELETE | `/api/v1/documents/{id}` | Xóa tài liệu + Qdrant chunks |

### Memory
| Method | Path | Mô tả |
|--------|------|-------|
| POST | `/api/v1/memory/search` | Tìm kiếm long-term memory |
| GET | `/api/v1/memory/user/{user_id}` | Lấy tất cả memories của user |
| DELETE | `/api/v1/memory/{id}` | Xóa một memory |

### Sessions
| Method | Path | Mô tả |
|--------|------|-------|
| GET | `/api/v1/sessions` | List sessions của user (từ DynamoDB) |
| GET | `/api/v1/sessions/{id}` | Load toàn bộ messages của session |
| DELETE | `/api/v1/sessions/{id}` | Xóa session |

### Transcription
| Method | Path | Mô tả |
|--------|------|-------|
| POST | `/api/v1/transcription/start` | Bắt đầu Soniox session, trả `meeting_id` |
| POST | `/api/v1/transcription/audio/{id}` | Gửi binary PCM16 chunk (204 No Content) |
| GET | `/api/v1/transcription/stream/{id}` | SSE stream `partial`/`final`/`end`/`error` |
| POST | `/api/v1/transcription/stop/{id}` | Dừng, lưu DynamoDB + ingest Qdrant |

### Meetings
| Method | Path | Mô tả |
|--------|------|-------|
| GET | `/api/v1/meetings` | List meetings của user |
| GET | `/api/v1/meetings/{id}/transcript` | Full transcript của meeting |
| DELETE | `/api/v1/meetings/{id}` | Xóa meeting (DynamoDB + Qdrant) |

### Wiki
| Method | Path | Mô tả |
|--------|------|-------|
| GET | `/api/v1/wiki/graph` | Lấy nodes + edges cho knowledge graph (React Flow) |
| GET | `/api/v1/wiki/pages/{category}/{slug}` | Đọc nội dung Markdown của một wiki page |

---

## 6. Cấu trúc thư mục

```
proj2/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── root_agent.py           # LlmAgent definition
│   │   │   ├── plugins/
│   │   │   │   └── context_filter_plugin.py  # async before_model_callback
│   │   │   └── tools/
│   │   │       ├── qdrant_search_tool.py
│   │   │       ├── pdf_ingestion_tool.py
│   │   │       ├── files_retrieval_tool.py
│   │   │       ├── mem0_tools.py
│   │   │       └── search_meeting_transcripts.py  # search Soniox transcripts
│   │   ├── api/v1/
│   │   │   ├── chat.py
│   │   │   ├── documents.py
│   │   │   ├── memory.py
│   │   │   ├── sessions.py
│   │   │   └── transcription.py        # transcription + meetings routers
│   │   ├── core/
│   │   │   ├── config.py               # Pydantic Settings (env vars)
│   │   │   ├── database.py             # lru_cache clients (Qdrant, mem0, DynamoDB)
│   │   │   ├── dependencies.py         # FastAPI DI graph + get_runner() singleton
│   │   │   └── logging.py              # structlog setup
│   │   ├── repositories/
│   │   │   ├── qdrant_repo.py
│   │   │   ├── mem0_repo.py
│   │   │   └── meeting_repo.py         # DynamoDB meetings CRUD
│   │   ├── services/
│   │   │   ├── chat_service.py
│   │   │   ├── rag_service.py
│   │   │   ├── memory_service.py
│   │   │   ├── document_service.py
│   │   │   ├── dynamo_session_service.py  # ADK BaseSessionService impl
│   │   │   ├── soniox_service.py          # WebSocket manager (_sessions dict)
│   │   │   └── transcript_rag_service.py  # embed + ingest transcript → Qdrant
│   │   ├── schemas/
│   │   │   ├── chat.py
│   │   │   ├── document.py
│   │   │   ├── memory.py
│   │   │   └── transcription.py
│   │   ├── exceptions/
│   │   │   └── handlers.py             # ValueError→400, FileNotFoundError→404, Exception→500
│   │   ├── utils/
│   │   │   └── gemini_utils.py         # batch embed, google.genai.Client
│   │   ├── storage/
│   │   │   └── __init__.py             # StorageBackend: local | s3
│   │   └── main.py                     # FastAPI app + lifespan
│   ├── tests/
│   ├── pyproject.toml                  # uv, ruff, pytest config
│   ├── uv.lock
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   ├── client.ts               # axios instance (relative URLs)
│   │   │   ├── chat.ts
│   │   │   ├── documents.ts
│   │   │   ├── memory.ts
│   │   │   ├── sessions.ts
│   │   │   └── transcription.ts
│   │   ├── components/
│   │   │   ├── chat/                   # ChatPanel, MessageList, InputBar
│   │   │   ├── documents/              # DocumentPanel
│   │   │   ├── memory/                 # MemoryPanel
│   │   │   └── transcription/          # TranscriptionPanel (Mic icon toggle)
│   │   ├── hooks/
│   │   │   └── useTranscription.ts     # audio capture + Soniox flow
│   │   ├── services/
│   │   │   └── AudioCaptureService.ts  # AudioWorklet 16kHz PCM16 (mic/system/both)
│   │   ├── store/                      # Zustand state
│   │   └── types/
│   ├── package.json
│   ├── vite.config.ts                  # proxy /api → :8000
│   ├── tailwind.config.js
│   └── eslint.config.js
│
├── docker-compose.yml                  # qdrant + dynamodb-local + backend
├── .env                                # secrets (gitignore này!)
├── .github/workflows/
│   ├── ci-cd.yml                       # backend: lint → test → ECR → ECS
│   └── deploy-frontend.yml             # frontend: build → S3 → CloudFront
├── .claude/
│   ├── settings.json                   # format-on-edit hooks
│   └── skills/                         # lint-fix, verify, verify-fe, docker-reset, check-all, deploy-frontend
├── infrastructure/                     # Terraform (EC2, ECS, ECR, S3, CloudFront, IAM)
├── docs/
│   ├── spec.md                         # (file này)
│   ├── deploy_plan.md
│   ├── cicd-flow.md
│   └── soniox-plan.md
├── CLAUDE.md
└── CLAUDE.local.md
```

---

## 7. Environment Variables quan trọng

| Biến | Bắt buộc | Mô tả |
|------|----------|-------|
| `GEMINI_API_KEY` | ✅ | Google AI Studio API key |
| `GEMINI_MODEL` | - | Default: `gemini-2.5-flash` |
| `GEMINI_EMBEDDING_MODEL` | - | Default: `models/gemini-embedding-001` |
| `QDRANT_URL` | - | Default: `http://localhost:6333`; docker-compose override: `http://qdrant:6333` |
| `DYNAMODB_ENDPOINT_URL` | - | Để trống = real AWS; local: `http://localhost:8001` |
| `DYNAMODB_TABLE_NAME` | - | Default: `memrag_sessions` |
| `DYNAMODB_REGION` | - | Default: `ap-southeast-2` |
| `STORAGE_BACKEND` | - | `local` hoặc `s3` (default: `local`) |
| `S3_BUCKET` | nếu s3 | `chatbotdeploytestv1` |
| `S3_REGION` | nếu s3 | `ap-southeast-2` |
| `ALLOWED_ORIGINS` | - | JSON array: `["http://localhost:5173"]` (không phải comma-separated) |
| `SONIOX_API_KEY` | nếu dùng transcription | Soniox account API key |
| `SONIOX_MODEL` | - | Default: `stt-rt-preview` |
| `SONIOX_TARGET_LANG` | - | Default: `vi` (tiếng Việt) |
| `MAX_CONTEXT_MESSAGES` | - | Default: 20 |
| `SUMMARY_THRESHOLD` | - | Default: 30 (số messages trước khi auto-summarize) |
| `SUMMARY_KEEP_RECENT` | - | Default: 10 (số messages giữ lại sau summarize) |
| `WIKI_ENABLED` | - | Default: true |
| `WIKI_BASE_DIR` | - | Default: `./wiki` |
| `WIKI_CHUNK_SIZE` | - | Default: 16384 |
| `WIKI_MAX_ENTITIES_PER_SOURCE` | - | Default: 20 |
| `WIKI_MAX_TOPICS_PER_SOURCE` | - | Default: 5 |
| `WIKI_MAX_PARALLEL_EXTRACTIONS` | - | Default: 5 |
| `WIKI_MAX_PARALLEL_SYNTHESIS` | - | Default: 5 |
| `JWT_SECRET_KEY` | - | Secret cho JWT signing (HS256). **Phải set trong production**. |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | - | Default: 15 |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | - | Default: 7 |
| `GOOGLE_OAUTH_CLIENT_ID` | - | Google OAuth client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | - | Google OAuth client secret |
| `GOOGLE_OAUTH_REDIRECT_URI` | - | Google OAuth redirect URI |

---

## 8. docker-compose.yml (local dev)

```yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage

  dynamodb-local:
    image: amazon/dynamodb-local:latest
    ports:
      - "8001:8000"
    command: -jar DynamoDBLocal.jar -inMemory -sharedDb

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    depends_on:
      - qdrant
      - dynamodb-local
    env_file: .env
    environment:
      QDRANT_URL: http://qdrant:6333
      DYNAMODB_ENDPOINT_URL: http://dynamodb-local:8000
    volumes:
      - uploads_data:/app/uploads

volumes:
  qdrant_data:
  uploads_data:
```

**Local dev:**
```bash
docker compose up -d       # qdrant + dynamodb-local + backend
cd frontend && npm run dev  # :5173, proxy /api → :8000
```
