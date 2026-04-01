# Kiến trúc Cloud — MemRAG Chatbot

## Sơ đồ tổng thể

```
Internet
    │
    ▼
┌────────────────────────────────────────────────────────┐
│                      AWS Account                        │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │           EC2 Instance t3.small (EBS gp3 30GB)    │  │
│  │                                                   │  │
│  │  ┌──────────────────────────────────────────────┐ │  │
│  │  │           ECS Task (network_mode=host)        │ │  │
│  │  │                                              │ │  │
│  │  │  ┌─────────────────┐  ┌──────────────────┐  │ │  │
│  │  │  │ Container:      │  │ Container:       │  │ │  │
│  │  │  │ qdrant          │  │ backend          │  │ │  │
│  │  │  │ :6333           │  │ FastAPI :8000    │  │ │  │
│  │  │  │ /qdrant/storage │  │ → localhost:6333 │  │ │  │
│  │  │  │ (EBS bind mount)│  │ → SSM secrets    │  │ │  │
│  │  │  └─────────────────┘  │ → S3 uploads     │  │ │  │
│  │  │    ↑ HEALTHY check    │ → Gemini API     │  │ │  │
│  │  │    trước khi backend  └──────────────────┘  │ │  │
│  │  │    được start                               │ │  │
│  │  └──────────────────────────────────────────────┘ │  │
│  │                                                   │  │
│  │  Swap: 2GB (file trên EBS) — chống OOM kill       │  │
│  │  ECS Agent: quản lý vòng đời cả 2 container       │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │   ECR    │  │   SSM    │  │          S3          │  │
│  │  (images)│  │(secrets) │  │   (PDF uploads)      │  │
│  └──────────┘  └──────────┘  └──────────────────────┘  │
│                                                         │
│  CloudWatch Logs: /ecs/memrag                           │
│  ├── backend/backend/<task-id>                          │
│  └── qdrant/qdrant/<task-id>                            │
└────────────────────────────────────────────────────────┘
```

---

## Từng service và lý do chọn

### EC2 t3.small

**Làm gì:** Máy chủ vật lý chạy ECS agent và tất cả containers trong 1 ECS Task.

**Tại sao t3.small (2 vCPU, 2GB RAM):**
- t3.micro (1GB) không đủ — Qdrant + FastAPI + ECS agent cần ~1.2GB RAM
- t3.medium (4GB) dư thừa cho giai đoạn đầu, tốn kém hơn không cần thiết
- t3 là "burstable" — baseline CPU thấp, burst khi có request thật

**EBS gp3 30GB:**
- Root volume chứa OS, Docker images, ECS agent
- `/qdrant/storage` bind mount vào đây → Qdrant data persistent qua các lần restart container

**Swap 2GB (file trên EBS):**
- Khi RAM đầy (VD: nhiều request đồng thời), Linux dùng swap thay vì OOM kill process
- Swap chậm hơn RAM ~10x nhưng tốt hơn là container bị kill đột ngột
- Được tạo tự động qua `user_data` khi EC2 khởi tạo, mount vĩnh viễn vào `/etc/fstab`

**Tại sao không dùng Fargate:**
- Fargate = serverless container, không cần quản lý EC2 nhưng không support bind mount trực tiếp vào EBS
- Qdrant cần persistent storage đơn giản → EC2 bind mount là giải pháp tự nhiên nhất
- EC2 rẻ hơn Fargate ~30-40% cho workload chạy liên tục

---

### ECS (Elastic Container Service) — Sidecar Pattern

**Làm gì:** Quản lý vòng đời cả 2 containers (backend + Qdrant) trong cùng 1 Task.

**Tại sao Sidecar Pattern (Qdrant trong cùng ECS Task):**

Trước đây: Qdrant chạy bằng `docker run --restart unless-stopped` thủ công trên EC2.
- Vấn đề: ECS không biết Qdrant đang chạy → không quản lý được lifecycle
- Khi deploy backend mới, ECS restart task → Qdrant vẫn chạy → OK
- Nhưng: Qdrant crash → phải SSH vào restart tay, không có alerting

Sau khi đổi sang Sidecar:
- ECS quản lý cả 2 containers trong cùng 1 Task
- Qdrant crash → ECS tự restart toàn bộ Task (cả backend lẫn Qdrant)
- Logs của cả 2 containers đều vào CloudWatch

**`network_mode = "host"`:**
- Cả 2 container dùng chung network namespace của EC2 host
- Backend gọi `localhost:6333` → gặp Qdrant trong cùng task (không cần service discovery)
- Không cần mở port giữa containers, không overhead routing

**`dependsOn: condition: "HEALTHY"`:**
- Backend chỉ start sau khi Qdrant healthcheck `/readyz` trả về 200
- Tránh lỗi `connection refused` khi backend start trước Qdrant còn đang khởi tạo

**`essential = true` cho cả 2:**
- Nếu 1 trong 2 crash → toàn bộ Task dừng → ECS tự restart Task mới
- Đảm bảo backend và Qdrant luôn live/die cùng nhau, không có trạng thái "backend running, Qdrant dead"

**`deployment_minimum_healthy_percent = 0`:**
- Single instance → chỉ có 1 task slot
- Nếu để 100%: ECS cần start task mới TRƯỚC khi stop task cũ → không đủ port (host network)
- Để 0%: ECS stop task cũ rồi start task mới → ~30-60s downtime khi deploy, chấp nhận được

**`force_new_deployment = false`:**
- `terraform apply` không restart container nếu task definition không thay đổi
- CI/CD pipeline tự register task def mới (với image SHA mới) → ECS tự rolling deploy

---

### ECR (Elastic Container Registry)

**Làm gì:** Kho lưu Docker images, giống Docker Hub nhưng private trong AWS.

**Tại sao không dùng Docker Hub:**
- Docker Hub free tier có pull rate limit (100 pulls/6h per IP)
- ECR nằm trong cùng AWS network với EC2 → pull image không tốn bandwidth ra internet, nhanh hơn
- Tích hợp IAM — EC2 instance dùng instance profile để pull, không cần username/password

**Lifecycle policy giữ 10 images:**
- Mỗi CI/CD push tạo 1 image mới tag theo commit SHA (immutable)
- Không giới hạn → tích lũy hàng trăm images → tốn tiền lưu trữ ($0.10/GB/tháng)
- Giữ 10 = rollback được về 10 commit gần nhất

---

### SSM Parameter Store (secrets)

**Làm gì:** Lưu trữ secrets dưới dạng encrypted, inject vào container lúc runtime qua ECS.

**Tại sao không để trong task definition / environment vars:**
- Task definition lưu trên AWS → ai có quyền đọc ECS đều thấy plaintext
- SSM SecureString = encrypted bằng KMS key của AWS, chỉ ECS task execution role mới đọc được
- Rotate key → chỉ update SSM value, không cần redeploy container

**Tại sao không dùng Secrets Manager:**
- Secrets Manager: $0.40/secret/tháng → 3 secrets = $1.2/tháng
- SSM SecureString: miễn phí với standard tier
- Secrets Manager phù hợp khi cần auto-rotation (tự động đổi DB password) — không cần ở đây

---

### S3 (file storage)

**Làm gì:** Lưu file PDF người dùng upload, persistent ngoài EC2.

**Tại sao không lưu trên EC2:**
- ECS task restart → container mới mount `/app/uploads` trống → mất hết file
- S3 = persistent, durable (11 nines), unlimited capacity
- Không cần quản lý disk space

**Presigned URL (expiry 3600s = 1h):**
- File private, không public trực tiếp qua URL
- Backend ký URL tạm → client download thẳng từ S3 (không qua backend → tiết kiệm bandwidth)
- URL hết hạn sau 1h → bảo mật

---

### IAM — Principle of Least Privilege

```
ec2-instance-role       → EC2 join ECS cluster, pull image từ ECR
ecs-task-execution-role → ECS agent pull image, đọc SSM, ghi CloudWatch logs
github-actions-user     → push image ECR, update ECS service (chỉ 2 action đó)
```

- GitHub Actions bị compromise → chỉ deploy được, không đọc SSM secrets, không xóa resource
- Container bị compromise → không push image mới lên ECR

---

### CloudWatch Logs

**Log groups:** `/ecs/memrag`
- Stream `backend/backend/<task-id>` — FastAPI application logs
- Stream `qdrant/qdrant/<task-id>` — Qdrant server logs

**Tại sao cần CloudWatch thay vì `docker logs`:**
- `docker logs` chỉ xem được khi SSH vào EC2, không xem được log cũ sau khi container restart
- CloudWatch giữ lịch sử, searchable, có thể set alert (VD: alert khi log có "ERROR")
- Logs persist dù container bị replace hoàn toàn

**`awslogs-create-group: true`:**
- Log group tự động tạo khi container start lần đầu
- Yêu cầu execution role có `logs:CreateLogGroup` (thêm vào IAM ngoài managed policy mặc định)

---

### Qdrant — self-hosted (Sidecar)

**Làm gì:** Vector database lưu embeddings cho RAG (PDF search) và mem0 (long-term memory).

**Tại sao không dùng Qdrant Cloud:**
- Free tier giới hạn 1GB RAM, 0.5 vCPU — không đủ cho cả RAG + mem0
- Self-host chia sẻ resource với backend trên t3.small → tiết kiệm chi phí
- Data không ra ngoài AWS network

**Persistent storage (`/qdrant/storage` bind mount):**
- Qdrant lưu vectors tại `/qdrant/storage` trong container
- Bind mount vào `/qdrant/storage` trên EBS → data survive qua container restart
- ECS task restart → container mới mount lại cùng path trên EBS → data intact

---

## Tóm tắt lý do cho từng config quan trọng

| Config | Giá trị | Lý do |
|--------|---------|-------|
| `network_mode` | `host` | Backend + Qdrant dùng chung localhost, không cần service discovery |
| `dependsOn condition` | `HEALTHY` | Backend không start khi Qdrant chưa sẵn sàng |
| `essential` (cả 2 containers) | `true` | Live/die cùng nhau, ECS tự restart khi 1 trong 2 crash |
| `deployment_minimum_healthy_percent` | `0` | Single instance, không đủ resource để chạy 2 tasks song song |
| `force_new_deployment` | `false` | `terraform apply` không restart container nếu không có thay đổi thực sự |
| Swap 2GB | file trên EBS | Chống OOM kill khi traffic đột biến, không cần nâng instance type |
| EBS bind mount | `/qdrant/storage` | Qdrant data persist qua container restart |
