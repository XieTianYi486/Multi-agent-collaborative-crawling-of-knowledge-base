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

# 发布标记：随包上传，用于确认服务器真的解压了本次内容（前端 index.html 的 hash 不一定每次都变）
$stamp = (Get-Date).ToString("yyyyMMdd-HHmmss")
$stage = Join-Path $env:TEMP "kb_stage"
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path (Join-Path $stage "deploy") -Force | Out-Null
Set-Content -Path (Join-Path $stage "deploy\VERSION") -Value $stamp -Encoding ascii

tar -czf $pkg -C $root frontend/dist backend/app backend/requirements.txt deploy/update.sh deploy/sync_content.py deploy/materials -C $stage deploy/VERSION
if ($LASTEXITCODE -ne 0) { throw "tar packaging failed" }
$size = "{0:N1} MB" -f ((Get-Item $pkg).Length / 1MB)
Write-Host "    package: $pkg ($size)"
scp $pkg "${Remote}:/tmp/kb_update.tar.gz"
if ($LASTEXITCODE -ne 0) { throw "Upload failed, check network / SSH password" }

Write-Host "==> 3/3 Extract and restart on server..." -ForegroundColor Cyan
$remoteOutput = ssh $Remote bash /opt/kb/deploy/update.sh 2>&1
$remoteOutput | ForEach-Object { Write-Host $_ }
if ($LASTEXITCODE -ne 0) { throw "Remote update failed, see output above" }

# 发布后校验：轮询服务器上的发布标记，确认远端确实解压并完成了本次更新
$remoteStamp = ""
for ($i = 0; $i -lt 20; $i++) {
  $remoteStamp = (ssh $Remote "cat /opt/kb/deploy/VERSION 2>/dev/null").Trim()
  if ($remoteStamp -eq $stamp) { break }
  Start-Sleep -Seconds 3
}
if ($remoteStamp -ne $stamp) {
  throw "Verification failed: server VERSION is '$remoteStamp', expected '$stamp'"
}
Write-Host "    verified release: $stamp" -ForegroundColor Green

Write-Host "Done." -ForegroundColor Green
