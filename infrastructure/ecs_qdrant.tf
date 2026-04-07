# ── Qdrant ECS Task Definition ────────────────────────────────────────────────
resource "aws_ecs_task_definition" "qdrant" {
  family             = "${var.project_name}-qdrant"
  network_mode       = "awsvpc"
  execution_role_arn = aws_iam_role.ecs_task_execution_role.arn
  # Không cần task_role — Qdrant không gọi AWS APIs

  # Bind mount từ /qdrant/storage trên EBS volume của EC2 host
  volume {
    name      = "qdrant-storage"
    host_path = "/qdrant/storage"
  }

  container_definitions = jsonencode([
    {
      name              = "qdrant"
      image             = "qdrant/qdrant:latest"
      memoryReservation = 512
      cpu               = 256
      essential         = true

      portMappings = [{
        containerPort = 6333
        protocol      = "tcp"
      }]

      mountPoints = [{
        sourceVolume  = "qdrant-storage"
        containerPath = "/qdrant/storage"
        readOnly      = false
      }]

      # Không dùng container health check vì qdrant/qdrant image không có curl/wget/python
      # ECS coi task healthy khi container process còn chạy (exit code != 0 → restart)

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/${var.project_name}"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "qdrant-new"
          "awslogs-create-group"  = "true"
        }
      }
    }
  ])

  tags = { Project = var.project_name }

  depends_on = [aws_ecs_account_setting_default.awsvpc_trunking]
}

# ── Qdrant ECS Service ────────────────────────────────────────────────────────
resource "aws_ecs_service" "qdrant" {
  name            = "${var.project_name}-qdrant-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.qdrant.arn
  desired_count   = 1
  launch_type     = "EC2"

  # awsvpc: mỗi task có ENI riêng trong private subnet
  network_configuration {
    subnets         = [aws_subnet.private[0].id] # cố định AZ[0] vì EBS gắn ở đó
    security_groups = [aws_security_group.qdrant.id]
    # Không cần assign_public_ip — private subnet + NAT
  }

  # Đăng ký task vào Cloud Map → DNS qdrant.memrag.local resolve thành task IP
  service_registries {
    registry_arn = aws_service_discovery_service.qdrant.arn
  }

  # Qdrant PHẢI chạy trên EC2 có EBS volume ở AZ[0]
  placement_constraints {
    type       = "memberOf"
    expression = "attribute:ecs.availability-zone == ${var.availability_zones[0]}"
  }

  # Single instance: stop task cũ trước khi start task mới
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  # Đảm bảo EC2 mới và EBS đã sẵn sàng trước khi deploy
  depends_on = [
    aws_instance.ecs_host_new,
    aws_volume_attachment.qdrant_data,
    aws_service_discovery_service.qdrant,
  ]

  tags = { Project = var.project_name }
}
