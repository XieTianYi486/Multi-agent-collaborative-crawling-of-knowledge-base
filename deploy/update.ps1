# ============================================================
# 人工智能学院教学知识库 - 本地一键更新
# 用法：powershell -ExecutionPolicy Bypass -File deploy\update.ps1
#       powershell -ExecutionPolicy Bypass -File deploy\update.ps1 -SkipBuild
# 说明：本地构建前端 -> 打包上传（dist、后端 app、内容同步脚本与配套资料）-> 服务器解压并重启。
# ============================================================
param(
  [string]$Remote = "root@47.93.4.199",
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if (-not $SkipBuild) {
  Write-Host "==> 1/3 Building frontend..." -ForegroundColor Cyan
  Push-Location (Join-Path $root "frontend")
  $env:npm_config_script_shell = "C:\Windows\System32\cmd.exe"
  npm run build
  if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Frontend build failed" }
  Pop-Location
} else {
  Write-Host "==> 1/3 Skip build, reuse existing dist" -ForegroundColor Yellow
}

if (-not (Test-Path (Join-Path $root "frontend\dist\index.html"))) {
  throw "frontend\dist\index.html not found. Run build first (remove -SkipBuild)."
}

Write-Host "==> 2/3 Packaging and uploading..." -ForegroundColor Cyan
$pkg = Join-Path $env:TEMP "kb_update.tar.gz"
if (Test-Path $pkg) { Remove-Item $pkg -Force }
tar -czf $pkg -C $root frontend/dist backend/app backend/requirements.txt deploy/update.sh deploy/sync_content.py deploy/materials
if ($LASTEXITCODE -ne 0) { throw "tar packaging failed" }
$size = "{0:N1} MB" -f ((Get-Item $pkg).Length / 1MB)
Write-Host "    package: $pkg ($size)"
scp $pkg "${Remote}:/tmp/kb_update.tar.gz"
if ($LASTEXITCODE -ne 0) { throw "Upload failed, check network / SSH password" }

Write-Host "==> 3/3 Extract and restart on server..." -ForegroundColor Cyan
# 线上可能仍是旧版 update.sh（不含内容同步），因此上传后额外执行一次 sync_content.py，
# 保证视频补录与配套资料入库在本轮生效；失败也不阻塞服务启动。
ssh $Remote "bash /opt/kb/deploy/update.sh /tmp/kb_update.tar.gz && systemctl stop kb && (sudo -u kb env KB_APP_DIR=/opt/kb /opt/kb/backend/.venv/bin/python /opt/kb/deploy/sync_content.py || true) && systemctl restart kb"
if ($LASTEXITCODE -ne 0) { throw "Remote update failed, see output above" }

Write-Host "Done." -ForegroundColor Green
