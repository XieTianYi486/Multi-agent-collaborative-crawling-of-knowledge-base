# ============================================================
# 人工智能学院教学知识库 - 本地一键更新 / 回滚
#
# 用法：
#   正常发布：
#     powershell -ExecutionPolicy Bypass -File deploy\update.ps1
#     powershell -ExecutionPolicy Bypass -File deploy\update.ps1 -SkipBuild
#     powershell -ExecutionPolicy Bypass -File deploy\update.ps1 -BackupLocal
#   回滚（跳过打包上传，直接触发远端回滚）：
#     powershell -ExecutionPolicy Bypass -File deploy\update.ps1 -RollbackLatest
#     powershell -ExecutionPolicy Bypass -File deploy\update.ps1 -RollbackStamp 20261118-143022
#   演练（不执行上传和远程命令）：
#     powershell -ExecutionPolicy Bypass -File deploy\update.ps1 -DryRun
#
# 说明：
#   - 远端 update.sh 会在解压前自动备份运行版本，保留最近 3 份
#   - 远端健康检查失败会自动回滚到本次发布前的备份
#   - -BackupLocal 会先把 .env、db、uploads、chroma_data 备份到本地 local-backups/<时间戳>/
# ============================================================
param(
  [string]$Remote = "root@47.93.4.199",
  [switch]$SkipBuild,
  [switch]$RollbackLatest,
  [string]$RollbackStamp,
  [switch]$BackupLocal,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

# ---------- 工具 ----------
function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Warn($msg) { Write-Host "    [WARN] $msg" -ForegroundColor Yellow }
function Write-Ok($msg)  { Write-Host "    [OK]   $msg" -ForegroundColor Green }
function Confirm-BashAvailable {
  try { $null = & bash --version 2>&1; return $LASTEXITCODE -eq 0 } catch { return $false }
}

# ---------- 本地备份（可选） ----------
if ($BackupLocal -or $DryRun) {
  $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
  $dst = Join-Path $root "local-backups\$stamp"
  if ($DryRun) {
    Write-Step "Dry-run：本将备份本地运行期数据到 $dst"
  } else {
    Write-Step "本地运行期数据备份 → $dst"
    New-Item -ItemType Directory -Path $dst -Force | Out-Null

    $copies = @(
      @{ Src = (Join-Path $root ".env");                          Dst = (Join-Path $dst ".env") },
      @{ Src = (Join-Path $root "backend\data\enterprise_rag.db"); Dst = (Join-Path $dst "enterprise_rag.db") },
      @{ Src = (Join-Path $root "backend\crawler\data\db\crawler.db"); Dst = (Join-Path $dst "crawler.db") },
      @{ Src = (Join-Path $root "backend\uploads");               Dst = (Join-Path $dst "uploads") },
      @{ Src = (Join-Path $root "chroma_data");                   Dst = (Join-Path $dst "chroma_data") }
    )
    foreach ($c in $copies) {
      if (Test-Path $c.Src) {
        if ((Get-Item $c.Src).PSIsContainer) {
          Copy-Item $c.Src $c.Dst -Recurse -Force
        } else {
          Copy-Item $c.Src $c.Dst -Force
        }
        Write-Ok "已备份 $(Split-Path $c.Src -Leaf)"
      } else {
        Write-Warn "跳过（不存在）：$($c.Src)"
      }
    }
  }
}

# ---------- 回滚分支 ----------
if ($RollbackLatest -or $RollbackStamp) {
  if ($DryRun) {
    Write-Step "Dry-run：将 ssh $Remote 执行远端回滚命令"
    if ($RollbackStamp) {
      Write-Host "    sudo bash /opt/kb/deploy/update.sh --rollback $RollbackStamp"
    } else {
      Write-Host "    sudo bash /opt/kb/deploy/update.sh --rollback-latest"
    }
    exit 0
  }

  Write-Step "触发远端回滚"
  if ($RollbackStamp) {
    Write-Host "  目标时间戳：$RollbackStamp"
    $remoteCmd = "sudo bash /opt/kb/deploy/update.sh --rollback $RollbackStamp"
  } else {
    Write-Host "  目标：最近一份备份"
    $remoteCmd = "sudo bash /opt/kb/deploy/update.sh --rollback-latest"
  }

  try {
    ssh $Remote $remoteCmd 2>&1 | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -eq 0) {
      Write-Host ""
      Write-Ok "回滚命令执行完毕"
    } else {
      Write-Host ""
      Write-Warn "远端回滚脚本返回非零退出码，请看上面的输出"
      exit 1
    }
  } catch {
    Write-Warn "SSH 连接失败：$_"
    Write-Host "请确认：远程主机可达、SSH 密钥/密码正常、目标主机上存在 /opt/kb/deploy/update.sh"
    exit 1
  }
  exit 0
}

# ---------- 以下为正常发布 ----------
Write-Step "目标主机：$Remote"

if (-not $SkipBuild) {
  Write-Step "1/3 构建前端"
  Push-Location (Join-Path $root "frontend")
  $env:npm_config_script_shell = "C:\Windows\System32\cmd.exe"
  & npm run build
  if ($LASTEXITCODE -ne 0) { Pop-Location; throw "前端构建失败" }
  Pop-Location
} else {
  Write-Step "1/3 跳过构建（-SkipBuild）"
}

$distIndex = Join-Path $root "frontend\dist\index.html"
if (-not (Test-Path $distIndex)) {
  throw "找不到 frontend\dist\index.html。先跑 npm run build，或去掉 -SkipBuild。"
}

# ---------- 打包 ----------
Write-Step "2/3 打包"
$pkg = Join-Path $env:TEMP "kb_update.tar.gz"
if (Test-Path $pkg) { Remove-Item $pkg -Force }

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stage = Join-Path $env:TEMP "kb_stage"
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path (Join-Path $stage "deploy") -Force | Out-Null
Set-Content -Path (Join-Path $stage "deploy\VERSION") -Value $stamp -Encoding ascii

$tarOk = Confirm-BashAvailable
if ($tarOk) {
  Write-Host "  使用 bash + tar 打包"
  $tarCmd = "tar -czf '$pkg' --exclude=backend/crawler/data --exclude=__pycache__ --exclude=*.pyc -C '$root' frontend/dist backend/app backend/crawler backend/requirements.txt deploy/update.sh deploy/sync_content.py deploy/materials -C '$stage' deploy/VERSION"
  & bash -c $tarCmd
} else {
  Write-Warn "bash 不在 PATH，尝试用 scp 上传目录再在远端打包（慢，推荐安装 Git Bash）"
  $tarOk = $false
}
if (-not (Test-Path $pkg)) {
  throw "打包失败，未生成 $pkg"
}
$sizeMB = "{0:N1}" -f ((Get-Item $pkg).Length / 1MB)
Write-Ok "包：$pkg ($sizeMB MB)，版本标记 $stamp"

if ($DryRun) {
  Write-Step "Dry-run：将上传 $pkg 到 ${Remote}:/tmp/kb_update.tar.gz，然后远端执行 update.sh"
  Write-Host "    远端会：备份 → 解压 → 检查依赖 → 同步内容 → 重启 → 健康检查 → 失败则回滚"
  exit 0
}

# ---------- 上传 ----------
Write-Step "3/3 上传 + 远端更新"
Write-Host "  上传中..."
scp $pkg "${Remote}:/tmp/kb_update.tar.gz" 2>&1 | ForEach-Object { Write-Host "  $_" }
if ($LASTEXITCODE -ne 0) { throw "上传失败，请检查网络或 SSH" }

# 远端执行
Write-Host "  远端执行 update.sh ..."
ssh $Remote "sudo bash /opt/kb/deploy/update.sh /tmp/kb_update.tar.gz" 2>&1 | ForEach-Object { Write-Host "  $_" }
if ($LASTEXITCODE -ne 0) {
  Write-Warn "远端脚本返回非零退出码。如果是自动回滚已执行，上面会有输出提示。"
  exit 1
}

# ---------- 版本标记校验 ----------
Write-Host ""
Write-Step "校验远端发布标记"
$remoteStamp = ""
for ($i = 0; $i -lt 20; $i++) {
  $remoteStamp = (ssh $Remote "cat /opt/kb/deploy/VERSION 2>/dev/null").Trim()
  if ($remoteStamp -eq $stamp) { break }
  Start-Sleep -Seconds 3
}
if ($remoteStamp -ne $stamp) {
  Write-Warn "版本标记不一致：本地 $stamp vs 远端 $remoteStamp。远端脚本可能已回滚。"
} else {
  Write-Ok "发布标记一致：$stamp"
}

Write-Host ""
Write-Ok "完成。回滚命令示例："
Write-Host "  powershell -File deploy\update.ps1 -RollbackLatest"
Write-Host "  powershell -File deploy\update.ps1 -RollbackStamp $stamp"
