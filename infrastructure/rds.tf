# ── DB Subnet Group ──────────────────────────────────────────────────────────
# Cần 2 AZ cho RDS dù chỉ chạy single-AZ instance
resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db-subnet-group"
  subnet_ids = [aws_subnet.private[0].id, aws_subnet.private[1].id]

  tags = {
    Project = var.project_name
    Name    = "${var.project_name}-db-subnet-group"
  }
}

# ── RDS Security Group ───────────────────────────────────────────────────────
# Chỉ cho phép ECS backend kết nối (host network mode → dùng ecs_host SG)
resource "aws_security_group" "rds" {
  name        = "${var.project_name}-rds-sg"
  description = "RDS PostgreSQL - allow from ECS backend only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "PostgreSQL from ECS host"
    from_port       = 5432
    to_port         = 5432
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
    Name    = "${var.project_name}-rds-sg"
  }
}

# ── Random Password ──────────────────────────────────────────────────────────
# special = false để tránh issues với connection string parsing
resource "random_password" "db_password" {
  length  = 32
  special = false
}

# ── SSM Parameter — DB Password ──────────────────────────────────────────────
resource "aws_ssm_parameter" "db_password" {
  name  = "/${var.project_name}/DB_PASSWORD"
  type  = "SecureString"
  value = random_password.db_password.result

  tags = {
    Project = var.project_name
  }
}

# ── RDS PostgreSQL Instance ──────────────────────────────────────────────────
resource "aws_db_instance" "postgres" {
  identifier     = "${var.project_name}-postgres"
  engine         = "postgres"
  engine_version = "16.13"
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = 30
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.project_name # "memrag"
  username = var.db_username
  password = random_password.db_password.result

  multi_az               = false
  availability_zone      = var.availability_zones[0] # cùng AZ với EC2 host
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false

  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.project_name}-postgres-final"
  deletion_protection       = false

  backup_retention_period = 1
  backup_window           = "15:00-16:00" # ~3-4 AM AEST

  performance_insights_enabled          = true
  performance_insights_retention_period = 7

  tags = {
    Project = var.project_name
    Name    = "${var.project_name}-postgres"
  }

  # Đảm bảo RDS được tạo sau khi security group và subnet group sẵn sàng
  depends_on = [
    aws_security_group.rds,
    aws_db_subnet_group.main,
  ]
}
