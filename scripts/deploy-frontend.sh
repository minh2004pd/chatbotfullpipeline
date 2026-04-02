#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/deploy-frontend.sh — Build React, sync S3, invalidate CloudFront
#
# Usage:
#   ./scripts/deploy-frontend.sh           # build + upload + invalidate
#   ./scripts/deploy-frontend.sh build     # chỉ build (không upload)
#   ./scripts/deploy-frontend.sh upload    # chỉ upload dist/ lên S3 (không build lại)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

# ── Cấu hình — lấy từ terraform output ───────────────────────────────────────
AWS_REGION="ap-southeast-2"
S3_BUCKET="memrag-frontend-860601623933"
CLOUDFRONT_DISTRIBUTION_ID="E17D2MVQHE58HY"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

info()    { echo -e "${CYAN}[frontend]${NC} $*"; }
success() { echo -e "${GREEN}[frontend]${NC} $*"; }
warn()    { echo -e "${YELLOW}[frontend]${NC} $*"; }
error()   { echo -e "${RED}[frontend]${NC} $*" >&2; exit 1; }

# ── Kiểm tra prerequisites ────────────────────────────────────────────────────
command -v node >/dev/null 2>&1 || error "Node.js chưa cài."
command -v npm >/dev/null 2>&1  || error "npm chưa cài."
command -v aws >/dev/null 2>&1  || error "aws cli chưa cài."

# ── Hàm build ─────────────────────────────────────────────────────────────────
do_build() {
  info "Install dependencies..."
  cd "$FRONTEND_DIR"
  npm ci

  info "Build production (VITE_API_BASE_URL='')..."
  # Empty → axios dùng relative URL /api/v1/... → CloudFront proxy đến EC2
  VITE_API_BASE_URL="" npm run build

  success "Build xong: $FRONTEND_DIR/dist/"
}

# ── Hàm upload S3 + invalidate CloudFront ─────────────────────────────────────
do_upload() {
  [[ -d "$FRONTEND_DIR/dist" ]] || error "Chưa có dist/. Chạy build trước."

  info "Kiểm tra AWS credentials..."
  aws sts get-caller-identity --query 'Account' --output text >/dev/null 2>&1 \
    || error "AWS credentials chưa cấu hình. Chạy: aws configure"

  info "Sync assets/* lên S3 (immutable cache 1 năm)..."
  aws s3 sync "$FRONTEND_DIR/dist/" "s3://$S3_BUCKET" \
    --region "$AWS_REGION" \
    --delete \
    --exclude "index.html" \
    --cache-control "public,max-age=31536000,immutable"

  info "Upload index.html (no-cache)..."
  aws s3 cp "$FRONTEND_DIR/dist/index.html" "s3://$S3_BUCKET/index.html" \
    --region "$AWS_REGION" \
    --cache-control "no-cache,no-store,must-revalidate"

  info "Invalidate CloudFront cache..."
  INVALIDATION_ID=$(aws cloudfront create-invalidation \
    --distribution-id "$CLOUDFRONT_DISTRIBUTION_ID" \
    --paths "/*" \
    --query 'Invalidation.Id' \
    --output text)
  info "Invalidation ID: $INVALIDATION_ID"

  success "Frontend đã deploy!"
  success "URL: https://d3qrt08bgfyl3d.cloudfront.net"
}

# ── Main ──────────────────────────────────────────────────────────────────────
CMD="${1:-all}"

case "$CMD" in
  build)
    do_build
    ;;
  upload)
    do_upload
    ;;
  all)
    do_build
    do_upload
    ;;
  *)
    error "Lệnh không hợp lệ: $CMD. Dùng: build | upload | all"
    ;;
esac
