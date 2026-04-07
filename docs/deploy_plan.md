# Kiến trúc Cloud — MemRAG Chatbot

> Cập nhật lần cuối: 2026-04-07

## Sơ đồ tổng thể

```
Internet
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                          AWS Account                             │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              CloudFront Distribution                      │   │
│  │              https://d3qrt08bgfyl3d.cloudfront.net       │   │
│  │                                                          │   │
│  │   /api/*  ──────────────────────────────────────────┐   │   │
│  │   (Reverse Proxy, no cache, compress=false)          │   │   │
│  │                                                      ▼   │   │
│  │   /*      ──► S3 Bucket (frontend static files)      │   │   │
│  │               memrag-frontend-860601623933           │   │   │
│  └──────────────────────────────────────────────────────┼───┘   │
│                                                         │        │
│                    HTTP :80 (ALB)                       │        │
│  ┌──────────────────────────────────────────────────────▼────┐  │
│  │         Application Load Balancer (internet-facing)        │  │
│  │         memrag-backend-alb (public subnets AZ-a, AZ-b)    │  │
│  └───────────────────────────┬────────────────────────────────┘  │
│                               │ HTTP :8000 (target group, awsvpc) │
│  ┌──────────────────────────  │  ──────────────────────────────┐  │
│  │      EC2 t3.small (EBS gp3 30GB root)                      │  │
│  │      Private subnet AZ-a — memrag-ecs-host-new             │  │
│  │                                                            │  │
│  │  ┌───────────────────────────────────────────────────┐    │  │
│  │  │  ECS Task: backend (awsvpc, private subnet)        │    │  │
│  │  │  Container: FastAPI :8000                          │    │  │
│  │  │    → qdrant.memrag.local:6333 (Cloud Map DNS)      │    │  │
│  │  │    → AWS DynamoDB                                  │    │  │
│  │  │    → S3 (file uploads)                             │    │  │
│  │  │    → Gemini API (LLM+embed)                        │    │  │
│  │  │    → Soniox API (STT WS)                           │    │  │
│  │  └───────────────────────────────────────────────────┘    │  │
│  │                                                            │  │
│  │  ┌───────────────────────────────────────────────────┐    │  │
│  │  │  ECS Task: qdrant (awsvpc, private subnet AZ-a)    │    │  │
│  │  │  Container: qdrant/qdrant:latest :6333             │    │  │
│  │  │    → /qdrant/storage (EBS 20GB gp3 bind mount)     │    │  │
│  │  │  Cloud Map: qdrant.memrag.local → task IP          │    │  │
│  │  └───────────────────────────────────────────────────┘    │  │
│  │  Swap: 2GB (EBS) — chống OOM kill                         │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
│  │   ECR    │  │   SSM    │  │ DynamoDB │  │      S3       │  │
│  │ (images) │  │(secrets) │  │(sessions │  │ uploads/ +    │  │
│  └──────────┘  └──────────┘  │+meetings)│  │ frontend/     │  │
│                               └──────────┘  └───────────────┘  │
│                                                                  │
│  CloudWatch Logs: /ecs/memrag                                   │
│  ├── backend/backend/<task-id>                                   │
│  └── qdrant-new/qdrant/<task-id>                                 │
│                                                                  │
│  External APIs (không containerized):                           │
│  ├── Soniox STT WebSocket (stt.soniox.com) — realtime STT      │
│  └── Google Gemini API — LLM + embeddings                       │
└─────────────────────────────────────────────────────────────────┘
```

**URL duy nhất cho user:** `https://d3qrt08bgfyl3d.cloudfront.net`
- `/*` → React SPA (từ S3)
- `/api/*` → FastAPI backend (qua ALB → ECS backend task)

---

## Từng service và lý do chọn

### CloudFront — Entry point & Reverse Proxy

**Làm gì:** Một distribution duy nhất phục vụ cả Frontend lẫn Backend API.

**2 origin trong cùng 1 distribution:**

| Behavior | Path Pattern | Origin | Cache |
|----------|-------------|--------|-------|
| API proxy | `/api/*` | ALB (HTTP :80) | Disabled |
| Frontend | `/*` (default) | S3 bucket (OAC) | 1 ngày (assets), no-cache (index.html) |

**Tại sao dùng CloudFront làm Reverse Proxy:**
- **Mixed Content**: CloudFront serving HTTPS, browser chỉ thấy 1 domain duy nhất
- **Same-origin**: FE và API cùng domain → không cần CORS
- `compress = false` trên `/api/*` → SSE streaming (chat + transcription) không bị buffer tại edge

**SPA routing:** S3 trả 403/404 khi path không phải file thực → CloudFront map → `index.html` (status 200) → React Router xử lý.

---

### VPC & Networking

**VPC:** `10.0.0.0/16` — memrag-vpc

| Subnet | CIDR | AZ | Dùng cho |
|--------|------|----|----------|
| Public AZ-a | 10.0.1.0/24 | ap-southeast-2a | ALB |
| Public AZ-b | 10.0.2.0/24 | ap-southeast-2b | ALB |
| Private AZ-a | 10.0.10.0/24 | ap-southeast-2a | EC2 host, backend task, qdrant task |
| Private AZ-b | 10.0.11.0/24 | ap-southeast-2b | Backend task (failover) |

- **NAT Gateway** (public AZ-a) → private subnets có outbound internet (ECR pull, Gemini API, Soniox)
- **S3 Gateway Endpoint** + **DynamoDB Gateway Endpoint** → traffic không qua NAT (miễn phí)

---

### Application Load Balancer

- Internet-facing, đặt ở 2 public subnets (AZ-a, AZ-b)
- Listener HTTP :80 → forward đến target group `memrag-backend-tg` (type=ip, port=8000)
- Health check: `GET /health` (30s interval, 3 unhealthy threshold)
- SG: chỉ nhận HTTP/HTTPS từ internet (0.0.0.0/0) — CloudFront restriction qua custom header nếu cần

---

### S3 — Frontend static files

**Bucket:** `memrag-frontend-860601623933`

- Private bucket + OAC (Origin Access Control, SigV4)
- `assets/*` → `max-age=31536000,immutable` (content hash thay đổi theo content)
- `index.html` → `no-cache,no-store` (user thấy deploy mới ngay)

---

### EC2 t3.small — ECS Host

- 2 vCPU, 2GB RAM
- **Root EBS gp3 30GB**: OS + Docker + ECS agent
- **Data EBS gp3 20GB** (`/dev/xvdf`, mount `/qdrant/storage`): Qdrant data persist
- Swap 2GB (file trên root EBS): chống OOM kill
- Đặt ở **private subnet AZ-a** — cùng AZ với Qdrant EBS
- `ECS_ENABLE_TASK_ENI=true` → awsvpc mode support cho nhiều task

---

### ECS — Hai service độc lập

**Backend service** (`memrag-backend-service`):

| Config | Giá trị | Lý do |
|--------|---------|-------|
| `network_mode` | `awsvpc` | Mỗi task có ENI riêng, dễ scale |
| `desiredCount` | `1` | Single instance |
| `deployment_minimum_healthy_percent` | `0` | Stop old → start new (~30-60s downtime) |
| Load balancer | ALB target group | ALB route traffic đến task IP trực tiếp |
| Qdrant URL | `qdrant.memrag.local:6333` | Cloud Map DNS |

**Qdrant service** (`memrag-qdrant-service`):

| Config | Giá trị | Lý do |
|--------|---------|-------|
| `network_mode` | `awsvpc` | ENI riêng |
| `desiredCount` | `1` | Single instance (EBS gắn cố định AZ-a) |
| Placement constraint | AZ-a only | EBS volume ở AZ-a |
| Storage | bind mount `/qdrant/storage` từ EBS | Data persist qua restart |
| Health check | Không dùng container healthCheck | `qdrant/qdrant` image không có curl/wget/python |
| Cloud Map | `qdrant.memrag.local` | Backend resolve qua DNS nội bộ |

---

### Cloud Map — Service Discovery

- Namespace: `memrag.local` (private DNS, gắn với VPC)
- Service: `qdrant` → `qdrant.memrag.local:6333`
- Khi ECS Qdrant task start → tự đăng ký IP vào Cloud Map → backend resolve được ngay

---

### DynamoDB — Session & Meeting Storage

**2 tables:**

| Table | PK | SK | Dữ liệu |
|-------|----|----|---------|
| `memrag_sessions` | `{app_name}#{user_id}` | `session_id` | Chat history, session title, ADK state |
| `memrag-meetings` | `USER#{user_id}` hoặc `MEETING#{id}` | `MEETING#{id}` hoặc `UTTERANCE#{ts}#{seq}` | Meeting metadata + utterances |

- **Production:** AWS DynamoDB — backend dùng IAM task role, không cần credentials
- **Lưu ý:** `float` ↔ `Decimal` conversion bắt buộc. Tables tự tạo khi app startup.

---

### ECR — Container Registry

- Repository: `memragbackend`
- Image tag: commit SHA (immutable) + `latest`
- Lifecycle policy: giữ 10 images gần nhất → rollback 10 commit

---

### SSM Parameter Store — Secrets

| Parameter | Mô tả |
|-----------|-------|
| `/memrag/GEMINI_API_KEY` | Google AI Studio API key |
| `/memrag/SONIOX_API_KEY` | Soniox realtime STT API key |
| `/memrag/S3_ACCESS_KEY_ID` | S3 upload credentials |
| `/memrag/S3_SECRET_ACCESS_KEY` | S3 upload credentials |

---

### S3 — PDF uploads

- Bucket: `chatbotdeploytestv1`
- Presigned URL (expiry 3600s) để download
- Backend stream file thẳng từ S3 khi đọc PDF cho RAG

---

### IAM — Principle of Least Privilege

```
ec2-instance-role         → EC2 join ECS cluster, pull ECR image, read DynamoDB, read/write S3
ecs-task-execution-role   → ECS agent pull image, read SSM secrets, write CloudWatch logs
github-actions-user       → push ECR, deploy ECS, sync S3 frontend, invalidate CloudFront
```

---

### Auto Scaling

- Target tracking: CPU > 60% → scale out backend tasks
- Scale out cooldown: 60s, scale in cooldown: 300s
- Min: 1, Max: 4 tasks (giới hạn bởi EC2 ENI count — t3.small max 3 ENIs)

---

### Soniox — External STT API

- Kết nối qua WebSocket (`websockets.asyncio.client` v14+)
- Backend duy trì module-level `_sessions` dict (singleton per process)
- Cần `SONIOX_API_KEY` trong SSM

---

### CloudWatch Logs

**Log groups:** `/ecs/memrag`
- Stream `backend/backend/<task-id>` — FastAPI logs
- Stream `qdrant-new/qdrant/<task-id>` — Qdrant server logs

---

## CI/CD — 2 workflows độc lập

```
.github/workflows/
├── ci-cd.yml            # Backend: lint → test → build ECR → deploy ECS
│   trigger: push backend/** hoặc ci-cd.yml
│
└── deploy-frontend.yml  # Frontend: npm build → s3 sync → CF invalidate
    trigger: push frontend/** hoặc deploy-frontend.yml
```

### Backend CI/CD (ci-cd.yml)

1. **lint** — `uv run ruff format --check .` + `uv run ruff check .`
2. **test** — `uv run pytest tests/ -v --cov=app` (GEMINI_API_KEY=dummy-ci-key)
3. **build-push** — ECR login → `docker build` → push `$REGISTRY/$ECR_REPOSITORY:$SHA` + `latest`
4. **deploy** — Download task def → render new image → `ecs deploy` với wait-for-stability

### Frontend CI/CD (deploy-frontend.yml)

1. `npm ci` + `npm run build` (`VITE_API_BASE_URL=""`)
2. `aws s3 sync dist/ s3/$FRONTEND_S3_BUCKET` (immutable assets, no-cache index.html)
3. `aws cloudfront create-invalidation --paths "/*"`

### GitHub Secrets cần thiết

| Secret | Dùng bởi | Giá trị |
|--------|----------|---------|
| `AWS_ACCESS_KEY_ID` | cả 2 | từ `terraform output github_actions_access_key_id` |
| `AWS_SECRET_ACCESS_KEY` | cả 2 | từ `terraform output github_actions_secret_access_key` |
| `FRONTEND_S3_BUCKET` | deploy-frontend | `memrag-frontend-860601623933` |
| `CLOUDFRONT_DISTRIBUTION_ID` | deploy-frontend | `E17D2MVQHE58HY` |

---

## Tóm tắt config quan trọng

| Config | Giá trị | Lý do |
|--------|---------|-------|
| `network_mode` | `awsvpc` | Mỗi task có ENI riêng, ALB target type = ip |
| Qdrant health check | Không dùng | `qdrant/qdrant` image không có curl/wget/python |
| Qdrant placement | AZ-a only | EBS bind mount cố định AZ |
| Cloud Map DNS | `qdrant.memrag.local` | Backend → Qdrant nội bộ VPC |
| `deployment_minimum_healthy_percent` | `0` | Single instance, không đủ resource chạy 2 tasks song song |
| Swap 2GB | file trên root EBS | Chống OOM kill khi traffic đột biến |
| EBS bind mount | `/qdrant/storage` | Qdrant data persist qua container restart |
| CloudFront `/api/*` | `compress=false` | SSE streaming (chat + transcription) không bị buffer |
| `VITE_API_BASE_URL` | `""` (empty) | FE dùng relative URL → same-origin → không cần CORS |
| DynamoDB tables | auto-created | `ensure_dynamo_table()` + `ensure_meetings_table()` khi app startup |
| Embedding model | `gemini-embedding-001` | 768-dim — phải reset Qdrant nếu đổi model |
| Audio chunk size | 8000 samples (500ms) | Tránh 502 CloudFront do quá nhiều concurrent POST |
| ENI trunking | `ECS_ENABLE_TASK_ENI=true` | Nhiều awsvpc tasks trên cùng EC2 |
