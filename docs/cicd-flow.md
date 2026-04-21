# CI/CD Flow — MemRAG Chatbot

## Tổng quan
> Cập nhật lần cuối: 2026-04-21

Dự án có **2 pipeline độc lập**, mỗi pipeline trigger theo thay đổi của phần code tương ứng:

| Workflow | File | Trigger | Mục tiêu |
|----------|------|---------|-----------|
| Backend CI/CD | `ci-cd.yml` | `backend/**` thay đổi | ECR → ECS (EC2) |
| Frontend Deploy | `deploy-frontend.yml` | `frontend/**` thay đổi | S3 → CloudFront |

---

## 1. Backend CI/CD (`ci-cd.yml`)

### Trigger conditions

```yaml
on:
  push:
    branches: [main]
    paths: ["backend/**", "docker-compose.yml", ".github/workflows/ci-cd.yml"]
  pull_request:
    branches: [main]
    paths: ["backend/**", ".github/workflows/ci-cd.yml"]
```

| Event | Hành động |
|-------|-----------|
| Push vào `main` | Toàn bộ pipeline: lint → test → build → deploy |
| Pull Request vào `main` | Chỉ lint + test (không build, không deploy) |
| Thay đổi `frontend/**` | Không trigger (pipeline riêng) |

### Sơ đồ luồng

```
Developer push backend/
        │
        ▼
GitHub Actions triggered
        │
        ├─────────────────────────────┐
        ▼                             ▼
┌───────────────┐           ┌─────────────────┐
│   JOB 1       │           │    JOB 2        │
│   lint        │           │    test         │
│               │           │                 │
│ uv sync       │           │ uv sync         │
│ ruff format   │           │ pytest (--cov)  │
│ ruff check    │           │ upload artifact │
└───────┬───────┘           └────────┬────────┘
        │                            │
        └─────────────┬──────────────┘
                      │  Cả 2 pass mới tiếp tục
                      ▼
             ┌─────────────────┐
             │    JOB 3        │  ← push main only (không chạy PR)
             │   build-push    │
             │                 │
             │ docker build    │
             │ tag: <sha>      │
             │ tag: latest     │
             │ push → ECR      │
             └────────┬────────┘
                      │
                      ▼
             ┌─────────────────┐
             │    JOB 4        │
             │    deploy       │  ← environment: production
             │                 │     (có thể bật approval gate)
             │ describe task   │
             │ inject image    │
             │ register task   │
             │ update service  │
             │ wait stable ✓   │
             └─────────────────┘
```

### Chi tiết từng Job

#### Job 1 — lint

**Môi trường:** Ubuntu runner, `working-directory: backend`

```
1. actions/checkout@v4

2. astral-sh/setup-uv@v5 (enable-cache: true)
   └── Cache .venv giữa các runs

3. uv sync --frozen
   └── Install từ uv.lock, không thay đổi lockfile
   └── pyproject.toml ≠ uv.lock → fail ngay

4. ruff format --check .
   └── --check = chỉ báo lỗi, KHÔNG sửa
   └── Exit 1 nếu có file cần format

5. ruff check .
   └── Import order (I001), unused vars (F841), errors (E)...
   └── Exit 1 nếu có vi phạm
```

#### Job 2 — test

**Chạy song song với Job 1** (tiết kiệm thời gian).

```
1. checkout + setup-uv + uv sync (tương tự Job 1)

2. uv run pytest tests/ -v \
     --cov=app \
     --cov-report=term-missing \
     --cov-report=xml
   └── env: GEMINI_API_KEY=dummy-ci-key
       (conftest.py mock hết clients, không gọi API thật)

3. actions/upload-artifact@v4
   └── Upload coverage.xml (7 ngày)
   └── if: always() → upload kể cả khi test fail
```

**Tại sao không cần API key thật:**
- `conftest.py` dùng `app.dependency_overrides` thay thế tất cả clients
- `mock_runner` fake `runner.run_async` → không gọi Gemini
- `mock_qdrant_client`, `mock_mem0_client` → không kết nối DB

#### Job 3 — build-push

**Điều kiện:** `github.ref == 'refs/heads/main' && github.event_name == 'push'`

```
1. configure-aws-credentials@v4 (từ GitHub Secrets)

2. amazon-ecr-login@v2
   └── aws ecr get-login-password | docker login
   └── Output: REGISTRY = <account>.dkr.ecr.<region>.amazonaws.com

3. docker build ./backend
   └── Tag 1: REGISTRY/memragbackend:<commit-sha>  (immutable)
   └── Tag 2: REGISTRY/memragbackend:latest        (convenience)

4. docker push (cả 2 tags)
   └── Output: image=REGISTRY/memragbackend:<sha>
```

**Tại sao tag theo commit SHA:**
- `latest` có thể bị overwrite → không biết đang chạy version nào
- SHA tag = pinned → rollback chính xác về đúng commit

#### Job 4 — deploy

**Phụ thuộc:** `needs: build-push`
**Environment:** `production` (có thể cấu hình "Required reviewers" để bật approval gate)

```
1. aws ecs describe-task-definition
   └── Download task definition JSON hiện tại từ ECS

2. amazon-ecs-render-task-definition@v1
   └── Thay field "image" của container "backend"
       bằng REGISTRY/memragbackend:<sha>

3. amazon-ecs-deploy-task-definition@v2
   └── Register task definition mới lên ECS
   └── Update service → ECS bắt đầu rolling update:
       Stop task cũ → Pull image mới → Start task mới → Health check
   └── wait-for-service-stability: true
       → Block cho đến khi STABLE, fail nếu unhealthy
```

### Thời gian thực tế

| Job | Thời gian |
|-----|-----------|
| lint | ~1 phút |
| test | ~2 phút |
| build-push | ~3-5 phút |
| deploy | ~2-3 phút |
| **Tổng** | **~6-8 phút** (lint + test song song) |

### Rollback backend

```bash
# Xem lịch sử task definitions
aws ecs list-task-definitions \
  --family-prefix memrag-backend \
  --region ap-southeast-2

# Rollback về version trước
aws ecs update-service \
  --cluster memrag-cluster \
  --service memrag-backend-service \
  --task-definition memrag-backend:<VERSION_CŨ> \
  --region ap-southeast-2
```

---

## 2. Frontend Deploy (`deploy-frontend.yml`)

### Trigger conditions

```yaml
on:
  push:
    branches: [main]
    paths: ["frontend/**", ".github/workflows/deploy-frontend.yml"]
```

Không có PR check — frontend là static build, không có tests riêng (dùng `/verify-fe` locally trước khi push).

### Sơ đồ luồng

```
Developer push frontend/
        │
        ▼
GitHub Actions triggered
        │
        ▼
┌─────────────────────────┐
│   JOB: deploy           │
│                         │
│ npm ci                  │
│ npm run build           │  ← VITE_API_BASE_URL="" (relative URLs)
│                         │
│ aws s3 sync dist/ → S3  │  ← assets: immutable cache
│                         │     index.html: no-cache
│                         │
│ cloudfront invalidate   │  ← Xóa cache cũ tại edge
└─────────────────────────┘
```

### Chi tiết

```
1. actions/setup-node@v4 (Node 20, cache npm)

2. npm ci
   └── Clean install từ package-lock.json

3. npm run build
   └── tsc && vite build → dist/
   └── VITE_API_BASE_URL="" → axios dùng relative URL /api/v1/...
       → Same-origin với CloudFront → không cần CORS

4. aws s3 sync dist/ s3://memrag-frontend-860601623933 --delete
   └── assets/* (JS/CSS có content hash):
       cache-control: public,max-age=31536000,immutable
   └── index.html:
       cache-control: no-cache,no-store,must-revalidate

5. aws cloudfront create-invalidation --paths "/*"
   └── Xóa tất cả cached objects tại 400+ edge locations
   └── User thấy bản mới trong vài giây
```

### Cache strategy

| File | Cache | Lý do |
|------|-------|-------|
| `assets/index-[hash].js` | 1 năm (immutable) | Hash thay đổi khi content thay đổi → safe |
| `assets/[vendor]-[hash].js` | 1 năm (immutable) | Tương tự |
| `index.html` | no-cache | Entry point, phải lấy bản mới nhất |

### Thời gian thực tế

| Bước | Thời gian |
|------|-----------|
| npm ci + build | ~1-2 phút |
| s3 sync | ~30 giây |
| CF invalidation | ~30 giây (propagate ~5 phút) |
| **Tổng** | **~2-3 phút** |

---

## GitHub Secrets

| Secret | Dùng bởi | Giá trị / Nguồn |
|--------|----------|-----------------|
| `AWS_ACCESS_KEY_ID` | cả 2 | `terraform output github_actions_access_key_id` |
| `AWS_SECRET_ACCESS_KEY` | cả 2 | `terraform output github_actions_secret_access_key` |
| `FRONTEND_S3_BUCKET` | deploy-frontend | `memrag-frontend-860601623933` |
| `CLOUDFRONT_DISTRIBUTION_ID` | deploy-frontend | `E17D2MVQHE58HY` |

## IAM Permissions (github-actions user)

```
ECR:
├── ecr:GetAuthorizationToken        → login
└── ecr:BatchCheck / PutImage / ...  → push image

ECS:
├── ecs:DescribeTaskDefinition       → đọc task def hiện tại
├── ecs:RegisterTaskDefinition       → đăng ký task def mới
├── ecs:UpdateService / Describe     → trigger deploy
└── iam:PassRole                     → truyền execution role

S3 (frontend bucket):
├── s3:PutObject                     → upload files
├── s3:DeleteObject                  → --delete cũ
└── s3:ListBucket                    → sync diff

CloudFront:
└── cloudfront:CreateInvalidation    → xóa edge cache
```

**Nguyên tắc Least Privilege:** Nếu bị compromise, attacker chỉ deploy được — không đọc SSM secrets, không xóa resources, không tạo EC2.

---

## Sơ đồ tổng thể Developer → Production

```
[Local Machine]
      │
      │ git push origin main
      ▼
[GitHub]
      │
      ├── backend/** thay đổi?
      │   └── CI/CD Backend:
      │       lint → test → build image → push ECR → deploy ECS
      │                                                    │
      │                                               [AWS ECS - EC2 13.211.227.6]
      │                                                    │
      │                                               FastAPI :8000
      │                                                    ↑
      └── frontend/** thay đổi?                           │
          └── Deploy Frontend:                   [CloudFront /api/*]
              build → s3 sync → CF invalidate         proxy
                          │                            │
                    [S3 Bucket]                        │
                          │                            │
                    [CloudFront /*] ──────── User: https://d3qrt08bgfyl3d.cloudfront.net
```
