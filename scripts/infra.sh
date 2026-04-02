#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/infra.sh — Build / update AWS infrastructure via Terraform
#
# Usage:
#   ./scripts/infra.sh           # plan + apply
#   ./scripts/infra.sh plan      # chỉ xem plan, không apply
#   ./scripts/infra.sh destroy   # xóa toàn bộ infra (cẩn thận!)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
INFRA_DIR="$PROJECT_ROOT/infrastructure"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

info()    { echo -e "${CYAN}[infra]${NC} $*"; }
success() { echo -e "${GREEN}[infra]${NC} $*"; }
warn()    { echo -e "${YELLOW}[infra]${NC} $*"; }
error()   { echo -e "${RED}[infra]${NC} $*" >&2; exit 1; }

# ── Kiểm tra prerequisites ────────────────────────────────────────────────────
command -v terraform >/dev/null 2>&1 || error "terraform chưa cài. Xem: https://developer.hashicorp.com/terraform/install"
command -v aws >/dev/null 2>&1       || error "aws cli chưa cài."

info "Kiểm tra AWS credentials..."
aws sts get-caller-identity --query 'Account' --output text >/dev/null 2>&1 \
  || error "AWS credentials chưa được cấu hình. Chạy: aws configure"

ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)
info "Account: $ACCOUNT_ID"

# ── Vào thư mục infra ─────────────────────────────────────────────────────────
cd "$INFRA_DIR"

CMD="${1:-apply}"

case "$CMD" in
  plan)
    info "Chạy terraform plan..."
    terraform init -upgrade -input=false
    terraform plan -input=false
    ;;

  apply)
    info "Chạy terraform init..."
    terraform init -upgrade -input=false

    info "Chạy terraform plan..."
    terraform plan -input=false -out=tfplan

    echo ""
    warn "Sắp apply các thay đổi trên. Nhấn Enter để tiếp tục hoặc Ctrl+C để hủy."
    read -r

    info "Chạy terraform apply..."
    terraform apply -input=false tfplan
    rm -f tfplan

    echo ""
    success "Infra đã cập nhật thành công!"
    echo ""
    info "Outputs:"
    terraform output
    ;;

  destroy)
    warn "⚠️  CẢNH BÁO: Lệnh này sẽ XÓA TOÀN BỘ infrastructure!"
    warn "Bao gồm: EC2, ECS, DynamoDB, S3 frontend, CloudFront, ECR, SSM, IAM..."
    echo ""
    read -r -p "Gõ 'yes-destroy' để xác nhận: " CONFIRM
    [[ "$CONFIRM" == "yes-destroy" ]] || { info "Hủy."; exit 0; }

    terraform init -input=false
    terraform destroy -input=false
    ;;

  *)
    error "Lệnh không hợp lệ: $CMD. Dùng: plan | apply | destroy"
    ;;
esac
