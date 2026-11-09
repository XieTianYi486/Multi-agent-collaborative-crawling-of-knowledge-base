---
name: "kb-deploy-update"
description: "Builds and deploys the Vue + FastAPI app to Aliyun ECS: packages dist and backend/app, restarts kb.service, verifies health. Invoke when user asks to deploy, release, update, 更新服务器, 上线."
---

# 教学知识库 · 服务器更新发布

把本地改动发布到生产环境（阿里云 ECS / Ubuntu 22.04 / Nginx + systemd）。

## 环境信息

| 项 | 值 |
|---|---|
| 服务器 | `root@47.93.4.199` |
| 项目目录 | `/opt/kb`（后端 `/opt/kb/backend`，前端 `/opt/kb/frontend/dist`） |
| 服务 | `kb.service`（uvicorn 127.0.0.1:8001） |
| 访问地址 | `http://47.93.4.199/` |
| 本地入口 | `deploy/update.ps1` |
| 服务端脚本 | `deploy/update.sh`（随更新包上传到 `/opt/kb/deploy/`） |

## 执行流程

### 1. 前置检查

- 工作目录必须是项目根目录（含 `frontend/`、`backend/`、`deploy/`）。
- 确认本地 `frontend/dist/index.html` 存在，或准备执行构建。
- 先判断是否能免密 SSH（决定走「自动执行」还是「让用户手动执行」）：

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=6 root@47.93.4.199 "echo ok"
```

- 返回 `ok` → 走第 2 步，由你直接执行。
- 返回权限错误 → 走第 3 步，把命令交给用户在他自己的终端执行（**不要让工具卡在密码输入**）。

### 2. 自动执行（免密可用时）

```powershell
powershell -ExecutionPolicy Bypass -File deploy\update.ps1
```

参数：
- `-SkipBuild`：只改了后端时跳过前端构建（复用现有 `dist`）。
- `-Remote "root@其他IP"`：换服务器。

脚本内部动作：`npm run build` → `tar` 打包（约 3MB）→ `scp` 到 `/tmp/kb_update.tar.gz` → `ssh` 执行 `update.sh` → 解压 / 比对 `requirements.txt` md5 决定是否装依赖 / 修正权限 / `systemctl restart kb`。

### 3. 交给用户执行（需要密码时）

把下面命令发给用户，让他粘贴到自己终端并输入 root 密码：

```powershell
powershell -ExecutionPolicy Bypass -File deploy\update.ps1
```

然后等他说完成后，你继续做第 4 步的验证（验证可以用公网 HTTP，不需要 SSH）。

### 4. 验证（必做）

```powershell
# 1) 页面可访问
curl.exe -s -o NUL -w "%{http_code}" http://47.93.4.199/

# 2) 后端健康检查
curl.exe -s http://47.93.4.199/api/health

# 3) 前端确实换成了新构建（对比 index.html 引用的 hash 与本地 dist）
Select-String -Path frontend\dist\index.html -Pattern "assets/index-"
```

- 期望：`200`、`{"status":"ok",...}`，且线上 `/` 返回的 index.html 引用与新 `dist` 中的 hash 一致。
- 需要看服务日志时（免密可用）：

```powershell
ssh root@47.93.4.199 "systemctl is-active kb; journalctl -u kb -n 40 --no-pager"
```

## 故障处理

| 现象 | 处理 |
|---|---|
| `kb.service` 启动失败 | 优先看 `journalctl -u kb -n 80`；常见是 `.env` 生产安全自检（DEBUG/JWT_SECRET_KEY/ADMIN_PASSWORD/CAPTCHA） |
| 页面还是旧版 | 让用户 Ctrl+F5；确认 `index.html` 的 `Cache-Control: no-cache` 仍生效 |
| 接口 502 | 后端未起来：`systemctl restart kb` 后立即查日志 |
| 新增依赖报 ImportError | `requirements.txt` 未同步或安装失败，执行 `/opt/kb/backend/.venv/bin/pip install -r requirements.txt` |
| 上传很慢或超时 | 包体过大（误带 `node_modules`/`backend/uploads`）；检查 `tar` 参数 |

## 安全红线

- **绝不**上传或覆盖服务器上的 `backend/.env`、`*.db`、`chroma_data/`、`backend/uploads/`、`node_modules/`。
- 不改动 Nginx 反代配置；若本次确实改了 `deploy/deploy.sh` 中的 Nginx 段，需单独征得用户同意后执行 `nginx -t && systemctl reload nginx`。
- 不执行 `rm -rf /opt/kb`、不重建服务、不修改 systemd 单元，除非用户明确要求。
- 数据库结构变更（新增表/列）要先确认是否已 `init_db()` 幂等兼容，必要时提醒用户备份 `/opt/kb/backend/*.db`。
