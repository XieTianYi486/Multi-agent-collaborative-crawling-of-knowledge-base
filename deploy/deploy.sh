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
# libgl1/libglib2.0-0：OCR（RapidOCR/opencv）运行依赖；libgomp1：FAISS 运行依赖；curl：健康检查
apt-get install -y python3.10-venv nginx curl libgl1 libglib2.0-0 libgomp1
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

echo "==> 4/7 调整 .env（关闭 DEBUG、重新生成密钥与管理员密码、开启验证码、固定 FAISS 向量后端）"
cd "$APP_DIR/backend"
if [[ ! -f .env ]]; then
  cp .env.example .env
fi
# 一次性生成全部安全生产配置；最后只输出新管理员密码供捕获
NEW_ADMIN_PW=$(python3 - <<'PY'
from pathlib import Path
import secrets

path = Path('.env')
lines = path.read_text(encoding='utf-8').splitlines()

new_admin_pw = secrets.token_urlsafe(12)
pending = {
    "DEBUG": "false",
    "SECRET_KEY": secrets.token_urlsafe(48),
    "JWT_SECRET_KEY": secrets.token_urlsafe(48),
    "ADMIN_PASSWORD": new_admin_pw,
    "CAPTCHA_ENABLED": "true",
    # 生产安全自检不得豁免
    "SKIP_SAFETY_CHECK": "false",
    # 交付的向量索引是 FAISS 格式；Ubuntu 22.04 的 SQLite 版本下 auto 会改选 ChromaDB，
    # 导致稠密检索落到空集合，必须显式固定为 FAISS
    "VECTOR_BACKEND": "faiss",
}
seen = set()
out = []
for line in lines:
    stripped = line.strip()
    key = line.split("=", 1)[0].strip() if ("=" in line and not stripped.startswith("#")) else None
    if key in pending:
        out.append(f"{key}={pending[key]}")
        seen.add(key)
        continue
    out.append(line)
for key, value in pending.items():
    if key not in seen:
        out.append(f"{key}={value}")
path.write_text("\n".join(out) + "\n", encoding="utf-8")
print(new_admin_pw)
PY
)
if [[ -z "$NEW_ADMIN_PW" ]]; then
  echo "[ERROR] 生成管理员密码失败"
  exit 1
fi
chown kb:kb .env
chmod 600 .env

echo "==> 5/7 安装 Python 依赖（首次约 3-8 分钟）"
sudo -u kb bash -c 'cd /opt/kb/backend && python3 -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install -r requirements.txt'

echo "==> 5.5/7 轮换数据库中的默认弱口令管理员（幂等）"
# 随包分发的数据库里 admin 的哈希可能是 admin123：改 .env 不影响库内已存在的用户，
# 必须把库内仍为已知弱口令的管理员密码轮换为新生成的强密码
sudo -u kb "$APP_DIR/backend/.venv/bin/python" - <<'PY'
from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.db.sqlite import SessionLocal
from app.models.user import User

WEAK_PASSWORDS = ("admin123", "change-this-password", "123456", "admin", "password")

db = SessionLocal()
try:
    admin = db.query(User).filter(User.username == settings.ADMIN_USERNAME).first()
    if admin is None:
        print("[deploy] 管理员账号不存在，首次启动时会自动创建")
    elif any(verify_password(pw, admin.password_hash) for pw in WEAK_PASSWORDS):
        admin.password_hash = hash_password(settings.ADMIN_PASSWORD)
        db.commit()
        print("[deploy] 已把弱口令管理员轮换为 .env 中配置的新密码")
    else:
        print("[deploy] 管理员密码非默认弱口令，保持不变")
finally:
    db.close()
PY

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

echo "==> 等待后端启动并做健康检查"
HEALTHY=0
for _i in $(seq 1 15); do
  sleep 2
  if curl -sf --max-time 5 http://127.0.0.1:8001/api/health >/dev/null; then
    HEALTHY=1
    break
  fi
done
if [[ "$HEALTHY" -ne 1 ]]; then
  echo "[ERROR] 后端健康检查失败！请查看日志：journalctl -u kb -n 80 --no-pager"
  systemctl --no-pager -l status kb | head -n 12 || true
  exit 1
fi

IP=$(curl -s --max-time 5 ifconfig.me || hostname -I | awk '{print $1}')
echo ""
echo "部署完成，访问：http://${IP}/"
echo "管理员账号：admin"
echo "管理员初始密码：${NEW_ADMIN_PW}（请登录后立即修改，并妥善保存）"
