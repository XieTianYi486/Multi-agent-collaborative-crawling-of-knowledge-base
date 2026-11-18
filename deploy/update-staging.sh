#!/usr/bin/env bash
# ============================================================
# staging 部署入口（复用 update.sh，只设不同的环境变量）
# 用法：
#   sudo bash deploy/update-staging.sh [/tmp/kb_update.tar.gz]
#   sudo bash deploy/update-staging.sh --backup
#   sudo bash deploy/update-staging.sh --rollback-latest
#   sudo bash deploy/update-staging.sh --dry-run
# ============================================================
set -euo pipefail

export KB_APP_DIR=/opt/kb-staging
export KB_BACKUP_ROOT=/opt/backups/kb-staging
export KB_SERVICE=kb-staging
export KB_USER=kb-staging
export KB_HEALTH_URL=http://127.0.0.1:8002/api/health

exec sudo bash "$(dirname "$0")/update.sh" "$@"
