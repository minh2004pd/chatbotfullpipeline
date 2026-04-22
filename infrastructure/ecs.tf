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
  network_mode       = "host" # dùng chung network EC2 host
  execution_role_arn = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn      = aws_iam_role.ecs_task_role.arn # runtime role cho DynamoDB access

  cpu    = var.task_cpu
  memory = var.task_memory

  container_definitions = jsonencode([
    # ── Main: FastAPI backend ─────────────────────────────────────────────
    {
      name  = var.container_name
      image = "${aws_ecr_repository.backend.repository_url}:latest"

      memoryReservation = 512
      cpu               = 256

      essential = true

      portMappings = [{
        containerPort = var.container_port
        protocol      = "tcp"
      }]

      environment = [
        { name = "GEMINI_MODEL", value = var.gemini_model },
        { name = "GEMINI_EMBEDDING_MODEL", value = "gemini-embedding-001" },
        { name = "QDRANT_URL", value = var.qdrant_url },
        { name = "ALLOWED_ORIGINS", value = var.allowed_origins },
        { name = "STORAGE_BACKEND", value = var.storage_backend },
        { name = "UPLOAD_DIR", value = "/app/uploads" },
        { name = "S3_BUCKET", value = var.s3_bucket },
        { name = "S3_REGION", value = var.s3_region },
        { name = "S3_ENDPOINT_URL", value = var.s3_endpoint_url },
        { name = "S3_PREFIX", value = var.s3_prefix },
        { name = "S3_PRESIGNED_URL_EXPIRY", value = tostring(var.s3_presigned_url_expiry) },
        # DynamoDB — không set DYNAMODB_ENDPOINT_URL → dùng real AWS; IAM task role xử lý auth
        { name = "DYNAMODB_TABLE_NAME", value = aws_dynamodb_table.sessions.name },
        { name = "DYNAMODB_REGION", value = var.aws_region },
        # Meetings table for voice/transcription RAG
        { name = "MEETINGS_TABLE_NAME", value = aws_dynamodb_table.meetings.name },
        # Wiki knowledge base — dùng S3 backend (STORAGE_BACKEND đã set ở trên)
        { name = "WIKI_ENABLED", value = "true" },
        # Soniox realtime transcription (non-secret config)
        { name = "SONIOX_MODEL", value = var.soniox_model },
        { name = "SONIOX_TARGET_LANG", value = var.soniox_target_lang },
        { name = "SONIOX_WS_URL", value = var.soniox_ws_url },
        { name = "SONIOX_ENDPOINT_DELAY_MS", value = tostring(var.soniox_endpoint_delay_ms) },
        # ElastiCache Redis
        { name = "REDIS_URL", value = "redis://${aws_elasticache_replication_group.redis.primary_endpoint_address}:6379/0" },
        # RDS PostgreSQL
        { name = "DATABASE_HOST", value = aws_db_instance.postgres.address },
        { name = "DB_USERNAME", value = var.db_username },
      ]

      secrets = [
        { name = "GEMINI_API_KEY", valueFrom = aws_ssm_parameter.gemini_api_key.arn },
        { name = "SONIOX_API_KEY", valueFrom = aws_ssm_parameter.soniox_api_key.arn },
        { name = "JWT_SECRET_KEY", valueFrom = aws_ssm_parameter.jwt_secret_key.arn },
        # RDS PostgreSQL password from SSM
        { name = "DB_PASSWORD", valueFrom = aws_ssm_parameter.db_password.arn },
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
        command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:${var.container_port}/health')\" || exit 1"]
        interval    = 30
        timeout     = 10
        retries     = 3
        startPeriod = 60
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

  # Single instance: cho phép stop task cũ trước khi start task mới
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  # false = terraform apply không restart container nếu task def không đổi
  force_new_deployment = false

  # Register EC2 instance vào ALB target group (host network mode)
  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = var.container_name
    container_port   = var.container_port
  }

  tags = { Project = var.project_name }

  depends_on = [aws_instance.ecs_host_new]
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

# Soniox API key (SecureString)
resource "aws_ssm_parameter" "soniox_api_key" {
  name  = "/${var.project_name}/SONIOX_API_KEY"
  type  = "SecureString"
  value = var.soniox_api_key
  tags  = { Project = var.project_name }
}

# JWT secret key (SecureString) — required for production auth
resource "aws_ssm_parameter" "jwt_secret_key" {
  name  = "/${var.project_name}/JWT_SECRET_KEY"
  type  = "SecureString"
  value = var.jwt_secret_key
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
        aws_ssm_parameter.soniox_api_key.arn,
        aws_ssm_parameter.jwt_secret_key.arn,
        aws_ssm_parameter.db_password.arn,
      ]
    }]
  })
}
