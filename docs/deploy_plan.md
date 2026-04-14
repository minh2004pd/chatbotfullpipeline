# Kiến trúc Cloud — MemRAG Chatbot

> Cập nhật lần cuối: 2026-04-14

## ⚠️ Lưu ý quan trọng về AWS Free Tier

**AWS account đang ở Free Tier plan** — không thể change EC2 instance type khi instance đang chạy.

- Lỗi: `FreeTierRestrictionError: This operation is not available for free plan accounts`
- Nếu cần upgrade EC2 instance type (`t3.small` → `t3.medium`), có 2 cách:
  1. **Upgrade AWS account** lên paid plan (vào AWS Console → Support → Account upgrade)
  2. **Destroy và recreate** EC2 instance mới với instance type mong muốn

**EC2 instance có thể bị stopped** khi Terraform apply thất bại trong quá trình modify instance type.
- Fix: `aws ec2 start-instances --instance-ids <instance-id> --region ap-southeast-2`
- Chờ 2-3 phút cho ECS agent connect trước khi kiểm tra services

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
│                               │ HTTP :8000 (target group, instance) │
│  ┌──────────────────────────  │  ──────────────────────────────┐  │
│  │      EC2 t3.small (EBS gp3 30GB root)                      │  │
│  │      Private subnet AZ-a — memrag-ecs-host-new             │  │
│  │                                                            │  │
│  │  ┌───────────────────────────────────────────────────┐    │  │
│  │  │  ECS Task: backend (host network mode)             │    │  │
│  │  │  Container: FastAPI :8000 (bind to host port)      │    │  │
│  │  │    → qdrant.memrag.local:6333 (Cloud Map DNS)      │    │  │
│  │  │    → AWS DynamoDB                                  │    │  │
│  │  │    → RDS PostgreSQL (memrag-postgres)              │    │  │
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
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  RDS PostgreSQL (db.t3.micro, gp3 20GB, multi-AZ=false) │   │
│  │  memrag-postgres.ch8w22em21x5.ap-southeast-2.rds...     │   │
│  └──────────────────────────────────────────────────────────┘   │
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
- Listener HTTP :80 → forward đến target group `memrag-backend-tg-v2` (type=instance, port=8000)
- Health check: `GET /health` (30s interval, timeout 10s, unhealthy threshold 3, healthy threshold 2, matcher 200)
- SG: chỉ nhận HTTP/HTTPS từ internet (0.0.0.0/0) — CloudFront restriction qua custom header nếu cần
- Deregistration delay: 30s (draining connections khi task bị stop)

**⚠️ Lưu ý:** Target group type là `instance` (không phải `ip`) vì backend dùng `host` network mode.

---

### S3 — Frontend static files

**Bucket:** `memrag-frontend-860601623933`

- Private bucket + OAC (Origin Access Control, SigV4)
- `assets/*` → `max-age=31536000,immutable` (content hash thay đổi theo content)
- `index.html` → `no-cache,no-store` (user thấy deploy mới ngay)

---

### EC2 t3.medium — ECS Host

- 2 vCPU, 4GB RAM (~3.8GB available cho ECS tasks sau khi trừ OS overhead)
- **Root EBS gp3 30GB**: OS + Docker + ECS agent
- **Data EBS gp3 20GB** (`/dev/xvdf`, mount `/qdrant/storage`): Qdrant data persist
- Swap 2GB (file trên root EBS): chống OOM kill
- Đặt ở **private subnet AZ-a** — cùng AZ với Qdrant EBS
- `ECS_ENABLE_TASK_ENI=true` → awsvpc mode support cho Qdrant task

**⚠️ Resource constraints trên t3.medium:**
- Total available: ~2048 CPU units, ~3800MB RAM (sau khi trừ OS ~200MB)
- Qdrant task (awsvpc): 256 CPU, 512MB RAM
- Backend task (host mode): 256 CPU, 512MB RAM (memoryReservation)
- **Max 2-3 backend tasks + 1 Qdrant** trên 1 instance
- Auto scaling max: 3 backend tasks (giới hạn bởi EC2 RAM/CPU)

**⚠️ AWS Free Tier limitation:**
- Không thể change instance type khi instance đang chạy (`FreeTierRestrictionError`)
- Nếu cần upgrade: upgrade AWS account lên paid plan, hoặc destroy & recreate instance
- EC2 có thể bị stopped khi Terraform modify instance type thất bại → cần `aws ec2 start-instances`

---

### ECS — Hai service độc lập

**Backend service** (`memrag-backend-service`):

| Config | Giá trị | Lý do |
|--------|---------|-------|
| `network_mode` | `host` | Dùng chung network namespace với EC2 host, không cần ENI riêng |
| `desiredCount` | `1` | Single instance (có thể scale lên 3 qua auto scaling) |
| `deployment_minimum_healthy_percent` | `0` | Stop old → start new (~30-60s downtime) |
| `deployment_maximum_percent` | `100` | Không chạy song song old + new tasks (tiết kiệm resource) |
| Load balancer | ALB target group (type=instance) | ALB route traffic đến EC2 instance trực tiếp |
| Qdrant URL | `qdrant.memrag.local:6333` | Cloud Map DNS |
| Health check | CMD-SHELL `curl -f http://localhost:8000/health` | Container healthCheck trong task definition |

**⚠️ Quan trọng về `host` network mode:**
- Backend task **không có ENI riêng** — dùng chung network interface của EC2 host
- ALB target group type là `instance` (target = EC2 instance ID, không phải task IP)
- Port 8000 được bind trực tiếp trên EC2 host network namespace
- Không thể chạy 2 backend tasks trên cùng 1 instance (port conflict)

**Qdrant service** (`memrag-qdrant-service`):

| Config | Giá trị | Lý do |
|--------|---------|-------|
| `network_mode` | `awsvpc` | ENI riêng, isolate network |
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
| `/memrag/JWT_SECRET_KEY` | JWT signing secret |
| `/memrag/DB_PASSWORD` | RDS PostgreSQL password |

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
- Min: 1, Max: 3 tasks (t3.medium đủ RAM cho ~3 backend tasks + 1 Qdrant)

**⚠️ Lưu ý:**
- Với `host` network mode, chỉ có thể chạy **1 backend task** trên 1 instance (port conflict)
- Auto scaling chỉ có ý nghĩa khi có **nhiều EC2 instances** (ASG)
- Hiện tại với 1 EC2 instance: auto scaling policy tồn tại nhưng không scale quá 1 task
- Nếu cần scale thực sự: thêm EC2 Auto Scaling Group hoặc migrate sang Fargate

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

**⚠️ Lưu ý:** Qdrant log stream prefix là `qdrant-new` (không phải `qdrant`) — xem trong Terraform state.

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
| Backend `network_mode` | `host` | Dùng chung network với EC2 host, ALB target = instance |
| Qdrant `network_mode` | `awsvpc` | ENI riêng, isolate network |
| ALB target group type | `instance` | Theo backend host network mode |
| ALB target group name | `memrag-backend-tg-v2` | Đã replace từ v1 |
| ALB health check | `/health`, 30s interval, timeout 10s | Healthy: 2, Unhealthy: 3, Matcher: 200 |
| Qdrant health check | Không dùng | `qdrant/qdrant` image không có curl/wget/python |
| Qdrant placement | AZ-a only | EBS bind mount cố định AZ |
| Qdrant CloudWatch log | `qdrant-new/qdrant/<task-id>` | Log stream prefix |
| Cloud Map DNS | `qdrant.memrag.local` | Backend → Qdrant nội bộ VPC |
| `deployment_minimum_healthy_percent` | `0` | Single instance, không đủ resource chạy 2 tasks song song |
| `deployment_maximum_percent` | `100` | Không chạy song song old + new tasks |
| Swap 2GB | file trên root EBS | Chống OOM kill khi traffic đột biến |
| EBS bind mount | `/qdrant/storage` | Qdrant data persist qua container restart |
| CloudFront `/api/*` | `compress=false` | SSE streaming (chat + transcription) không bị buffer |
| `VITE_API_BASE_URL` | `""` (empty) | FE dùng relative URL → same-origin → không cần CORS |
| DynamoDB tables | auto-created | `ensure_dynamo_table()` + `ensure_meetings_table()` khi app startup |
| Embedding model | `gemini-embedding-001` | 768-dim — phải reset Qdrant nếu đổi model |
| Audio chunk size | 8000 samples (500ms) | Tránh 502 CloudFront do quá nhiều concurrent POST |
| ENI trunking | `ECS_ENABLE_TASK_ENI=true` | Nhiều awsvpc tasks trên cùng EC2 |
| Auto Scaling max | `3` | Default trong code (nhưng chỉ có ý nghĩa với ASG) |
| RDS PostgreSQL | `db.t3.micro`, gp3 20GB | Persistent relational DB cho user/auth data |
| SSM secrets | 6 parameters | Gemini, Soniox, S3, JWT, DB password |
| AWS Free Tier | ⚠️ Không thể change instance type | Cần upgrade account hoặc recreate instance |

---

## 🔧 Troubleshooting

### EC2 instance bị stopped sau khi Terraform apply thất bại

**Triệu chứng:**
- ECS services có `runningCount: 0`, `desiredCount: 1`
- Container instance có `agentConnected: false`
- `aws ec2 describe-instances` cho thấy instance state = `stopped`

**Nguyên nhân:** Terraform cố change instance type nhưng thất bại (FreeTierRestrictionError), AWS stop instance.

**Fix:**
```bash
# Start lại EC2 instance
aws ec2 start-instances --instance-ids <instance-id> --region ap-southeast-2

# Chờ 2-3 phút cho ECS agent connect
aws ecs describe-container-instances \
  --cluster memrag-cluster \
  --container-instances <container-arn> \
  --region ap-southeast-2 \
  --query 'containerInstances[0].agentConnected'

# Kiểm tra services đã start tasks chưa
aws ecs describe-services \
  --cluster memrag-cluster \
  --services memrag-qdrant-service memrag-backend-service \
  --region ap-southeast-2 \
  --query 'services[*].{name:name,runningCount:runningCount}'
```

### Backend task không start được (port conflict)

**Triệu chứng:** ECS event log có message `service memrag-backend-service has stopped 1 running tasks` liên tục

**Nguyên nhân:** Với `host` network mode, port 8000 đã bị chiếm (process khác hoặc task cũ chưa cleanup xong).

**Fix:**
```bash
# Kiểm tra process trên port 8000 (qua SSM)
aws ssm send-command \
  --instance-ids <instance-id> \
  --document-name AWS-RunShellScript \
  --parameters 'commands=["ss -tlnp | grep 8000 || echo PORT_FREE"]' \
  --region ap-southeast-2

# Force new deployment
aws ecs update-service \
  --cluster memrag-cluster \
  --service memrag-backend-service \
  --desired-count 0 \
  --force-new-deployment \
  --region ap-southeast-2

sleep 15

aws ecs update-service \
  --cluster memrag-cluster \
  --service memrag-backend-service \
  --desired-count 1 \
  --region ap-southeast-2
```

### Qdrant connection timeout

**Triệu chứng:** Backend log có `qdrant_init_failed error='timed out'`

**Nguyên nhân:** Qdrant service chưa start xong, hoặc Cloud Map DNS chưa resolve được.

**Fix:**
```bash
# Kiểm tra Qdrant service
aws ecs describe-services \
  --cluster memrag-cluster \
  --services memrag-qdrant-service \
  --region ap-southeast-2 \
  --query 'services[0].{runningCount:runningCount,events:events[:2]}'

# Force restart Qdrant service
aws ecs update-service \
  --cluster memrag-cluster \
  --service memrag-qdrant-service \
  --desired-count 0 \
  --region ap-southeast-2

sleep 10

aws ecs update-service \
  --cluster memrag-cluster \
  --service memrag-qdrant-service \
  --desired-count 1 \
  --region ap-southeast-2
```

### ECS service không thể place task (insufficient resources)

**Triệu chứng:** Event log có message `no container instance met all of its requirements... insufficient memory/cpu available`

**Nguyên nhân:** EC2 instance không đủ RAM/CPU cho task mới.

**Fix:**
```bash
# Kiểm tra remaining resources trên container instance
aws ecs describe-container-instances \
  --cluster memrag-cluster \
  --container-instances <container-arn> \
  --region ap-southeast-2 \
  --query 'containerInstances[0].remainingResources[?type==`MEMORY`||type==`CPU`]'

# Kiểm tra running tasks
aws ecs list-tasks --cluster memrag-cluster --region ap-southeast-2

# Với t3.medium (4GB RAM): max ~3 backend tasks + 1 Qdrant
# Nếu cần thêm capacity: thêm EC2 instance hoặc upgrade instance type
```

### Backend startup nhưng Qdrant không available

**Triệu chứng:** Backend log cho thấy Qdrant timeout, nhưng Qdrant task đang RUNNING

**Nguyên nhân:** Qdrant task start sau backend, hoặc Cloud Map DNS chưa propagate.

**Fix:** Restart backend service sau khi Qdrant đã healthy:
```bash
# Kiểm tra Qdrant đã chạy chưa
aws ecs describe-services \
  --cluster memrag-cluster \
  --services memrag-qdrant-service \
  --region ap-southeast-2 \
  --query 'services[0].runningCount'

# Force new deployment cho backend
aws ecs update-service \
  --cluster memrag-cluster \
  --service memrag-backend-service \
  --desired-count 0 \
  --force-new-deployment \
  --region ap-southeast-2

sleep 10

aws ecs update-service \
  --cluster memrag-cluster \
  --service memrag-backend-service \
  --desired-count 1 \
  --region ap-southeast-2
```

### Kiểm tra health qua CloudFront

```bash
# Test API response
curl -s -o /dev/null -w "HTTP %{http_code} - Time: %{time_total}s\n" \
  https://d3qrt08bgfyl3d.cloudfront.net/

# Test health endpoint (nếu có)
curl -s -w "\nHTTP %{http_code}\n" \
  https://d3qrt08bgfyl3d.cloudfront.net/api/v1/health
```

### Xem logs

```bash
# Backend logs (CloudWatch)
aws logs get-log-events \
  --log-group-name "/ecs/memrag" \
  --log-stream-name "backend/backend/<task-id>" \
  --region ap-southeast-2 \
  --limit 50

# Qdrant logs (lưu ý: stream prefix là qdrant-new, không phải qdrant)
aws logs get-log-events \
  --log-group-name "/ecs/memrag" \
  --log-stream-name "qdrant-new/qdrant/<task-id>" \
  --region ap-southeast-2 \
  --limit 50

# ECS service events
aws ecs describe-services \
  --cluster memrag-cluster \
  --services memrag-backend-service \
  --region ap-southeast-2 \
  --query 'services[0].events[:10]' \
  --output table
```
