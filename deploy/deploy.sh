#!/usr/bin/env bash
# ============================================================
# 人工智能学院教学知识库 - Ubuntu 22.04 一键部署脚本
# 用法：sudo bash deploy.sh [/tmp/kb_deploy.tar.gz]
# 说明：脚本会安装 Python/ Nginx、解压项目、建虚拟环境、
#       生成 systemd 服务与 Nginx 反代，并启动后端。
# ============================================================
set -euo pipefail

APP_DIR=/opt/kb
PKG=${1:-/tmp/kb_deploy.tar.gz}

if [[ $EUID -ne 0 ]]; then
  echo "[ERROR] 请用 root 运行：sudo bash $0"
  exit 1
fi

echo "==> 1/7 安装系统依赖"
apt-get update -y
apt-get install -y python3.10-venv nginx
timedatectl set-timezone Asia/Shanghai || true

echo "==> 2/7 解压项目"
if [[ ! -d "$APP_DIR/backend" ]]; then
  if [[ ! -f "$PKG" ]]; then
    echo "[ERROR] 找不到压缩包 $PKG，请先上传到 /tmp"
    exit 1
  fi
  mkdir -p "$APP_DIR"
  tar -xzf "$PKG" -C "$APP_DIR"
fi

echo "==> 3/7 创建运行用户并设置权限"
id kb >/dev/null 2>&1 || useradd -r -m -s /bin/bash kb
mkdir -p "$APP_DIR/backend/logs"
chown -R kb:kb "$APP_DIR"
chmod -R a+rX "$APP_DIR/frontend/dist" 2>/dev/null || true

echo "==> 4/7 调整 .env（关闭 DEBUG、重新生成密钥）"
cd "$APP_DIR/backend"
sed -i 's/^DEBUG=.*/DEBUG=false/' .env
python3 - <<'PY'
from pathlib import Path
import secrets

path = Path('.env')
text = path.read_text(encoding='utf-8')
lines = []
for line in text.splitlines():
    if line.startswith('SECRET_KEY='):
        line = 'SECRET_KEY=' + secrets.token_urlsafe(48)
    elif line.startswith('JWT_SECRET_KEY='):
        line = 'JWT_SECRET_KEY=' + secrets.token_urlsafe(48)
    lines.append(line)
path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
PY
chown kb:kb .env

echo "==> 5/7 安装 Python 依赖（首次约 3-8 分钟）"
sudo -u kb bash -c 'cd /opt/kb/backend && python3 -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install -r requirements.txt'

echo "==> 6/7 配置 systemd 服务"
cat >/etc/systemd/system/kb.service <<'EOF'
[Unit]
Description=AI Teaching KB Backend
After=network.target

[Service]
User=kb
Group=kb
WorkingDirectory=/opt/kb/backend
Environment="PATH=/opt/kb/backend/.venv/bin"
ExecStart=/opt/kb/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1
Restart=always
RestartSec=5
StandardOutput=append:/opt/kb/backend/logs/uvicorn.log
StandardError=append:/opt/kb/backend/logs/uvicorn.err.log

[Install]
WantedBy=multi-user.target
EOF

echo "==> 7/7 配置 Nginx 并启动"
cat >/etc/nginx/sites-available/kb <<'EOF'
server {
    listen 80;
    server_name _;
    root /opt/kb/frontend/dist;
    index index.html;
    client_max_body_size 50m;

    # 静态资源压缩：JS/CSS 体积约可降到原来的 1/3，明显加快首屏
    gzip on;
    gzip_comp_level 5;
    gzip_min_length 1024;
    gzip_proxied any;
    gzip_vary on;
    gzip_types text/plain text/css application/javascript application/json application/xml image/svg+xml;

    # 带 hash 的构建产物长期缓存，index.html 不缓存
    location /assets/ {
        expires 30d;
        add_header Cache-Control "public, immutable";
        try_files $uri =404;
    }

    location = /index.html {
        add_header Cache-Control "no-cache";
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_read_timeout 300s;
    }

    location /static/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
EOF

rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/kb /etc/nginx/sites-enabled/kb
nginx -t
systemctl daemon-reload
systemctl enable --now kb
systemctl reload nginx

echo "==> 等待后端启动"
sleep 3
systemctl --no-pager -l status kb | head -n 12 || true
IP=$(curl -s --max-time 5 ifconfig.me || hostname -I | awk '{print $1}')
echo ""
echo "部署完成，访问：http://${IP}/"
echo "提示：首次登录后请立即修改 admin 默认密码。"
