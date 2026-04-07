# ── VPC ──────────────────────────────────────────────────────────────────────
# enable_dns_hostnames + enable_dns_support bắt buộc để Cloud Map DNS hoạt động
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Project = var.project_name
    Name    = "${var.project_name}-vpc"
  }
}

# ── Internet Gateway ──────────────────────────────────────────────────────────
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Project = var.project_name
    Name    = "${var.project_name}-igw"
  }
}

# ── Public Subnets (ALB) ─────────────────────────────────────────────────────
resource "aws_subnet" "public" {
  count = length(var.public_subnet_cidrs)

  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = true

  tags = {
    Project = var.project_name
    Name    = "${var.project_name}-public-${var.availability_zones[count.index]}"
  }
}

# ── Private Subnets (backend + qdrant) ──────────────────────────────────────
resource "aws_subnet" "private" {
  count = length(var.private_subnet_cidrs)

  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = {
    Project = var.project_name
    Name    = "${var.project_name}-private-${var.availability_zones[count.index]}"
  }
}

# ── NAT Gateway (cho private subnets kéo image, gọi external APIs) ───────────
resource "aws_eip" "nat" {
  domain = "vpc"

  tags = {
    Project = var.project_name
    Name    = "${var.project_name}-nat-eip"
  }

  depends_on = [aws_internet_gateway.main]
}

resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id

  tags = {
    Project = var.project_name
    Name    = "${var.project_name}-nat"
  }

  depends_on = [aws_internet_gateway.main]
}

# ── Route Tables ─────────────────────────────────────────────────────────────
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Project = var.project_name
    Name    = "${var.project_name}-rt-public"
  }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }

  tags = {
    Project = var.project_name
    Name    = "${var.project_name}-rt-private"
  }
}

resource "aws_route_table_association" "public" {
  count = length(aws_subnet.public)

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  count = length(aws_subnet.private)

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# ── VPC Endpoints (Gateway — miễn phí) ───────────────────────────────────────
# Tránh data charges qua NAT Gateway cho traffic đến S3 và DynamoDB
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]

  tags = {
    Project = var.project_name
    Name    = "${var.project_name}-vpce-s3"
  }
}

resource "aws_vpc_endpoint" "dynamodb" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.aws_region}.dynamodb"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]

  tags = {
    Project = var.project_name
    Name    = "${var.project_name}-vpce-dynamodb"
  }
}
