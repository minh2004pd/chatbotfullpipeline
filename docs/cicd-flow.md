# CI/CD Flow — MemRAG Chatbot

## Tổng quan

Pipeline được định nghĩa trong `.github/workflows/ci-cd.yml`, tự động chạy mỗi khi có thay đổi trong thư mục `backend/` hoặc workflow files.

---

## Trigger conditions

```yaml
on:
  push:
    branches: [main]
    paths: ["backend/**", ".github/workflows/**"]
  pull_request:
    branches: [main]
    paths: ["backend/**", ".github/workflows/**"]
```

| Event | Hành động |
|-------|-----------|
| Push vào `main` | Chạy toàn bộ pipeline: lint → test → build → deploy |
| Tạo Pull Request vào `main` | Chỉ chạy lint + test (không deploy) |
| Push vào branch khác | Không trigger (do `paths` filter) |
| Thay đổi file ngoài `backend/` | Không trigger (tiết kiệm CI minutes) |

---

## Sơ đồ luồng

```
Developer push code
        │
        ▼
GitHub Actions triggered
        │
        ├──────────────────────────────────────┐
        ▼                                      ▼
┌───────────────┐                    ┌─────────────────┐
│   JOB 1       │                    │    JOB 2        │
│   lint        │                    │    test         │
│               │                    │                 │
│ uv sync       │                    │ uv sync         │
│ ruff format   │                    │ pytest (43 tests│
│ ruff check    │                    │ + coverage XML) │
└───────┬───────┘                    └────────┬────────┘
        │                                     │
        └──────────────┬──────────────────────┘
                       │ Cả 2 pass mới tiếp tục
                       │ (nếu 1 fail → dừng)
                       ▼
              ┌─────────────────┐
              │    JOB 3        │  ← Chỉ chạy khi push vào main
              │   build-push    │     (không chạy khi PR)
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
              │    deploy       │
              │                 │
              │ describe task   │
              │ definition cũ   │
              │ inject image    │
              │ mới vào JSON    │
              │ register task   │
              │ def mới lên ECS │
              │ update service  │
              │ wait stable ✓   │
              └─────────────────┘
```

---

## Chi tiết từng Job

### Job 1 — lint

**Mục đích:** Đảm bảo code format đúng chuẩn trước khi merge.

**Môi trường:** Ubuntu runner, `working-directory: backend`

**Các bước:**
```
1. actions/checkout@v4
   └── Clone repo về runner

2. astral-sh/setup-uv@v5 (enable-cache: true)
   └── Cài uv package manager
   └── Cache .venv để lần sau không install lại

3. uv sync --frozen
   └── Install deps từ uv.lock (--frozen = không thay đổi lockfile)
   └── Nếu pyproject.toml và uv.lock không đồng bộ → fail luôn

4. ruff format --check .
   └── Kiểm tra formatting (quotes, indentation, line length...)
   └── --check = chỉ báo lỗi, KHÔNG sửa file
   └── Exit code 1 nếu có file cần format

5. ruff check .
   └── Kiểm tra linting: import order (I001), unused vars (F841)...
   └── Exit code 1 nếu có lỗi
```

**Fail nhanh:** Nếu `ruff format` fail → không chạy `ruff check` → job fail luôn.

---

### Job 2 — test

**Mục đích:** Chạy toàn bộ test suite, đảm bảo code không break.

**Chạy song song với Job 1** (tiết kiệm thời gian).

**Các bước:**
```
1. checkout + setup-uv + uv sync (tương tự Job 1)

2. uv run pytest tests/ -v \
     --cov=app \
     --cov-report=term-missing \
     --cov-report=xml
   └── env: GEMINI_API_KEY=dummy-ci-key
       (Settings cần key nhưng tests mock hết, không gọi API thật)
   └── -v: verbose output
   └── --cov=app: đo coverage thư mục app/
   └── --cov-report=xml: tạo coverage.xml

3. actions/upload-artifact@v4
   └── Upload coverage.xml lên GitHub Artifacts
   └── Giữ 7 ngày
   └── if: always() = upload kể cả khi test fail (để debug)
```

**Tại sao mock không cần API key thật:**
- `conftest.py` dùng `app.dependency_overrides` thay thế tất cả clients
- `mock_runner` fake `runner.run_async` → không gọi Gemini
- `mock_qdrant_client` → không kết nối Qdrant
- `mock_mem0_client` → không kết nối mem0

---

### Job 3 — build-push

**Mục đích:** Build Docker image và đẩy lên ECR.

**Điều kiện chạy:**
```yaml
if: github.ref == 'refs/heads/main' && github.event_name == 'push'
```
→ Chỉ chạy khi **push vào main**, KHÔNG chạy khi tạo Pull Request.

**Phụ thuộc:** `needs: [lint, test]` — cả 2 job trước phải pass.

**Các bước:**
```
1. checkout

2. aws-actions/configure-aws-credentials@v4
   └── Đọc AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY từ GitHub Secrets
   └── Set env vars cho AWS CLI trong runner

3. aws-actions/amazon-ecr-login@v2
   └── Chạy: aws ecr get-login-password | docker login
   └── Output: REGISTRY = account_id.dkr.ecr.region.amazonaws.com

4. docker build
   └── Context: ./backend (thư mục chứa Dockerfile)
   └── Tag 1: REGISTRY/memragbackend:<commit-sha>
       → Immutable, trace được đến đúng commit
   └── Tag 2: REGISTRY/memragbackend:latest
       → Convenience, luôn trỏ vào version mới nhất

5. docker push (cả 2 tags)
   └── Upload layers lên ECR
   └── Output: image=REGISTRY/memragbackend:<sha>
       → Truyền sang Job 4 qua outputs
```

**Tại sao tag theo commit SHA:**
- `latest` có thể bị overwrite → không biết đang chạy version nào
- SHA tag = pinned → rollback chính xác về đúng commit

---

### Job 4 — deploy

**Mục đích:** Rolling update ECS service với image mới.

**Phụ thuộc:** `needs: build-push`

**Environment:** `environment: production`
→ Nếu cấu hình "Required reviewers" trong GitHub Environment Settings, job sẽ **pause và chờ approval** trước khi deploy.

**Các bước:**
```
1. configure-aws-credentials (tương tự Job 3)

2. aws ecs describe-task-definition
   └── Download task definition JSON hiện tại từ ECS
   └── Lưu vào task-definition.json
   └── File này chứa: container config, env vars, secrets, CPU/memory...

3. aws-actions/amazon-ecs-render-task-definition@v1
   └── Đọc task-definition.json
   └── Thay field "image" của container "backend"
       bằng image mới: REGISTRY/memragbackend:<sha>
   └── Ghi ra file task-definition-new.json

4. aws-actions/amazon-ecs-deploy-task-definition@v2
   └── Register task definition mới lên ECS
       (ECS giữ lịch sử tất cả versions: memrag-backend:1, :2, :3...)
   └── Update service memrag-backend-service dùng task def mới
   └── ECS bắt đầu rolling update:
       - Stop task cũ (gửi SIGTERM, đợi 30s, SIGKILL)
       - Pull image mới từ ECR
       - Start task mới
       - Chờ health check pass
   └── wait-for-service-stability: true
       → Job block cho đến khi service STABLE
       → Nếu task mới unhealthy → deployment fail → alert
```

---

## Thời gian thực tế

| Job | Thời gian trung bình |
|-----|---------------------|
| lint | ~1 phút |
| test | ~2 phút |
| build-push | ~3-5 phút (phụ thuộc image size) |
| deploy | ~2-3 phút (đợi ECS stable) |
| **Tổng** | **~8-10 phút** |

lint và test chạy song song → tổng thời gian = max(lint, test) + build + deploy ≈ **6-8 phút**.

---

## Secrets và bảo mật

```
GitHub Secrets (mã hóa, chỉ GitHub Actions đọc được)
├── AWS_ACCESS_KEY_ID      → IAM user "memrag-github-actions"
└── AWS_SECRET_ACCESS_KEY  → chỉ có quyền ECR push + ECS deploy

IAM user "memrag-github-actions" (tạo bởi Terraform) có quyền:
├── ecr:GetAuthorizationToken       → login ECR
├── ecr:PutImage / InitiateLayerUpload / ... → push image
├── ecs:DescribeTaskDefinition      → đọc task def hiện tại
├── ecs:RegisterTaskDefinition      → đăng ký task def mới
├── ecs:UpdateService               → trigger rolling deploy
└── iam:PassRole                    → truyền execution role cho task def mới
```

**Không có quyền:** Đọc SSM secrets, xóa resources, tạo EC2, v.v.
→ Nếu GitHub Actions bị compromise, attacker chỉ deploy được, không phá được infrastructure.

---

## Rollback

Nếu deploy mới bị lỗi:

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

## Sơ đồ tổng thể Developer → Production

```
[Local Machine]
      │
      │ git push origin main
      ▼
[GitHub]
      │
      ├── Trigger GitHub Actions
      │
      ├── Job: lint (check code quality)
      ├── Job: test (run 43 tests)
      │
      ├── Job: build-push
      │   └── Push image → [AWS ECR]
      │                         │
      └── Job: deploy           │
          └── Update task def ──┘
          └── Rolling update → [AWS ECS]
                                    │
                                    └── Pull image từ ECR
                                    └── Start container mới
                                    └── Health check pass
                                    └── Stop container cũ
                                    └── ✅ Production updated

[AWS ECS - EC2 Instance 13.238.128.124]
      ├── Container: backend (FastAPI :8000)
      ├── Container: qdrant (Vector DB :6333)
      └── Container: ecs-agent (quản lý ECS)
```
