# ── Cloud Map Private DNS Namespace ──────────────────────────────────────────
# Backend tìm thấy Qdrant qua DNS qdrant.memrag.local:6333
# Không cần hardcode IP hay dùng EC2 metadata
resource "aws_service_discovery_private_dns_namespace" "main" {
  name = "memrag.local"
  vpc  = aws_vpc.main.id

  tags = {
    Project = var.project_name
    Name    = "${var.project_name}-dns-namespace"
  }
}

# ── Qdrant Service Discovery Record ──────────────────────────────────────────
# Khi Qdrant ECS task start, nó tự đăng ký vào record này
# Backend dùng URL http://qdrant.memrag.local:6333
resource "aws_service_discovery_service" "qdrant" {
  name = "qdrant"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.main.id

    dns_records {
      ttl  = 10
      type = "A"
    }

    # MULTIVALUE: trả về nhiều IP nếu có nhiều task
    # (Qdrant luôn desired_count=1 nhưng config sẵn cho tương lai)
    routing_policy = "MULTIVALUE"
  }

  # ECS tự quản lý health check thông qua task health check
  # failure_threshold=1: xóa record ngay khi task unhealthy
  health_check_custom_config {
    failure_threshold = 1
  }

  tags = {
    Project = var.project_name
    Name    = "${var.project_name}-qdrant-sd"
  }
}
