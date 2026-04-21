<div align="center">

# 🤖 MemRAG Chatbot

**Multimodal AI Research Assistant** được xây dựng trên **Google Agent Development Kit (ADK)**

Kết hợp RAG · Bộ nhớ dài hạn · Transcription thời gian thực · Wiki Knowledge Graph

[![Live Demo](https://img.shields.io/badge/🌐_Live_Demo-d3qrt08bgfyl3d.cloudfront.net-blue?style=for-the-badge)](https://d3qrt08bgfyl3d.cloudfront.net)

---

### 🛠 Tech Stack

![Python](https://img.shields.io/badge/Python_3.11-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![Google Gemini](https://img.shields.io/badge/Gemini_2.5_Flash-4285F4?style=flat-square&logo=google&logoColor=white)
![React](https://img.shields.io/badge/React_18-61DAFB?style=flat-square&logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&logo=typescript&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-646CFF?style=flat-square&logo=vite&logoColor=white)
![TailwindCSS](https://img.shields.io/badge/Tailwind_CSS-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white)

![AWS](https://img.shields.io/badge/AWS-232F3E?style=flat-square&logo=amazonaws&logoColor=white)
![ECS](https://img.shields.io/badge/ECS_Fargate-FF9900?style=flat-square&logo=amazonaws&logoColor=white)
![S3](https://img.shields.io/badge/S3-569A31?style=flat-square&logo=amazons3&logoColor=white)
![DynamoDB](https://img.shields.io/badge/DynamoDB-4053D6?style=flat-square&logo=amazondynamodb&logoColor=white)
![RDS](https://img.shields.io/badge/RDS_PostgreSQL-336791?style=flat-square&logo=postgresql&logoColor=white)
![ElastiCache](https://img.shields.io/badge/ElastiCache_Redis-DC382D?style=flat-square&logo=redis&logoColor=white)
![CloudFront](https://img.shields.io/badge/CloudFront-FF9900?style=flat-square&logo=amazonaws&logoColor=white)

![Qdrant](https://img.shields.io/badge/Qdrant-FF4081?style=flat-square&logo=qdrant&logoColor=white)
![Terraform](https://img.shields.io/badge/Terraform-7B42BC?style=flat-square&logo=terraform&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=flat-square&logo=githubactions&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)

</div>

---

## ✨ Tính năng nổi bật

| Tính năng | Mô tả |
|-----------|-------|
| 🚀 **Realtime Chat Streaming** | SSE token-by-token, phản hồi tức thì |
| 📄 **Multimodal PDF RAG** | Upload PDF → chunk → embed → semantic search với trích dẫn |
| 🧠 **Long-term Memory** | Tích hợp **mem0** ghi nhớ thông tin cá nhân xuyên phiên |
| 🎙️ **Realtime Transcription** | Soniox STT, 60+ ngôn ngữ, tự lưu transcript → RAG |
| 🌐 **Wiki Knowledge Graph** | Tự tổng hợp từ tài liệu + meetings, visualize bằng React Flow |
| ⚡ **Redis Caching** | ElastiCache cache wiki/graph/session/docs — giảm latency |
| 🔐 **Auth** | JWT + Google OAuth2, refresh token rotation, CSRF protection |
| 🏗️ **IaC** | Toàn bộ hạ tầng AWS quản lý bằng Terraform |

---

## 🏛️ Kiến trúc hệ thống

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        USER (Browser)                                    │
│              https://d3qrt08bgfyl3d.cloudfront.net                       │
└────────────────────────────┬────────────────────────────────────────────┘
                             │ HTTPS
              ┌──────────────▼──────────────┐
              │         CloudFront           │
              │   /api/* → ALB (proxy)       │
              │   /*     → S3 Frontend       │
              └───────┬──────────┬──────────┘
                      │          │
          ┌───────────▼──┐  ┌────▼────────────────────────┐
          │  S3 Bucket   │  │  Application Load Balancer   │
          │  (React SPA) │  │  memrag-backend-alb-*.elb    │
          └──────────────┘  └────────────┬────────────────┘
                                         │
              ┌──────────────────────────▼──────────────────────────┐
              │              ECS EC2 — FastAPI Backend               │
              │                   Port 8000                          │
              │                                                      │
              │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
              │  │ Chat API │  │ Docs API │  │ Wiki / Auth API  │  │
              │  │  (SSE)   │  │ (upload) │  │ Transcription WS │  │
              │  └────┬─────┘  └────┬─────┘  └────────┬─────────┘  │
              │       │             │                  │            │
              │  ┌────▼─────────────▼──────────────────▼──────────┐ │
              │  │      Google ADK Agent (Gemini 2.5-flash)        │ │
              │  │           9 Tools + ContextFilterPlugin         │ │
              │  └────┬────┬────┬────┬────┬────┬───────────────────┘ │
              │       │    │    │    │    │    │                     │
              └───────┼────┼────┼────┼────┼────┼─────────────────────┘
                      │    │    │    │    │    │
          ┌───────────▼┐ ┌─▼──┐ │ ┌─▼──┐ │ ┌─▼──────┐
          │  ElastiCache│ │mem0│ │ │Wiki│ │ │DynamoDB│
          │  Redis Cache│ │    │ │ │S3  │ │ │Sessions│
          └─────────────┘ └────┘ │ └────┘ │ └────────┘
                              ┌──▼──┐  ┌──▼────┐
                              │     │  │  RDS  │
                              │Qdrant  │Postgres│
                              │(RAG)│  │(Auth) │
                              └─────┘  └───────┘
```

---

## 🔄 Data Flow

### 💬 Chat Flow
```
User nhắn tin
    └─► POST /api/v1/chat/stream (SSE)
            └─► ChatService._ensure_session() [DynamoDB]
                    └─► ContextFilterPlugin (tóm tắt nếu > 22 msgs)
                            └─► ADK Runner → Gemini 2.5-flash
                                    ├─► read_wiki_index / read_wiki_page
                                    ├─► search_documents (RAG — Qdrant)
                                    ├─► retrieve_memories (mem0)
                                    └─► ─── SSE stream tokens ──► Browser
```

### 📄 Upload PDF Flow
```
Upload PDF
    └─► POST /api/v1/documents/upload
            ├─► extract text → StorageBackend.save() [S3]
            ├─► RAGService: chunk → embed → Qdrant upsert
            ├─► Cache.delete("docs:{user_id}:list")
            └─► [background] WikiService 4-phase pipeline
                    ├─► Phase 1 MAP:    extract entities/topics (parallel)
                    ├─► Phase 2 REDUCE: merge + deduplicate by slug
                    ├─► Phase 3 SYNTH:  LLM synthesize per page → S3
                    └─► Phase 4 FINAL:  rebuild index + link_index
```

### 🎙️ Transcription Flow
```
Start meeting → POST /transcription/start [DynamoDB]
    │
Audio stream → WS /transcription/audio/{meeting_id}
    └─► SonioxService → Soniox STT → utterances → DynamoDB
    │
Stop meeting → POST /transcription/stop
    ├─► TranscriptRAGService.ingest() [Qdrant]
    └─► [background] WikiService.update_wiki_from_transcript()
```

### ⚡ Cache Strategy
```
Request đến API
    │
    ├─► Cache.get(key) ──► HIT  ──► Return cached data (< 1ms)
    │
    └─► MISS ──► Tính toán / DB query
                    └─► Cache.set(key, data, ttl)
                            └─► Return data

TTL: wiki_page=10min | wiki_graph=2min | sessions=1min | docs=1min | user=5min
```

---

## 🚀 Quickstart — Local Dev

### Yêu cầu
- Docker & Docker Compose
- Node.js 20+
- Python 3.11+ với [uv](https://docs.astral.sh/uv/)
- Google Gemini API Key

### 1. Clone & cấu hình
```bash
git clone https://github.com/minh2004pd/chatbotfullpipeline.git
cd chatbotfullpipeline

# Tạo file .env từ example
cp .env.example .env
# → Điền GEMINI_API_KEY và các biến cần thiết
```

### 2. Khởi động services
```bash
# Chạy toàn bộ: Redis, Qdrant, DynamoDB Local, Postgres, Backend
docker compose up -d

# Kiểm tra logs backend
docker logs -f memrag-backend
```

### 3. Chạy Frontend
```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

### 4. API Docs
| URL | Mô tả |
|-----|-------|
| http://localhost:8000/docs | Swagger UI |
| http://localhost:6333/dashboard | Qdrant Dashboard |
| http://localhost:8001 | DynamoDB Local |

---

## 🧪 Testing

```bash
# Chạy toàn bộ test suite
cd backend && uv run pytest

# Với coverage report
uv run pytest --cov=app --cov-report=term-missing

# Chạy test cụ thể
uv run pytest tests/services/test_wiki_service.py -v
```

**Test coverage:**
| Module | Test file |
|--------|-----------|
| Wiki pipeline | `tests/services/test_wiki_service.py` |
| Auth + JWT | `tests/core/test_auth.py` |
| Session CRUD | `tests/services/test_dynamo_session_service.py` |
| Cache Service | `tests/core/test_cache_service.py` |
| RAG Service | `tests/services/test_rag_service.py` |

---

## 🔁 CI/CD Pipeline

```
git push origin main
        │
        ├── backend/** thay đổi?
        │       │
        │   ┌───▼──────────────┐   ┌──────────────────┐
        │   │   JOB: lint      │   │   JOB: test      │  ← chạy song song
        │   │  ruff format     │   │ pytest + coverage │
        │   │  ruff check      │   │ upload artifact   │
        │   └───────┬──────────┘   └────────┬─────────┘
        │           └──────────┬────────────┘
        │                      │ cả 2 pass
        │            ┌─────────▼──────────┐
        │            │  JOB: build-push   │  ← push main only
        │            │  docker build      │
        │            │  tag: <sha>+latest │
        │            │  push → ECR        │
        │            └─────────┬──────────┘
        │                      │
        │            ┌─────────▼──────────┐
        │            │   JOB: deploy      │  ← environment: production
        │            │  ECS rolling update│
        │            │  wait stable ✓     │
        │            └────────────────────┘
        │
        └── frontend/** thay đổi?
                │
            ┌───▼──────────────────────┐
            │  JOB: validate           │
            │  tsc --noEmit + eslint   │
            └───────────┬──────────────┘
                        │
            ┌───────────▼──────────────┐
            │  JOB: deploy             │
            │  npm build               │
            │  s3 sync (immutable)     │
            │  CloudFront invalidate   │
            └──────────────────────────┘
```

---

## ☁️ Infrastructure (AWS)

```
AWS ap-southeast-2
├── VPC (10.0.0.0/16)
│   ├── Public Subnets  → ALB, NAT Gateway
│   └── Private Subnets → ECS EC2, RDS, ElastiCache
│
├── ECS Cluster (EC2 launch type)
│   └── Backend Task (FastAPI :8000)
│
├── Qdrant (ECS Fargate + EFS volume)
│
├── ALB → ECS Backend (port 8000)
├── CloudFront → S3 (frontend) + ALB (/api/*)
│
├── RDS PostgreSQL (db.t3.micro) — Auth
├── DynamoDB — Sessions + Meetings
├── ElastiCache Redis (cache.t3.micro) — Caching
├── S3 — Uploads + Wiki pages
└── ECR — Docker images
```

**Triển khai:**
```bash
cd infrastructure

terraform init
terraform plan    # kiểm tra trước
terraform apply   # tạo hạ tầng (~10-15 phút)
terraform output  # xem endpoints
```

**Outputs quan trọng:**
| Output | Giá trị |
|--------|---------|
| `cloudfront_url` | URL frontend public |
| `alb_dns_name` | Backend ALB endpoint |
| `redis_primary_endpoint` | ElastiCache Redis |
| `rds_endpoint` | PostgreSQL host |

---

## 📁 Cấu trúc dự án

```
.
├── backend/                  # FastAPI + Google ADK
│   ├── app/
│   │   ├── agents/           # ADK Agent + 9 Tools
│   │   ├── api/v1/           # REST endpoints
│   │   ├── core/             # Config, Cache, DB, DI
│   │   ├── repositories/     # Data access layer
│   │   ├── services/         # Business logic
│   │   └── schemas/          # Pydantic models
│   ├── tests/                # pytest (~40 test files)
│   ├── Dockerfile
│   └── pyproject.toml
│
├── frontend/                 # React 18 + Vite + TypeScript
│   └── src/
│       ├── api/              # Axios clients
│       ├── components/       # UI components
│       ├── hooks/            # React Query hooks
│       ├── store/            # Zustand state
│       └── types/            # TypeScript types
│
├── infrastructure/           # Terraform (AWS)
│   ├── ecs.tf                # ECS cluster + task def
│   ├── rds.tf                # PostgreSQL
│   ├── elasticache.tf        # Redis
│   ├── dynamodb.tf           # Sessions + Meetings
│   ├── s3_frontend.tf        # Frontend hosting
│   ├── alb.tf                # Load balancer
│   └── variables.tf          # Input variables
│
├── docs/                     # Documentation
│   ├── codebase.md           # Kiến trúc chi tiết
│   ├── spec.md               # Product specification
│   ├── wiki.md               # Wiki system design
│   └── cicd-flow.md          # CI/CD flow
│
├── .github/workflows/
│   ├── ci-cd.yml             # Backend CI/CD
│   └── deploy-frontend.yml   # Frontend deploy
│
└── docker-compose.yml        # Local dev stack
```

---

## 🛠️ Development Rules

Để đảm bảo chất lượng và deploy mượt mà:

1. **🧪 Chạy full test suite** trước khi hoàn thành bất kỳ task nào:
   ```bash
   cd backend && uv run pytest
   ```
2. **📝 Bổ sung test case** cho mọi tính năng mới (unit + integration).
3. **📚 Cập nhật docs** — `docs/`, `CLAUDE.md`, `README.md` khi thay đổi kiến trúc.
4. **🎨 Format code** trước khi commit:
   ```bash
   cd backend && uv run ruff format .
   ```

---

## 🌐 Environment Variables

| Biến | Bắt buộc | Mô tả |
|------|----------|-------|
| `GEMINI_API_KEY` | ✅ | Google Gemini API key |
| `JWT_SECRET_KEY` | ✅ (prod) | JWT signing secret (32+ chars) |
| `STORAGE_BACKEND` | — | `local` hoặc `s3` (default: `local`) |
| `S3_BUCKET` | ✅ (nếu S3) | Tên S3 bucket |
| `S3_ACCESS_KEY_ID` | ✅ (nếu S3) | AWS Access Key |
| `S3_SECRET_ACCESS_KEY` | ✅ (nếu S3) | AWS Secret Key |
| `QDRANT_URL` | — | Qdrant server URL |
| `REDIS_URL` | — | Redis connection URL |
| `REDIS_ENABLED` | — | Bật/tắt cache (default: `true`) |
| `DATABASE_URL` | — | PostgreSQL connection string |
| `SONIOX_API_KEY` | — | Soniox STT API key |
| `WIKI_ENABLED` | — | Bật/tắt wiki pipeline (default: `true`) |
| `DEBUG` | — | Dev mode — bỏ qua JWT (`true`/`false`) |

---

## 📄 License

MIT © 2026 minh2004pd
