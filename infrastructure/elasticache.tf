# ── ElastiCache Redis ───────────────────────────────────────────────────────
# Single-node Redis 7.1 for caching (wiki, auth, sessions, documents).
# Uses private subnets + security group restricted to ECS host.

resource "aws_elasticache_subnet_group" "redis" {
  name        = "${var.project_name}-redis-subnet"
  description = "Subnet group for ElastiCache Redis"
  subnet_ids  = aws_subnet.private[*].id

  tags = {
    Project = var.project_name
  }
}

resource "aws_security_group" "redis" {
  name        = "${var.project_name}-redis-sg"
  description = "ElastiCache Redis - allow traffic from ECS host only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Redis from ECS host"
    from_port       = 6379
    to_port         = 6379
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
    Name    = "${var.project_name}-redis-sg"
  }
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id       = "${var.project_name}-redis"
  description                = "MemRAG Redis cache"
  engine                     = "redis"
  engine_version             = var.redis_engine_version
  node_type                  = var.redis_node_type
  num_cache_clusters             = 1
  port                       = 6379
  subnet_group_name          = aws_elasticache_subnet_group.redis.name
  security_group_ids         = [aws_security_group.redis.id]
  automatic_failover_enabled = false
  multi_az_enabled           = false
  at_rest_encryption_enabled = true
  transit_encryption_enabled = false

  tags = {
    Project = var.project_name
    Name    = "${var.project_name}-redis"
  }
}
