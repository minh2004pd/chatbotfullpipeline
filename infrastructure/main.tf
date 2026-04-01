terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Uncomment để lưu state trên S3 thay vì local (recommended cho team)
  # backend "s3" {
  #   bucket = "your-terraform-state-bucket"
  #   key    = "memrag/terraform.tfstate"
  #   region = "ap-southeast-2"
  # }
}

provider "aws" {
  region = var.aws_region
}

# Lấy account ID hiện tại (dùng trong IAM policy)
data "aws_caller_identity" "current" {}
