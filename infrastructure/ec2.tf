# ECS-optimized Amazon Linux 2 AMI mới nhất
data "aws_ami" "ecs_optimized" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["amzn2-ami-ecs-hvm-*-x86_64-ebs"]
  }
}

# Security group cho EC2
resource "aws_security_group" "backend" {
  name        = "${var.project_name}-backend-sg"
  description = "Security group cho MemRAG backend EC2"

  # App port
  ingress {
    from_port   = var.container_port
    to_port     = var.container_port
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Backend API"
  }

  # SSH (chỉ mở khi cần debug, đổi allowed_ssh_cidr thành IP của bạn)
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
    description = "SSH"
  }

  # Cho phép EC2 kết nối ra ngoài (pull image, gọi API, etc.)
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Project = var.project_name }
}

# EC2 instance chạy ECS agent
resource "aws_instance" "ecs_host" {
  ami                    = data.aws_ami.ecs_optimized.id
  instance_type          = var.instance_type
  iam_instance_profile   = aws_iam_instance_profile.ecs_instance.name
  vpc_security_group_ids = [aws_security_group.backend.id]
  key_name               = var.key_pair_name != "" ? var.key_pair_name : null

  # ECS agent đọc file này để biết join vào cluster nào
  user_data = base64encode(<<-EOF
    #!/bin/bash
    echo ECS_CLUSTER=${var.ecs_cluster_name} >> /etc/ecs/ecs.config
    echo ECS_ENABLE_CONTAINER_METADATA=true >> /etc/ecs/ecs.config

    # Tạo Swap 2GB — tránh OOM kill khi traffic đột biến
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab

    # Thư mục persistent storage cho Qdrant (bind mount vào EBS gp3)
    mkdir -p /qdrant/storage
  EOF
  )

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
  }

  tags = {
    Project = var.project_name
    Name    = "${var.project_name}-ecs-host"
  }
}

# Elastic IP — IP tĩnh, không thay đổi khi stop/start EC2
# Chi phí: miễn phí khi EC2 đang chạy, $0.005/giờ (~$3.6/tháng) khi EC2 stopped
resource "aws_eip" "backend" {
  instance = aws_instance.ecs_host.id
  domain   = "vpc"
  tags     = { Project = var.project_name }
}
