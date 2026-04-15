# ── ALB Security Group ────────────────────────────────────────────────────────
# Allow HTTP/HTTPS from anywhere — CloudFront-only restriction is enforced via
# a secret custom header (X-Origin-Verify) checked at the ALB listener level,
# not via IP-based rules (CloudFront prefix list expands to 150+ CIDRs which
# exceeds the default 60-rule limit per security group).
resource "aws_security_group" "alb" {
  name        = "${var.project_name}-alb-sg"
  description = "ALB - allow HTTP and HTTPS from internet"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP from internet"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS from internet"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Project = var.project_name
    Name    = "${var.project_name}-alb-sg"
  }
}

# ── Backend Security Group ────────────────────────────────────────────────────
# Chỉ nhận traffic từ ALB (port 8000)
resource "aws_security_group" "backend_new" {
  name        = "${var.project_name}-backend-new-sg"
  description = "Backend ECS tasks - allow traffic from ALB only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Backend API from ALB"
    from_port       = var.container_port
    to_port         = var.container_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Project = var.project_name
    Name    = "${var.project_name}-backend-new-sg"
  }
}

# ── Qdrant Security Group ─────────────────────────────────────────────────────
# Chỉ nhận traffic từ backend (port 6333)
resource "aws_security_group" "qdrant" {
  name        = "${var.project_name}-qdrant-sg"
  description = "Qdrant service - allow traffic from backend only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Qdrant REST API from backend (host network mode)"
    from_port       = 6333
    to_port         = 6333
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_host.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Project = var.project_name
    Name    = "${var.project_name}-qdrant-sg"
  }
}

# ── ECS Host Security Group ───────────────────────────────────────────────────
# EC2 instance chạy ECS tasks — cần cho ENI trunking (awsvpc mode)
resource "aws_security_group" "ecs_host" {
  name        = "${var.project_name}-ecs-host-sg"
  description = "EC2 ECS host - allow traffic from ALB and SSH"
  vpc_id      = aws_vpc.main.id

  # ENI trunking: ALB gửi traffic trực tiếp đến task ENI trên EC2 host
  ingress {
    description     = "Traffic from ALB to task ENIs"
    from_port       = 0
    to_port         = 65535
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Project = var.project_name
    Name    = "${var.project_name}-ecs-host-sg"
  }
}
