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
  description = "URL của Qdrant server (Cloud Map DNS sau khi tách service)"
  type        = string
  default     = "http://qdrant.memrag.local:6333"
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

# ── VPC ─────────────────────────────────────────────────────────────────────
variable "vpc_cidr" {
  description = "CIDR block cho VPC mới"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Danh sách AZ (ít nhất 2 AZ cho ALB)"
  type        = list(string)
  default     = ["ap-southeast-2a", "ap-southeast-2b"]
}

variable "public_subnet_cidrs" {
  description = "CIDR cho public subnets (ALB)"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR cho private subnets (backend + qdrant)"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}

# ── Auto Scaling ─────────────────────────────────────────────────────────────
variable "backend_min_count" {
  description = "Số lượng backend task tối thiểu"
  type        = number
  default     = 1
}

variable "backend_max_count" {
  description = "Số lượng backend task tối đa"
  type        = number
  default     = 4
}

variable "cpu_scaling_target" {
  description = "CPU utilization % để trigger scale out"
  type        = number
  default     = 60
}
