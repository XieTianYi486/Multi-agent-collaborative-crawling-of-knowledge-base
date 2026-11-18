#!/usr/bin/env bash
# ============================================================
# 人工智能学院教学知识库 - 服务器端增量更新脚本
# 用法：
#   sudo bash deploy/update.sh [/tmp/kb_update.tar.gz]
#   sudo bash deploy/update.sh --backup                # 仅手动备份一份
#   sudo bash deploy/update.sh --rollback-latest        # 回滚到最近一份备份
#   sudo bash deploy/update.sh --rollback 20261118-143022
#   sudo bash deploy/update.sh --dry-run [pkg]          # 只打印将要执行的动作
#
# 说明：
#   - 正常更新：解压 → 重启 → 健康检查；失败自动回滚
#   - 备份目录 /opt/backups/kb/，保留最近 3 份
#   - .venv、.env、运行期数据库与 uploads 不纳入部署包与备份
# ============================================================
set -euo pipefail

# 允许通过环境变量覆盖，方便 staging 复用同一个脚本
APP_DIR="${KB_APP_DIR:-/opt/kb}"
BACKUP_ROOT="${KB_BACKUP_ROOT:-/opt/backups/$(basename "$APP_DIR")}"
SERVICE_NAME="${KB_SERVICE:-kb}"
SERVICE_USER="${KB_USER:-kb}"
HEALTH_URL="${KB_HEALTH_URL:-http://127.0.0.1:8001/api/health}"
PKG=""
ACTION="update"             # update | backup | rollback | dry-run
ROLLBACK_STAMP=""

# ---------- 参数解析 ----------
for arg in "$@"; do
  case "$arg" in
    --backup)            ACTION="backup" ;;
    --rollback-latest)   ACTION="rollback"; ROLLBACK_STAMP="__LATEST__" ;;
    --rollback)          ACTION="rollback" ;;
    --dry-run)           ACTION="dry-run" ;;
    --help|-h)
      sed -n '2,20p' "$0"
      exit 0
      ;;
    *)
      if [[ "$ACTION" == "rollback" && -z "$ROLLBACK_STAMP" && "$arg" != "$PKG" ]]; then
        ROLLBACK_STAMP="$arg"
      elif [[ -z "$PKG" ]]; then
        PKG="$arg"
      fi
      ;;
  esac
done
PKG=${PKG:-/tmp/kb_update.tar.gz}

if [[ $EUID -ne 0 ]]; then
  echo "[ERROR] 请用 root 运行：sudo bash $0" >&2
  exit 1
fi

# ---------- 工具函数 ----------
log()  { echo "==> $(date '+%H:%M:%S') $*"; }
warn() { echo "    [WARN] $*"; }
err()  { echo "    [ERROR] $*" >&2; }
ok()   { echo "    [OK] $*"; }

health_ok() {
  local url=${1:-$HEALTH_URL}
  curl -sf --max-time 5 "$url" >/dev/null 2>&1
}

wait_until_healthy() {
  local max=${1:-15}
  local url=${2:-$HEALTH_URL}
  for ((i=1; i<=max; i++)); do
    sleep 2
    if health_ok "$url"; then
      ok "健康检查通过（第 ${i} 次）"
      return 0
    fi
  done
  return 1
}

prune_old_backups() {
  mkdir -p "$BACKUP_ROOT"
  # 按时间戳降序保留前 3 个，其余 rm -rf
  local keep=${1:-3}
  local count
  count=$(ls -1d "$BACKUP_ROOT"/*/ 2>/dev/null | wc -l || true)
  if (( count > keep )); then
    ls -1dt "$BACKUP_ROOT"/*/ | tail -n +$((keep + 1)) | while read -r old; do
      warn "清理旧备份 $(basename "$old")"
      rm -rf "$old"
    done
  fi
}

take_backup() {
  local stamp
  stamp=$(date '+%Y%m%d-%H%M%S')
  local target="$BACKUP_ROOT/$stamp"
  log "0/5 备份当前运行版本 → $target"

  mkdir -p "$target/frontend/dist" "$target/backend" "$target/deploy"
  [[ -d "$APP_DIR/frontend/dist" ]]   && cp -a "$APP_DIR/frontend/dist/."   "$target/frontend/dist/" || warn "旧版本无前端 dist"
  [[ -d "$APP_DIR/backend/app" ]]     && cp -a "$APP_DIR/backend/app"       "$target/backend/" || warn "旧版本无后端 app"
  [[ -f "$APP_DIR/backend/requirements.txt" ]] && cp "$APP_DIR/backend/requirements.txt" "$target/backend/" || warn "无 requirements.txt"
  [[ -d "$APP_DIR/deploy" ]]          && cp -a "$APP_DIR/deploy/."          "$target/deploy/"
  # 记录当前的 requirements.txt 指纹，用于回滚时判断是否要重装依赖
  if [[ -f "$APP_DIR/backend/requirements.txt" ]]; then
    md5sum "$APP_DIR/backend/requirements.txt" | awk '{print $1}' > "$target/req_md5.txt"
  fi

  prune_old_backups 3
  ok "备份完成：$stamp"
  echo "$stamp"
}

# ---------- 动作：仅备份 ----------
if [[ "$ACTION" == "backup" ]]; then
  take_backup >/dev/null
  exit 0
fi

# ---------- 动作：回滚 ----------
if [[ "$ACTION" == "rollback" ]]; then
  mkdir -p "$BACKUP_ROOT"
  if [[ "$ROLLBACK_STAMP" == "__LATEST__" ]]; then
    ROLLBACK_STAMP=$(ls -1dt "$BACKUP_ROOT"/*/ 2>/dev/null | head -n 1 | xargs -r basename)
  fi
  if [[ -z "$ROLLBACK_STAMP" ]]; then
    err "没有可用备份"
    exit 1
  fi
  bkp_path="$BACKUP_ROOT/$ROLLBACK_STAMP"
  if [[ ! -d "$bkp_path" ]]; then
    err "找不到备份目录：$bkp_path"
    exit 1
  fi

  log "回滚到 $ROLLBACK_STAMP"
  take_backup >/dev/null  # 回滚前先备份当前坏版本，防止误操作

  systemctl stop "${SERVICE_NAME}" || true

  # 还原前端 dist
  rm -rf "$APP_DIR/frontend/dist"
  mkdir -p "$APP_DIR/frontend/dist"
  if [[ -d "$bkp_path/frontend/dist" && -n "$(ls -A "$bkp_path/frontend/dist" 2>/dev/null)" ]]; then
    cp -a "$bkp_path/frontend/dist/." "$APP_DIR/frontend/dist/"
  fi

  # 还原后端 app
  rm -rf "$APP_DIR/backend/app"
  if [[ -d "$bkp_path/backend/app" ]]; then
    cp -a "$bkp_path/backend/app" "$APP_DIR/backend/"
  fi

  # 还原 requirements.txt（如果存在）
  if [[ -f "$bkp_path/backend/requirements.txt" ]]; then
    cp "$bkp_path/backend/requirements.txt" "$APP_DIR/backend/requirements.txt"
    ok "还原 requirements.txt"
  fi

  # 还原 deploy（含 VERSION 标记）
  rm -rf "$APP_DIR/deploy"
  mkdir -p "$APP_DIR/deploy"
  if [[ -d "$bkp_path/deploy" ]]; then
    cp -a "$bkp_path/deploy/." "$APP_DIR/deploy/"
  fi

  # 权限
  chown -R "${SERVICE_USER}:${SERVICE_USER}" "$APP_DIR/backend/app" "$APP_DIR/frontend/dist" "$APP_DIR/deploy"
  chmod 755 "$APP_DIR"
  chmod -R a+rX "$APP_DIR/frontend/dist"

  # 回滚后直接重装依赖，避免 venv 与还原后的 requirements.txt 不一致
  if [[ -f "$APP_DIR/backend/requirements.txt" ]]; then
    warn "回滚后重装依赖以确保 venv 匹配（约 1-3 分钟）"
    sudo -u "${SERVICE_USER}" "$APP_DIR/backend/.venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt" || true
  fi

  log "启动服务并验证"
  systemctl start "${SERVICE_NAME}"
  if wait_until_healthy 20; then
    ok "回滚成功"
    exit 0
  else
    err "回滚后健康检查仍失败，请手动查看：journalctl -u \"${SERVICE_NAME}\" -n 80 --no-pager"
    exit 2
  fi
fi

# ---------- 以下为正常更新 / dry-run ----------
if [[ ! -f "$PKG" ]]; then
  err "找不到更新包 $PKG"
  exit 1
fi

CURRENT_REQ_MD5=""
[[ -f "$APP_DIR/backend/requirements.txt" ]] && CURRENT_REQ_MD5=$(md5sum "$APP_DIR/backend/requirements.txt" | awk '{print $1}')

if [[ "$ACTION" == "dry-run" ]]; then
  log "DRY-RUN 模式：不执行任何改动"
  echo "  - 将备份当前运行版本到 $BACKUP_ROOT/<stamp> （保留最近 3 份）"
  echo "  - 将解压 $PKG 并覆盖 frontend/dist、backend/app、backend/requirements.txt、deploy/"
  echo "  - 如 requirements.txt 指纹变化，将自动 pip install"
  echo "  - 服务停止、内容同步、重启、健康检查"
  echo "  - 健康检查失败时，自动回滚到本次备份"
  echo "  - 回滚命令：sudo bash $0 --rollback-latest"
  exit 0
fi

# 正常更新流程 ----
BACKUP_STAMP=$(take_backup)

log "1/5 解压更新包"
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
tar -xzf "$PKG" -C "$stage"
if [[ ! -f "$stage/frontend/dist/index.html" ]]; then
  err "更新包缺少 frontend/dist/index.html，已中止（未改动线上）"
  exit 1
fi

log "2/5 替换前端 + 覆盖后端"
# 前端整体替换（dist 是完整产物）
rm -rf "$APP_DIR/frontend/dist/assets"
mkdir -p "$APP_DIR/frontend/dist"
cp -a "$stage/frontend/dist/." "$APP_DIR/frontend/dist/"
# 其余内容直接覆盖
cp -a "$stage/." "$APP_DIR/"
chmod 755 "$APP_DIR"

log "3/5 检查依赖变化"
NEW_REQ_MD5=""
[[ -f "$APP_DIR/backend/requirements.txt" ]] && NEW_REQ_MD5=$(md5sum "$APP_DIR/backend/requirements.txt" | awk '{print $1}')
if [[ "$CURRENT_REQ_MD5" != "$NEW_REQ_MD5" ]]; then
  ok "requirements.txt 有变化，安装依赖（约 1-3 分钟）"
  sudo -u "${SERVICE_USER}" "$APP_DIR/backend/.venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt" || {
    err "依赖安装失败，自动回滚"
    systemctl start "${SERVICE_NAME}" 2>/dev/null || true
    bash "$0" --rollback "$BACKUP_STAMP"
    exit 2
  }
else
  ok "依赖未变化，跳过"
fi

chown -R "${SERVICE_USER}:${SERVICE_USER}" "$APP_DIR/backend/app" "$APP_DIR/frontend/dist"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "$APP_DIR/backend/crawler"
mkdir -p "$APP_DIR/backend/crawler/data"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "$APP_DIR/backend/crawler/data"
chmod -R a+rX "$APP_DIR/frontend/dist"
chmod a+rX "$APP_DIR/deploy/materials" || true

log "4/5 同步视频与配套资料"
# 内容同步在服务停掉之后执行（需要停掉 kb 以免读写冲突）
systemctl stop "${SERVICE_NAME}" || true
SYNC_OK=true
if sudo -u "${SERVICE_USER}" env KB_APP_DIR="$APP_DIR" "$APP_DIR/backend/.venv/bin/python" "$APP_DIR/deploy/sync_content.py"; then
  ok "内容同步完成"
else
  warn "内容同步失败（服务仍会启动）"
  SYNC_OK=false
fi

log "5/5 重启并健康检查"
systemctl start "${SERVICE_NAME}"
if wait_until_healthy 20; then
  # 再校验 VERSION 标记，确保前端也被正确替换
  IP=$(curl -s --max-time 5 ifconfig.me 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}')
  echo ""
  ok "更新完成，访问：http://${IP}/"
  ok "发布标记：$(cat "$APP_DIR/deploy/VERSION" 2>/dev/null)"
  echo "提示：前端发版，浏览器强刷（Ctrl+F5）可立即看到新页面。"
  echo "如需回滚：sudo bash $0 --rollback-latest"
  if [[ "$SYNC_OK" == "false" ]]; then
    warn "内容同步失败，请查看 $APP_DIR/deploy/sync_content.py 日志"
  fi
  exit 0
fi

# ---- 健康检查失败，自动回滚 ----
err "健康检查失败，自动回滚到 $BACKUP_STAMP"
systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
bash "$0" --rollback "$BACKUP_STAMP"
ROLLBACK_EXIT=$?
if [[ $ROLLBACK_EXIT -eq 0 ]]; then
  err "自动回滚已完成，请排查问题后重试"
else
  err "自动回滚也失败了！当前运行状态未知"
  err "请登录服务器手动检查 $BACKUP_ROOT/ 并执行回滚"
  exit 3
fi
