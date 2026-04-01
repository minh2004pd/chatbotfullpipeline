Kiến trúc Cloud của MemRAG

Internet
    │
    ▼
┌─────────────────────────────────────────────────────┐
│                   AWS Account                        │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │              EC2 Instance (t3.small)          │   │
│  │                                              │   │
│  │  ┌─────────────────┐   ┌──────────────────┐  │   │
│  │  │  ECS Agent      │   │  Qdrant          │  │   │
│  │  │  (quản lý       │   │  :6333           │  │   │
│  │  │   containers)   │   │  (vector DB)     │  │   │
│  │  └─────────────────┘   └──────────────────┘  │   │
│  │                                              │   │
│  │  ┌──────────────────────────────────────┐    │   │
│  │  │  ECS Task (backend container)        │    │   │
│  │  │  FastAPI :8000                       │    │   │
│  │  │  → đọc secrets từ SSM               │    │   │
│  │  │  → gọi localhost:6333 (Qdrant)      │    │   │
│  │  │  → gọi S3 (file storage)            │    │   │
│  │  │  → gọi Gemini API (LLM)             │    │   │
│  │  └──────────────────────────────────────┘    │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │   ECR    │  │   SSM    │  │       S3         │   │
│  │  (image) │  │(secrets) │  │  (PDF uploads)   │   │
│  └──────────┘  └──────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────┘
Từng service và lý do chọn
EC2 t3.small
Làm gì: Máy chủ vật lý chạy tất cả containers.

Tại sao t3.small (2 vCPU, 2GB RAM):

t3.micro (1GB) không đủ — Qdrant + FastAPI + ECS agent cần ~1.2GB
t3.medium (4GB) dư thừa cho giai đoạn đầu
t3 là "burstable" — bình thường dùng ít CPU, khi có request burst lên được
Tại sao không dùng Fargate:

Fargate = serverless container, không cần quản lý EC2
Nhưng Fargate không chạy được Qdrant (cần persistent storage phức tạp hơn)
EC2 cho phép chạy Qdrant trực tiếp trên host bằng docker run
ECS (Elastic Container Service)
Làm gì: Quản lý vòng đời container — tự restart khi crash, deploy version mới, health check.

Tại sao không chạy Docker thẳng trên EC2:

Docker thẳng: crash → không tự restart, deploy mới → phải SSH tay
ECS: crash → tự restart, CI/CD push image mới → ECS tự rolling deploy không downtime
Cấu hình network_mode = "host" (vừa đổi):

Bridge mode: container có network riêng → localhost:6333 trong container = chính container đó, không reach được Qdrant trên host
Host mode: container dùng chung network với EC2 → localhost:6333 = Qdrant đang chạy trên EC2
Cấu hình deployment_minimum_healthy_percent = 0:

Single instance → chỉ có 1 task chạy được
Nếu để 100%: ECS cần start task mới TRƯỚC khi stop task cũ → không đủ resource
Để 0%: ECS stop task cũ rồi start task mới → có ~30s downtime khi deploy, chấp nhận được
ECR (Elastic Container Registry)
Làm gì: Kho lưu Docker images, giống Docker Hub nhưng private trong AWS.

Tại sao không dùng Docker Hub:

Docker Hub public có pull rate limit (100 pulls/6h với free tier)
ECR nằm trong cùng AWS network với ECS → pull image nhanh hơn, không tốn bandwidth ra ngoài
Tích hợp sẵn IAM — không cần quản lý username/password riêng
Lifecycle policy giữ 10 images:

Mỗi CI/CD push tạo 1 image mới (tag theo commit SHA)
Không giới hạn → tích lũy hàng trăm images → tốn tiền lưu trữ
Giữ 10 = có thể rollback về 10 version gần nhất nếu cần
SSM Parameter Store (secrets)
Làm gì: Lưu trữ secrets (API keys) dưới dạng encrypted, inject vào container lúc runtime.

Tại sao không để secrets trong task definition / environment variables:

Task definition lưu trên AWS → ai có quyền đọc ECS đều thấy secrets dưới dạng plaintext
SSM SecureString = encrypted bằng KMS, chỉ container có đúng IAM role mới đọc được
Thay đổi secret (rotate key) → chỉ cần update SSM, không cần redeploy
Tại sao không dùng Secrets Manager:

Secrets Manager đắt hơn ($0.40/secret/tháng vs SSM free tier)
SSM đủ dùng cho project này
Secrets Manager phù hợp khi cần auto-rotation (tự động đổi password DB)
S3 (file storage)
Làm gì: Lưu file PDF người dùng upload.

Tại sao không lưu trực tiếp trên EC2:

EC2 disk = ephemeral — khi instance bị replace (stop/start), data mất
ECS task restart → container mới không có file cũ
S3 = persistent, durable (11 nines), không giới hạn dung lượng
Presigned URL (3600s = 1h):

File PDF private, không public trực tiếp
Backend tạo URL tạm có chữ ký → client download trực tiếp từ S3 (không qua backend)
Sau 1h URL hết hạn → bảo mật
IAM Roles — tại sao cần 3 roles riêng biệt

ec2-instance-role       → EC2 đăng ký vào ECS cluster, pull image từ ECR
ecs-task-execution-role → ECS agent pull image, đọc SSM secrets, ghi CloudWatch logs
github-actions-user     → CI/CD push image ECR, update ECS service
Principle of Least Privilege: Mỗi entity chỉ có đúng quyền cần thiết.

Nếu GitHub Actions bị compromise → chỉ deploy được, không đọc được SSM secrets
Container bị compromise → không push được image mới lên ECR
CloudWatch Logs
Cấu hình awslogs-create-group: true: Tự tạo log group nếu chưa tồn tại.

Tại sao không đọc logs bằng docker logs trực tiếp:

docker logs chỉ xem được khi SSH vào EC2
CloudWatch = xem logs từ browser, search, alert khi có lỗi, giữ lịch sử dù container restart
Qdrant (self-hosted trên EC2)
Làm gì: Vector database lưu embeddings cho RAG và mem0 memory.

Tại sao không dùng Qdrant Cloud:

Qdrant Cloud free tier giới hạn 1GB RAM, 0.5 vCPU
Self-host trên EC2 dùng chung resource với backend → tiết kiệm chi phí
Data không ra ngoài AWS network
Tại sao --restart unless-stopped:

EC2 reboot → Docker service start lại → Qdrant tự start lại
ECS chỉ quản lý backend container, không quản lý Qdrant