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
# update.sh 已包含解压、按需装依赖、内容同步与重启；这里只负责触发，并把远端输出直接显示出来
ssh $Remote "bash /opt/kb/deploy/update.sh /tmp/kb_update.tar.gz" | Out-Host
if ($LASTEXITCODE -ne 0) { throw "Remote update failed, see output above" }

# 发布后校验：远端 index.html 必须引用本次构建的入口文件，避免“上传成功但没生效”
$localEntry = (Select-String -Path (Join-Path $root "frontend\dist\index.html") -Pattern 'index-[A-Za-z0-9_-]+\.js').Matches[0].Value
$remoteEntry = (ssh $Remote "grep -o 'index-[A-Za-z0-9_-]*\.js' /opt/kb/frontend/dist/index.html | head -1").Trim()
if ($remoteEntry -notlike "*$localEntry*") {
  throw "Verification failed: server serves $remoteEntry, local build is $localEntry"
}
Write-Host "    verified: $remoteEntry" -ForegroundColor Green

Write-Host "Done." -ForegroundColor Green
