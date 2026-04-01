output "ecr_repository_url" {
  description = "ECR repository URL — dán vào app_image hoặc dùng trong CI/CD"
  value       = aws_ecr_repository.backend.repository_url
}

output "ecs_cluster_name" {
  description = "Tên ECS cluster — phải khớp với ECS_CLUSTER trong GitHub Actions"
  value       = aws_ecs_cluster.main.name
}

output "ec2_public_ip" {
  description = "Public IP của EC2 instance"
  value       = aws_instance.ecs_host.public_ip
}

output "ec2_public_dns" {
  description = "Public DNS của EC2 — dùng để test API"
  value       = "http://${aws_instance.ecs_host.public_dns}:${var.container_port}"
}

output "github_actions_access_key_id" {
  description = "AWS_ACCESS_KEY_ID — dán vào GitHub Secrets"
  value       = aws_iam_access_key.github_actions.id
}

output "github_actions_secret_access_key" {
  description = "AWS_SECRET_ACCESS_KEY — dán vào GitHub Secrets"
  value       = aws_iam_access_key.github_actions.secret
  sensitive   = true # dùng: terraform output github_actions_secret_access_key
}

output "frontend_bucket_name" {
  description = "Tên S3 bucket chứa frontend — dán vào GitHub Secret FRONTEND_S3_BUCKET"
  value       = aws_s3_bucket.frontend.id
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID — dán vào GitHub Secret CLOUDFRONT_DISTRIBUTION_ID"
  value       = aws_cloudfront_distribution.frontend.id
}

output "cloudfront_url" {
  description = "URL public của frontend"
  value       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}
