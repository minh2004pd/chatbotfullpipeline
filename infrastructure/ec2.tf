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

# ─────────────────────────────────────────────────────────────────────────────
# Phase 2+: EC2 mới trong VPC private subnet (chạy cả Qdrant và Backend tasks)
# EC2 cũ (aws_instance.ecs_host + aws_eip.backend) giữ nguyên đến Phase 5
# ─────────────────────────────────────────────────────────────────────────────

# EC2 mới trong VPC private subnet
resource "aws_instance" "ecs_host_new" {
  ami                    = data.aws_ami.ecs_optimized.id
  instance_type          = var.instance_type
  iam_instance_profile   = aws_iam_instance_profile.ecs_instance.name
  subnet_id              = aws_subnet.private[0].id
  vpc_security_group_ids = [aws_security_group.ecs_host.id]
  key_name               = var.key_pair_name != "" ? var.key_pair_name : null

  user_data = base64encode(<<-EOF
    #!/bin/bash
    # Join ECS cluster
    echo ECS_CLUSTER=${var.ecs_cluster_name} >> /etc/ecs/ecs.config
    echo ECS_ENABLE_CONTAINER_METADATA=true >> /etc/ecs/ecs.config
    # Bắt buộc để dùng awsvpc network mode với nhiều task trên cùng instance
    echo ECS_ENABLE_TASK_ENI=true >> /etc/ecs/ecs.config

    # Swap 2GB — chống OOM kill
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab

    # Mount EBS volume cho Qdrant data
    # Chờ volume attach (/dev/xvdf) trước khi mount
    while [ ! -e /dev/xvdf ]; do sleep 1; done
    mkdir -p /qdrant/storage
    # Chỉ format nếu volume chưa có filesystem (bảo toàn data khi reboot)
    blkid /dev/xvdf || mkfs.ext4 /dev/xvdf
    mount /dev/xvdf /qdrant/storage
    echo '/dev/xvdf /qdrant/storage ext4 defaults,nofail 0 2' >> /etc/fstab
  EOF
  )

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
  }

  tags = {
    Project = var.project_name
    Name    = "${var.project_name}-ecs-host-new"
  }

  depends_on = [aws_subnet.private, aws_security_group.ecs_host]
}

# EBS volume riêng cho Qdrant data (không nằm trên root volume)
# AZ phải match với EC2 instance AZ
resource "aws_ebs_volume" "qdrant_data" {
  availability_zone = var.availability_zones[0]
  size              = 20
  type              = "gp3"

  # Bật encryption nếu muốn (không ảnh hưởng performance đáng kể)
  # encrypted = true

  tags = {
    Project = var.project_name
    Name    = "${var.project_name}-qdrant-data"
  }
}

# Attach EBS volume vào EC2 instance ở device /dev/xvdf
resource "aws_volume_attachment" "qdrant_data" {
  device_name = "/dev/xvdf"
  volume_id   = aws_ebs_volume.qdrant_data.id
  instance_id = aws_instance.ecs_host_new.id
}
