# MemRAG Chatbot

Multimodal AI chatbot với RAG (Retrieval-Augmented Generation) và long-term memory. Upload PDF, chat với nội dung tài liệu, và AI nhớ ngữ cảnh giữa các cuộc hội thoại.

**Live:** https://d3qrt08bgfyl3d.cloudfront.net

---

## Features

- **Chat streaming** — SSE token-by-token, không phải đợi toàn bộ response
- **PDF RAG** — Upload PDF, AI tìm kiếm ngữ nghĩa trong tài liệu để trả lời
- **Long-term memory** — mem0 ghi nhớ thông tin quan trọng giữa các session
- **Multimodal** — Gửi kèm ảnh trong câu hỏi (Gemini Vision)
- **Multi-session** — Mỗi `(user_id, session_id)` là một cuộc hội thoại độc lập
- **Citations** — Trích dẫn đoạn văn bản nguồn khi trả lời từ PDF

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, TailwindCSS, Zustand, React Query |
| Backend | FastAPI, Python 3.11, Google ADK, Gemini 2.5 Flash |
| AI Memory | mem0 (long-term), ADK InMemorySessionService (short-term) |
| Vector DB | Qdrant (self-hosted, embeddings 768-dim via gemini-embedding-001) |
| File Storage | AWS S3 (PDF uploads + frontend static files) |
| CDN / Proxy | AWS CloudFront (FE serving + API reverse proxy) |
| Infrastructure | AWS ECS (EC2 launch type), Terraform |
| CI/CD | GitHub Actions (2 pipelines: backend + frontend) |

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

`/api/*` được CloudFront proxy về EC2 → FE và BE cùng origin → không cần CORS.

---

## Local Development

### Prerequisites

- Python 3.11+, [`uv`](https://docs.astral.sh/uv/)
- Node.js 20+, npm
- Docker & Docker Compose
- `GEMINI_API_KEY` từ [Google AI Studio](https://aistudio.google.com/)

### Setup

```bash
# Clone
git clone <repo-url>
cd proj2

# Tạo file env
cp backend/.env.example backend/.env
# Điền GEMINI_API_KEY vào .env
```

### Chạy với Docker (recommended)

```bash
# Start tất cả services (Qdrant + Backend)
docker compose up -d

# Xem logs
docker compose logs backend -f

# Rebuild sau khi thay đổi code
docker compose build backend && docker compose up -d
```

Backend: http://localhost:8000 | API docs: http://localhost:8000/docs

### Chạy Backend riêng

```bash
cd backend
uv sync
uv run python -m app.main
```

### Chạy Frontend riêng

```bash
cd frontend
npm ci
npm run dev   # http://localhost:5173
              # Vite proxy: /api → http://localhost:8000
```

---

## Environment Variables

Tạo `backend/.env` (xem `.env.example`):

```env
# Required
GEMINI_API_KEY=your-key-here

# CORS — JSON array format (bắt buộc)
ALLOWED_ORIGINS=["http://localhost:5173"]

# Qdrant (override bởi docker-compose khi chạy Docker)
QDRANT_URL=http://localhost:6333

# Storage: "local" hoặc "s3"
STORAGE_BACKEND=local

# S3 (chỉ cần khi STORAGE_BACKEND=s3)
S3_BUCKET=
S3_REGION=ap-southeast-2
S3_ACCESS_KEY_ID=
S3_SECRET_ACCESS_KEY=
```

---

## API Endpoints

| Method | Path | Mô tả |
|--------|------|-------|
| `POST` | `/api/v1/chat` | Chat (blocking) |
| `POST` | `/api/v1/chat/stream` | Chat (SSE streaming) |
| `POST` | `/api/v1/documents/upload` | Upload PDF |
| `GET` | `/api/v1/documents` | Danh sách tài liệu |
| `DELETE` | `/api/v1/documents/{id}` | Xóa tài liệu |
| `GET` | `/api/v1/memory` | Xem long-term memories |
| `DELETE` | `/api/v1/memory/{id}` | Xóa memory |

**Authentication:** Header `X-User-ID` (mặc định `"default_user"`). Mỗi user có data riêng biệt.

API docs: http://localhost:8000/docs

---

## Testing

```bash
cd backend

# Chạy tất cả tests
uv run pytest tests/ -v

# Với coverage
uv run pytest tests/ --cov=app --cov-report=term-missing

# Test cụ thể
uv run pytest tests/test_chat.py::test_chat_basic -v
```

Tests dùng `app.dependency_overrides` để mock tất cả external clients — không cần API key thật, không cần Qdrant/mem0 đang chạy.

---

## Deployment

Infrastructure được quản lý bằng Terraform (`infrastructure/`), deploy tự động qua GitHub Actions.

### CI/CD Pipelines

| Push to `main` | Pipeline |
|----------------|---------|
| `backend/**` | Lint → Test → Build Docker → Push ECR → Deploy ECS |
| `frontend/**` | npm build → S3 sync → CloudFront invalidate |

Chi tiết: [docs/cicd-flow.md](docs/cicd-flow.md)

### Terraform (lần đầu setup)

```bash
cd infrastructure

# Tạo terraform.tfvars
cat > terraform.tfvars <<EOF
gemini_api_key = "your-key"
soniox_api_key = "your-soniox-api-key"
s3_bucket      = "your-uploads-bucket"
s3_access_key_id     = "..."
s3_secret_access_key = "..."
EOF

terraform init
terraform apply

# Lấy outputs để dán vào GitHub Secrets
terraform output github_actions_access_key_id
terraform output github_actions_secret_access_key
terraform output frontend_bucket_name
terraform output cloudfront_distribution_id
terraform output cloudfront_url
```

### GitHub Secrets cần thiết

| Secret | Nguồn |
|--------|-------|
| `AWS_ACCESS_KEY_ID` | `terraform output github_actions_access_key_id` |
| `AWS_SECRET_ACCESS_KEY` | `terraform output github_actions_secret_access_key` |
| `FRONTEND_S3_BUCKET` | `terraform output frontend_bucket_name` |
| `CLOUDFRONT_DISTRIBUTION_ID` | `terraform output cloudfront_distribution_id` |

### Reset Qdrant data

Thay đổi embedding model/dimension yêu cầu xóa toàn bộ vector data:

```bash
docker compose down -v && docker compose up -d
```

---

## Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── agents/          # Google ADK agent, plugins, tools
│   │   ├── api/v1/          # FastAPI routers
│   │   ├── core/            # Config, database clients, logging
│   │   ├── repositories/    # Qdrant, mem0 data layer
│   │   ├── services/        # Business logic (Chat, RAG, Memory)
│   │   ├── schemas/         # Pydantic models
│   │   └── main.py
│   ├── tests/
│   └── pyproject.toml       # uv, ruff, pytest config
├── frontend/
│   ├── src/
│   │   ├── api/             # axios client, SSE streaming
│   │   ├── components/      # React components
│   │   ├── hooks/           # React Query hooks
│   │   └── store/           # Zustand state
│   └── package.json
├── infrastructure/          # Terraform (AWS)
│   ├── ec2.tf / ecs.tf      # Compute
│   ├── s3_frontend.tf       # CloudFront + S3 frontend
│   ├── iam.tf               # IAM roles & policies
│   └── outputs.tf
├── docs/
│   ├── deploy_plan.md       # Kiến trúc AWS chi tiết
│   └── cicd-flow.md         # CI/CD flow chi tiết
├── docker-compose.yml
└── CLAUDE.md
```

---

## License

MIT
