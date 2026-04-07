# ── ENI Trunking (bắt buộc cho awsvpc network mode trên EC2 launch type) ─────
# Cho phép nhiều task dùng awsvpc trên cùng 1 EC2 instance
# Một lần per account per region — không ảnh hưởng resource đang chạy
resource "aws_ecs_account_setting_default" "awsvpc_trunking" {
  name  = "awsvpcTrunking"
  value = "enabled"
}

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
  network_mode       = "awsvpc" # mỗi task có ENI riêng trong VPC
  execution_role_arn = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn      = aws_iam_role.ecs_task_role.arn

  cpu    = var.task_cpu
  memory = var.task_memory

  # Qdrant đã được tách ra service riêng — không cần qdrant-storage volume
  # và không cần qdrant sidecar container nữa

  container_definitions = jsonencode([
    # ── Main: FastAPI backend ─────────────────────────────────────────────
    {
      name  = var.container_name
      image = "${aws_ecr_repository.backend.repository_url}:latest"

      memoryReservation = 512
      cpu               = 256

      essential = true

      # Không còn dependsOn qdrant — Qdrant là service riêng biệt

      portMappings = [{
        containerPort = var.container_port
        protocol      = "tcp"
      }]

      environment = [
        { name = "GEMINI_MODEL", value = var.gemini_model },
        { name = "GEMINI_EMBEDDING_MODEL", value = "gemini-embedding-001" },
        # Qdrant service discovery: resolve qua Cloud Map DNS
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
        # Soniox realtime transcription (non-secret config)
        { name = "SONIOX_MODEL", value = var.soniox_model },
        { name = "SONIOX_TARGET_LANG", value = var.soniox_target_lang },
        { name = "SONIOX_WS_URL", value = var.soniox_ws_url },
      ]

      secrets = [
        { name = "GEMINI_API_KEY", valueFrom = aws_ssm_parameter.gemini_api_key.arn },
        { name = "S3_ACCESS_KEY_ID", valueFrom = aws_ssm_parameter.s3_access_key_id.arn },
        { name = "S3_SECRET_ACCESS_KEY", valueFrom = aws_ssm_parameter.s3_secret_access_key.arn },
        { name = "SONIOX_API_KEY", valueFrom = aws_ssm_parameter.soniox_api_key.arn },
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

  depends_on = [aws_ecs_service.qdrant]
}

# ── ECS Service ──────────────────────────────────────────────────────────────
resource "aws_ecs_service" "backend" {
  name            = var.ecs_service_name
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.desired_count
  launch_type     = "EC2"

  # awsvpc: mỗi task có ENI riêng trong private subnets
  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.backend_new.id]
  }

  # ALB routes traffic đến backend tasks
  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = var.container_name
    container_port   = var.container_port
  }

  # Rolling deploy: Terraform destroy + recreate service khi thêm load_balancer lần đầu
  # create_before_destroy giảm thiểu downtime
  lifecycle {
    create_before_destroy = true
  }

  # Min 0 cho phép stop task cũ trước khi start task mới (single instance)
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  # false = terraform apply không restart container nếu task def không đổi
  force_new_deployment = false

  tags = { Project = var.project_name }

  depends_on = [
    aws_instance.ecs_host_new,
    aws_ecs_service.qdrant,
    aws_lb_listener.http,
  ]
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
        aws_ssm_parameter.soniox_api_key.arn,
      ]
    }]
  })
}
