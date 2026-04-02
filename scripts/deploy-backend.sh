#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/deploy-backend.sh — Build Docker image, push ECR, deploy ECS
#
# Usage:
#   ./scripts/deploy-backend.sh            # build + push + deploy
#   ./scripts/deploy-backend.sh build      # chỉ build & push ECR (không deploy)
#   ./scripts/deploy-backend.sh deploy     # chỉ deploy (dùng image :latest)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# ── Cấu hình — phải khớp với CI/CD và Terraform ──────────────────────────────
AWS_REGION="ap-southeast-2"
ECR_REPOSITORY="memragbackend"
ECS_CLUSTER="memrag-cluster"
ECS_SERVICE="memrag-backend-service"
ECS_TASK_DEFINITION="memrag-backend"
CONTAINER_NAME="backend"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

info()    { echo -e "${CYAN}[backend]${NC} $*"; }
success() { echo -e "${GREEN}[backend]${NC} $*"; }
warn()    { echo -e "${YELLOW}[backend]${NC} $*"; }
error()   { echo -e "${RED}[backend]${NC} $*" >&2; exit 1; }

# ── Kiểm tra prerequisites ────────────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || error "docker chưa cài hoặc chưa chạy."
command -v aws >/dev/null 2>&1    || error "aws cli chưa cài."

info "Kiểm tra AWS credentials..."
ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text 2>/dev/null) \
  || error "AWS credentials chưa được cấu hình. Chạy: aws configure"
info "Account: $ACCOUNT_ID | Region: $AWS_REGION"

ECR_REGISTRY="$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
IMAGE_TAG="$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo "local")"
FULL_IMAGE="$ECR_REGISTRY/$ECR_REPOSITORY"

CMD="${1:-all}"

# ── Hàm build & push ──────────────────────────────────────────────────────────
do_build() {
  info "Login vào ECR..."
  aws ecr get-login-password --region "$AWS_REGION" \
    | docker login --username AWS --password-stdin "$ECR_REGISTRY"

  info "Build Docker image (tag: $IMAGE_TAG)..."
  docker build \
    -t "$FULL_IMAGE:$IMAGE_TAG" \
    -t "$FULL_IMAGE:latest" \
    "$PROJECT_ROOT/backend"

  info "Push image lên ECR..."
  docker push "$FULL_IMAGE:$IMAGE_TAG"
  docker push "$FULL_IMAGE:latest"

  success "Image đã push: $FULL_IMAGE:$IMAGE_TAG"
}

# ── Hàm deploy ECS ────────────────────────────────────────────────────────────
do_deploy() {
  local image_uri="${2:-$FULL_IMAGE:latest}"

  info "Lấy task definition hiện tại..."
  aws ecs describe-task-definition \
    --task-definition "$ECS_TASK_DEFINITION" \
    --region "$AWS_REGION" \
    --query taskDefinition \
    > /tmp/task-def.json

  info "Inject image mới vào task definition..."
  # Cập nhật image của container backend, giữ nguyên các trường khác
  NEW_TASK_DEF=$(python3 -c "
import json, sys

with open('/tmp/task-def.json') as f:
    td = json.load(f)

# Cập nhật image
for c in td.get('containerDefinitions', []):
    if c['name'] == '$CONTAINER_NAME':
        c['image'] = '$image_uri'
        break

# Xóa các trường read-only mà AWS thêm vào
for field in ['taskDefinitionArn','revision','status','requiresAttributes',
              'compatibilities','registeredAt','registeredBy']:
    td.pop(field, None)

print(json.dumps(td))
")

  info "Register task definition mới..."
  NEW_ARN=$(echo "$NEW_TASK_DEF" | aws ecs register-task-definition \
    --region "$AWS_REGION" \
    --cli-input-json /dev/stdin \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text)
  info "Task definition mới: $NEW_ARN"

  info "Update ECS service..."
  aws ecs update-service \
    --region "$AWS_REGION" \
    --cluster "$ECS_CLUSTER" \
    --service "$ECS_SERVICE" \
    --task-definition "$NEW_ARN" \
    --force-new-deployment \
    --output text --query 'service.serviceName' > /dev/null

  info "Đợi service stable (có thể mất 1-2 phút)..."
  aws ecs wait services-stable \
    --region "$AWS_REGION" \
    --cluster "$ECS_CLUSTER" \
    --services "$ECS_SERVICE"

  success "Deploy hoàn tất! Service đang chạy với image: $image_uri"
  rm -f /tmp/task-def.json
}

# ── Main ──────────────────────────────────────────────────────────────────────
case "$CMD" in
  build)
    do_build
    ;;
  deploy)
    do_deploy "" "$FULL_IMAGE:latest"
    ;;
  all)
    do_build
    do_deploy "" "$FULL_IMAGE:$IMAGE_TAG"
    ;;
  *)
    error "Lệnh không hợp lệ: $CMD. Dùng: build | deploy | all"
    ;;
esac
