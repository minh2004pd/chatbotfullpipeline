#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/deploy-all.sh — Full deploy: infra + backend + frontend
#
# Usage:
#   ./scripts/deploy-all.sh              # deploy tất cả
#   ./scripts/deploy-all.sh --skip-infra # bỏ qua terraform (chỉ deploy code)
#   ./scripts/deploy-all.sh --be-only    # chỉ deploy backend
#   ./scripts/deploy-all.sh --fe-only    # chỉ deploy frontend
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[deploy-all]${NC} $*"; }
success() { echo -e "${GREEN}[deploy-all]${NC} $*"; }
header()  { echo -e "\n${BOLD}${CYAN}════════════════════════════════════════${NC}"; echo -e "${BOLD}${CYAN}  $*${NC}"; echo -e "${BOLD}${CYAN}════════════════════════════════════════${NC}"; }

SKIP_INFRA=false
BE_ONLY=false
FE_ONLY=false

for arg in "$@"; do
  case "$arg" in
    --skip-infra) SKIP_INFRA=true ;;
    --be-only)    BE_ONLY=true ;;
    --fe-only)    FE_ONLY=true ;;
  esac
done

START_TIME=$(date +%s)

# ── 1. Infrastructure ─────────────────────────────────────────────────────────
if [[ "$SKIP_INFRA" == false && "$FE_ONLY" == false && "$BE_ONLY" == false ]]; then
  header "1/3  Infrastructure (Terraform)"
  bash "$SCRIPT_DIR/infra.sh" apply
fi

# ── 2. Backend ────────────────────────────────────────────────────────────────
if [[ "$FE_ONLY" == false ]]; then
  header "${BE_ONLY:+1}${BE_ONLY:-2}/$([ "$BE_ONLY" = true ] && echo 1 || echo 3)  Backend (ECR + ECS)"
  bash "$SCRIPT_DIR/deploy-backend.sh" all
fi

# ── 3. Frontend ───────────────────────────────────────────────────────────────
if [[ "$BE_ONLY" == false ]]; then
  header "${FE_ONLY:+1}${FE_ONLY:-3}/$([ "$FE_ONLY" = true ] && echo 1 || echo 3)  Frontend (S3 + CloudFront)"
  bash "$SCRIPT_DIR/deploy-frontend.sh" all
fi

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo ""
success "✓ Deploy hoàn tất trong ${ELAPSED}s"
success "Frontend: https://d3qrt08bgfyl3d.cloudfront.net"
