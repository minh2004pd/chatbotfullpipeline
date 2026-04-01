resource "aws_ecs_cluster" "main" {
  name = var.ecs_cluster_name

  setting {
    name  = "containerInsights"
    value = "disabled" # bật lên nếu cần CloudWatch metrics chi tiết
  }

  tags = { Project = var.project_name }
}

# ── Task Definition ──────────────────────────────────────────────────────────
resource "aws_ecs_task_definition" "backend" {
  family             = var.ecs_task_family
  network_mode       = "bridge" # EC2 launch type dùng bridge (không phải awsvpc)
  execution_role_arn = aws_iam_role.ecs_task_execution_role.arn

  # CPU/memory ở level task (soft limit, EC2 launch type không enforce cứng như Fargate)
  cpu    = var.task_cpu
  memory = var.task_memory

  container_definitions = jsonencode([
    {
      name  = var.container_name
      image = "${aws_ecr_repository.backend.repository_url}:latest"

      cpu    = var.task_cpu
      memory = var.task_memory

      essential = true

      portMappings = [{
        containerPort = var.container_port
        hostPort      = var.container_port
        protocol      = "tcp"
      }]

      environment = [
        { name = "GEMINI_MODEL", value = var.gemini_model },
        { name = "QDRANT_URL", value = var.qdrant_url },
        { name = "ALLOWED_ORIGINS", value = var.allowed_origins },
        { name = "STORAGE_BACKEND", value = var.storage_backend },
        { name = "UPLOAD_DIR", value = "/app/uploads" },
        { name = "S3_BUCKET", value = var.s3_bucket },
        { name = "S3_REGION", value = var.s3_region },
        { name = "S3_ENDPOINT_URL", value = var.s3_endpoint_url },
        { name = "S3_PREFIX", value = var.s3_prefix },
        { name = "S3_PRESIGNED_URL_EXPIRY", value = tostring(var.s3_presigned_url_expiry) },
      ]

      # Sensitive values lưu trong SSM SecureString
      secrets = [
        { name = "GEMINI_API_KEY", valueFrom = aws_ssm_parameter.gemini_api_key.arn },
        { name = "S3_ACCESS_KEY_ID", valueFrom = aws_ssm_parameter.s3_access_key_id.arn },
        { name = "S3_SECRET_ACCESS_KEY", valueFrom = aws_ssm_parameter.s3_secret_access_key.arn },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/${var.project_name}"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "backend"
          "awslogs-create-group"  = "true"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:${var.container_port}/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }
    }
  ])

  tags = { Project = var.project_name }
}

# ── ECS Service ──────────────────────────────────────────────────────────────
resource "aws_ecs_service" "backend" {
  name            = var.ecs_service_name
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.desired_count
  launch_type     = "EC2"

  # Rolling deploy: ECS giữ ít nhất 100% capacity khi deploy
  deployment_minimum_healthy_percent = 0   # single instance: cho phép task dừng trước khi start mới
  deployment_maximum_percent         = 100

  # Tự động đăng ký lại task mới nhất khi service cập nhật
  force_new_deployment = true

  tags = { Project = var.project_name }

  # Đợi EC2 instance join cluster trước khi tạo service
  depends_on = [aws_instance.ecs_host]
}

# ── SSM Parameters (SecureString) cho sensitive values ───────────────────────
resource "aws_ssm_parameter" "gemini_api_key" {
  name  = "/${var.project_name}/GEMINI_API_KEY"
  type  = "SecureString"
  value = var.gemini_api_key
  tags  = { Project = var.project_name }
}

resource "aws_ssm_parameter" "s3_access_key_id" {
  name  = "/${var.project_name}/S3_ACCESS_KEY_ID"
  type  = "SecureString"
  value = var.s3_access_key_id
  tags  = { Project = var.project_name }
}

resource "aws_ssm_parameter" "s3_secret_access_key" {
  name  = "/${var.project_name}/S3_SECRET_ACCESS_KEY"
  type  = "SecureString"
  value = var.s3_secret_access_key
  tags  = { Project = var.project_name }
}

# ── IAM: cho phép task execution role đọc SSM ────────────────────────────────
resource "aws_iam_role_policy" "ecs_task_ssm" {
  name = "${var.project_name}-ecs-task-ssm"
  role = aws_iam_role.ecs_task_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["ssm:GetParameters"]
      Resource = [
        aws_ssm_parameter.gemini_api_key.arn,
        aws_ssm_parameter.s3_access_key_id.arn,
        aws_ssm_parameter.s3_secret_access_key.arn,
      ]
    }]
  })
}
