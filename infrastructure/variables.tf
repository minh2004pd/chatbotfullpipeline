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

# ── EC2 ─────────────────────────────────────────────────────────────────────
variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.small"
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
