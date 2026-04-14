# ── Application Load Balancer ─────────────────────────────────────────────────
# Internet-facing ALB trong public subnets — nhận traffic từ CloudFront
resource "aws_lb" "backend" {
  name               = "${var.project_name}-backend-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  # Bật access logs nếu cần audit: enable_http2 = true (mặc định)
  # access_logs { bucket = "..." enabled = true }

  tags = {
    Project = var.project_name
    Name    = "${var.project_name}-backend-alb"
  }
}

# ── Target Group ─────────────────────────────────────────────────────────────
# target_type = "instance" cho EC2 launch type với host network mode
# ECS auto-registers EC2 instance ID vào target group
resource "aws_lb_target_group" "backend" {
  name        = "${var.project_name}-backend-tg-v2"
  port        = var.container_port
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "instance"

  # FastAPI health check endpoint (không có /api prefix)
  health_check {
    enabled             = true
    path                = "/health"
    port                = "traffic-port"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 10
    interval            = 30
    matcher             = "200"
  }

  # Graceful deregistration: cho phép in-flight requests hoàn thành
  deregistration_delay = 30

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Project = var.project_name
    Name    = "${var.project_name}-backend-tg"
  }
}

# ── HTTP Listener ─────────────────────────────────────────────────────────────
# CloudFront → ALB qua HTTP (CloudFront xử lý HTTPS với user)
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.backend.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  tags = { Project = var.project_name }
}
