# 部署操作手册

## 目录

- [正常发布](#正常发布)
- [Staging 验证（推荐）](#staging-验证推荐)
- [回滚](#回滚)
- [本地数据备份](#本地数据备份)
- [手动备份](#手动备份)
- [新服务器首次部署](#新服务器首次部署)

---

## 正常发布

```powershell
# 完整流程（构建 → 打包 → 上传 → 远端解压 → 重启 → 健康检查 → 版本标记校验）
powershell -ExecutionPolicy Bypass -File deploy\update.ps1

# 跳过前端构建（已有 dist）
powershell -ExecutionPolicy Bypass -File deploy\update.ps1 -SkipBuild

# 发布前先把本地运行期数据备份一份（.env、db、uploads、chroma_data）
powershell -ExecutionPolicy Bypass -File deploy\update.ps1 -BackupLocal

# 演练（不执行上传和远端命令，只打印将要做的事）
powershell -ExecutionPolicy Bypass -File deploy\update.ps1 -DryRun
```

远端 `update.sh` 会自动做：

1. 解压前把当前运行版本（dist、app、requirements.txt、deploy）备份到 `/opt/backups/kb/<时间戳>/`，保留最近 3 份
2. 替换前端 dist、覆盖后端 app 和 deploy 目录
3. 如果 `requirements.txt` 有变化，自动 `pip install`
4. 停止服务、同步内容、重启
5. 轮询 `http://127.0.0.1:8001/api/health` 做健康检查（最多 20 次，每次间隔 2 秒）
6. 健康检查失败 → 自动回滚到本次发布前的备份（先停服务、还原、改权限、重装依赖、重启、再次健康检查）
7. 版本标记（`/opt/kb/deploy/VERSION`）随包上传，本地会轮询远端 VERSION 做最终校验

---

## Staging 验证（推荐）

**强烈建议升级前先在 staging 跑通 3—5 天。** staging 跟生产完全隔离：独立目录、独立用户、独立端口、独立备份。

### 首次搭建 staging（在服务器上执行一次）

```bash
# 1. 建独立用户和目录
sudo useradd -r -m -s /bin/bash kb-staging
sudo mkdir -p /opt/kb-staging
sudo chown -R kb-staging:kb-staging /opt/kb-staging

# 2. 用生产的 deploy.sh 但把目标目录改一下（或者直接手动搭 venv）
sudo -u kb-staging bash -c '
  cd /opt/kb-staging
  python3 -m venv .venv
  .venv/bin/pip install -U pip
'

# 3. 部署一次代码到 /opt/kb-staging/（可以从现有 dist 拷贝，也可以从 git 拉）
#    最简单的做法：把生产的 kb_update.tar.gz 解压到 /opt/kb-staging/

# 4. 装 systemd 和 nginx
sudo cp /opt/kb/deploy/kb-staging.service /etc/systemd/system/
sudo cp /opt/kb/deploy/kb-staging.nginx.conf /etc/nginx/sites-available/kb-staging
sudo ln -sf /etc/nginx/sites-available/kb-staging /etc/nginx/sites-enabled/
sudo systemctl daemon-reload
sudo systemctl enable --now kb-staging
sudo nginx -t && sudo systemctl reload nginx

# 5. 健康检查
curl -sf http://127.0.0.1:8002/api/health && echo OK
# 浏览器访问 staging：http://<服务器IP>:8080/
```

### 后续发布到 staging

```bash
# 在服务器上直接调 staging 包装脚本
sudo bash /opt/kb/deploy/update-staging.sh /tmp/kb_update.tar.gz

# 或者跟生产一样，在本地 PowerShell 上跑——但 update.ps1 目前只支持生产服务，
# 要发布到 staging 建议直接 ssh 上去跑 update-staging.sh
```

staging 的备份独立保存在 `/opt/backups/kb-staging/`，默认也保留最近 3 份。

---

## 回滚

### 远端（已上传到服务器，跳过打包）

```powershell
# 回滚到最近一份备份
powershell -ExecutionPolicy Bypass -File deploy\update.ps1 -RollbackLatest

# 回滚到指定时间戳
powershell -ExecutionPolicy Bypass -File deploy\update.ps1 -RollbackStamp 20261118-143022
```

### 服务器上手动执行

```bash
# 回滚到最近一份
sudo bash /opt/kb/deploy/update.sh --rollback-latest

# 回滚到指定时间戳
sudo bash /opt/kb/deploy/update.sh --rollback 20261118-143022

# 查看当前可用的备份
ls -la /opt/backups/kb/
```

回滚流程（update.sh 自动执行）：

1. 在回滚前先备份当前"坏版本"（防止你回滚错了方向）
2. 停止服务
3. 还原 dist、app、requirements.txt、deploy
4. 改权限
5. 重装依赖（保险起见）
6. 启动服务 + 健康检查

### staging 回滚

```bash
sudo bash /opt/kb/deploy/update-staging.sh --rollback-latest
```

---

## 本地数据备份

运行期数据（git 不跟踪，纯本地/生产），发布前建议备份：

```powershell
# 一键备份到 local-backups/<时间戳>/
powershell -ExecutionPolicy Bypass -File deploy\update.ps1 -BackupLocal

# 备份内容：.env、enterprise_rag.db、crawler.db、uploads/、chroma_data/
```

手动备份示例：

```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dst = "E:\kb-backups\$stamp"
New-Item -ItemType Directory -Path $dst -Force | Out-Null

Copy-Item .env $dst
Copy-Item backend\data\enterprise_rag.db $dst -ErrorAction SilentlyContinue
Copy-Item backend\crawler\data\db\crawler.db $dst -ErrorAction SilentlyContinue
if (Test-Path backend\uploads) { Copy-Item backend\uploads $dst -Recurse }
if (Test-Path chroma_data)    { Copy-Item chroma_data $dst -Recurse }
```

---

## 手动备份

服务器上随时可以手动触发一份备份（不做任何解压/重启）：

```bash
sudo bash /opt/kb/deploy/update.sh --backup
sudo bash /opt/kb/deploy/update-staging.sh --backup
```

查看备份：

```bash
ls -lah /opt/backups/kb/
```

---

## 新服务器首次部署

```bash
# 1. 打包（本地 PowerShell）
cd frontend; npm run build; cd ..
tar -czf kb_deploy.tar.gz --exclude=backend/crawler/data -C . frontend/dist backend backend/requirements.txt deploy
scp kb_deploy.tar.gz root@<IP>:/tmp/

# 2. 服务器上执行一次部署脚本（会自动装依赖、建 venv、配 nginx、启动）
sudo bash deploy.sh /tmp/kb_deploy.tar.gz
```

首次部署后，日常更新统一用 `update.ps1` / `update.sh`，不要再次跑 `deploy.sh`——它会重新配 `.env` 和 systemd，覆盖你的自定义。
