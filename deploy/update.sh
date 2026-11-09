#!/usr/bin/env bash
# ============================================================
# 人工智能学院教学知识库 - 服务器端增量更新脚本
# 用法：sudo bash /opt/kb/deploy/update.sh [/tmp/kb_update.tar.gz]
# 说明：解压更新包（前端 dist、后端 app、内容同步脚本与配套资料），按需装依赖，同步内容后重启服务。
# ============================================================
set -euo pipefail

APP_DIR=/opt/kb
PKG=${1:-/tmp/kb_update.tar.gz}

if [[ $EUID -ne 0 ]]; then
  echo "[ERROR] 请用 root 运行：sudo bash $0"
  exit 1
fi

if [[ ! -f "$PKG" ]]; then
  echo "[ERROR] 找不到更新包 $PKG"
  exit 1
fi

echo "==> 1/5 记录依赖文件指纹"
if [[ -f "$APP_DIR/backend/requirements.txt" ]]; then
  BEFORE=$(md5sum "$APP_DIR/backend/requirements.txt" | awk '{print $1}')
else
  BEFORE=none
fi

echo "==> 2/5 解压更新包"
tar -xzf "$PKG" -C "$APP_DIR"

echo "==> 3/5 检查依赖是否需要重装"
AFTER=$(md5sum "$APP_DIR/backend/requirements.txt" | awk '{print $1}')
if [[ "$BEFORE" != "$AFTER" ]]; then
  echo "    requirements.txt 有变化，安装依赖（约 1-3 分钟）"
  sudo -u kb "$APP_DIR/backend/.venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt"
else
  echo "    依赖未变化，跳过"
fi

chown -R kb:kb "$APP_DIR/backend/app" "$APP_DIR/frontend/dist"
chmod -R a+rX "$APP_DIR/frontend/dist"
chmod a+rX "$APP_DIR/deploy/materials" || true

echo "==> 4/5 同步视频与配套资料（幂等）"
systemctl stop kb || true
if sudo -u kb env KB_APP_DIR="$APP_DIR" "$APP_DIR/backend/.venv/bin/python" "$APP_DIR/deploy/sync_content.py"; then
  echo "    内容同步完成"
else
  echo "    [WARN] 内容同步失败，跳过（服务仍会启动）"
fi

echo "==> 5/5 重启后端服务"
systemctl restart kb
sleep 2
systemctl --no-pager -l status kb | head -n 8 || true

IP=$(curl -s --max-time 5 ifconfig.me || hostname -I | awk '{print $1}')
echo ""
echo "更新完成，访问：http://${IP}/"
echo "提示：前端改为直接发版，浏览器强刷（Ctrl+F5）可立即看到新页面。"
