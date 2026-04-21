variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "ap-southeast-2"
}

variable "project_name" {
  description = "Tên project, dùng làm prefix cho các resource"
  type        = string
  default     = "memrag"
}

# ── ECR ─────────────────────────────────────────────────────────────────────
variable "ecr_repository_name" {
  description = "Tên ECR repository (phải khớp với ECR_REPOSITORY trong CI/CD)"
  type        = string
  default     = "memragbackend"
}

# ── ECS ─────────────────────────────────────────────────────────────────────
variable "ecs_cluster_name" {
  description = "Tên ECS cluster (phải khớp với ECS_CLUSTER trong CI/CD)"
  type        = string
  default     = "memrag-cluster"
}

variable "ecs_service_name" {
  description = "Tên ECS service (phải khớp với ECS_SERVICE trong CI/CD)"
  type        = string
  default     = "memrag-backend-service"
}

variable "ecs_task_family" {
  description = "Tên task definition family (phải khớp với ECS_TASK_DEFINITION trong CI/CD)"
  type        = string
  default     = "memrag-backend"
}

variable "container_name" {
  description = "Tên container trong task def (phải khớp với CONTAINER_NAME trong CI/CD)"
  type        = string
  default     = "backend"
}

variable "container_port" {
  description = "Port mà backend lắng nghe"
  type        = number
  default     = 8000
}

variable "task_cpu" {
  description = "CPU units cho task (1 vCPU = 1024 units)"
  type        = number
  default     = 512
}

variable "task_memory" {
  description = "Memory MB cho task"
  type        = number
  default     = 1024
}

variable "desired_count" {
  description = "Số lượng task muốn chạy"
  type        = number
  default     = 1
}

# ── Auto Scaling ──────────────────────────────────────────────────────────────
variable "backend_max_count" {
  description = "Maximum number of backend tasks for auto scaling"
  type        = number
  default     = 3
}

variable "backend_min_count" {
  description = "Minimum number of backend tasks for auto scaling"
  type        = number
  default     = 1
}

variable "cpu_scaling_target" {
  description = "Target CPU utilization percentage for auto scaling"
  type        = number
  default     = 60
}

# ── EC2 ─────────────────────────────────────────────────────────────────────
variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.medium"
}

variable "key_pair_name" {
  description = "Tên EC2 Key Pair để SSH vào instance (phải tạo trước trên AWS Console)"
  type        = string
  default     = ""
}

variable "allowed_ssh_cidr" {
  description = "CIDR được phép SSH vào EC2 (mặc định chặn hết)"
  type        = string
  default     = "0.0.0.0/0" # Đổi thành IP của bạn cho an toàn hơn
}

# ── App environment variables ────────────────────────────────────────────────
variable "gemini_api_key" {
  description = "Google Gemini API key"
  type        = string
  sensitive   = true
}

variable "gemini_model" {
  type    = string
  default = "gemini-2.5-flash"
}

variable "qdrant_url" {
  description = "URL của Qdrant server"
  type        = string
  default     = "http://localhost:6333"
}

variable "allowed_origins" {
  description = "CORS allowed origins (JSON array format)"
  type        = string
  default     = "[\"http://localhost:5173\"]"
}

# ── S3 Storage ───────────────────────────────────────────────────────────────
variable "storage_backend" {
  type    = string
  default = "s3"
}

variable "s3_bucket" {
  type = string
}

variable "s3_region" {
  type    = string
  default = "ap-southeast-2"
}

variable "s3_access_key_id" {
  type      = string
  sensitive = true
}

variable "s3_secret_access_key" {
  type      = string
  sensitive = true
}

variable "s3_endpoint_url" {
  type    = string
  default = "https://s3.ap-southeast-2.amazonaws.com"
}

variable "s3_prefix" {
  type    = string
  default = "uploads"
}

variable "s3_presigned_url_expiry" {
  type    = number
  default = 3600
}

# ── Soniox (realtime transcription) ────────────────────────────────────────
variable "soniox_api_key" {
  description = "Soniox API key for realtime transcription"
  type        = string
  sensitive   = true
}

variable "soniox_model" {
  description = "Soniox realtime transcription model"
  type        = string
  default     = "stt-rt-v4"
}

variable "soniox_target_lang" {
  description = "Target language for Soniox translation"
  type        = string
  default     = "vi"
}

variable "soniox_ws_url" {
  description = "Soniox websocket URL"
  type        = string
  default     = "wss://stt-rt.soniox.com/transcribe-websocket"
}

variable "soniox_endpoint_delay_ms" {
  description = "Soniox endpoint detection delay in milliseconds (500-3000)"
  type        = number
  default     = 1000
}

variable "jwt_secret_key" {
  description = "JWT signing secret (HS256). Must be 32+ characters."
  type        = string
  sensitive   = true
}

# ── Networking ─────────────────────────────────────────────────────────────────
variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "AWS availability zones"
  type        = list(string)
  default     = ["ap-southeast-2a", "ap-southeast-2b"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}

# ── RDS PostgreSQL ───────────────────────────────────────────────────────────
variable "db_instance_class" {
  description = "RDS instance class for PostgreSQL"
  type        = string
  default     = "db.t3.micro"
}

variable "db_allocated_storage" {
  description = "Initial allocated storage for RDS (GB)"
  type        = number
  default     = 20
}

variable "db_username" {
  description = "Master username for RDS PostgreSQL"
  type        = string
  default     = "memrag"
}

# ── ElastiCache Redis ─────────────────────────────────────────────────────────
variable "redis_node_type" {
  description = "ElastiCache Redis node type"
  type        = string
  default     = "cache.t3.micro"
}

variable "redis_engine_version" {
  description = "ElastiCache Redis engine version"
  type        = string
  default     = "7.1"
}
