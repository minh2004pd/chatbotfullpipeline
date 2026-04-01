resource "aws_ecr_repository" "backend" {
  name                 = var.ecr_repository_name
  image_tag_mutability = "MUTABLE" # cho phép overwrite tag "latest"

  image_scanning_configuration {
    scan_on_push = true # tự động scan vulnerabilities khi push
  }

  tags = {
    Project = var.project_name
  }
}

# Giữ tối đa 10 image, xóa cũ hơn tự động
resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Giữ 10 image gần nhất"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}
