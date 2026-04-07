# ── ECS Auto Scaling ──────────────────────────────────────────────────────────
# Scale backend tasks dựa trên CPU utilization
# Lưu ý: t3.small (2 vCPU, 2GB RAM), mỗi backend task dùng 256 CPU + 512MB
# → max ~3 backend tasks trên 1 instance (Qdrant chiếm 256 CPU + 512MB)
# Nếu cần scale hơn, thêm EC2 ASG

resource "aws_appautoscaling_target" "backend" {
  max_capacity       = var.backend_max_count
  min_capacity       = var.backend_min_count
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.backend.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"

  depends_on = [aws_ecs_service.backend]
}

# Scale out khi CPU trung bình > 60%, scale in khi < 60%
resource "aws_appautoscaling_policy" "backend_cpu" {
  name               = "${var.project_name}-backend-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.backend.resource_id
  scalable_dimension = aws_appautoscaling_target.backend.scalable_dimension
  service_namespace  = aws_appautoscaling_target.backend.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value = var.cpu_scaling_target

    # scale_out: 60s cooldown — phản ứng nhanh khi traffic tăng đột biến
    scale_out_cooldown = 60
    # scale_in: 300s cooldown — tránh flapping khi traffic giảm tạm thời
    scale_in_cooldown = 300
  }
}
