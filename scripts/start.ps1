# VaultMind startup — starts all three required processes concurrently.
# Usage: npm run vaultmind:start  (Windows / PowerShell)
# Requires: Docker Desktop, Python 3.11+, Node/npm

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "=== VaultMind: starting all processes ===" -ForegroundColor Cyan

# 1. Redis via docker compose (idempotent)
Write-Host "[1/3] Starting Redis..." -ForegroundColor Yellow
try {
    docker compose up -d
    Write-Host "      Redis started via Docker" -ForegroundColor Green
} catch {
    Write-Host "      WARNING: Docker not found or failed. Start Redis manually." -ForegroundColor Red
}

# 2. Python watcher
Write-Host "[2/3] Starting Python watcher (vaultmind-pipeline)..." -ForegroundColor Yellow
$VaultRoot = if ($env:VAULTMIND_VAULT_ROOT) { $env:VAULTMIND_VAULT_ROOT } else { Join-Path $RepoRoot "vault" }
New-Item -ItemType Directory -Force -Path (Join-Path $VaultRoot "nodes") | Out-Null
$env:VAULTMIND_VAULT_ROOT = $VaultRoot
$PythonExe = "python"
$watcher = Start-Process $PythonExe -ArgumentList "-m vaultmind.watcher" -PassThru -NoNewWindow
Write-Host "      Watcher PID: $($watcher.Id)" -ForegroundColor Green

# 3. Next.js dev server
Write-Host "[3/3] Starting Next.js dev server on port 3000..." -ForegroundColor Yellow
$env:REPO_ROOT = $RepoRoot
$nextjs = Start-Process cmd -ArgumentList "/c npm run dev" -WorkingDirectory (Join-Path $RepoRoot "webapp") -PassThru -NoNewWindow
Write-Host "      Next.js PID: $($nextjs.Id)" -ForegroundColor Green

Write-Host ""
Write-Host "=== All processes started ===" -ForegroundColor Cyan
Write-Host "  Redis:   port 6379 (Docker)"
Write-Host "  Watcher: PID $($watcher.Id)"
Write-Host "  Next.js: http://localhost:3000 (PID $($nextjs.Id))"
Write-Host ""
Write-Host "Press Ctrl+C to stop all processes." -ForegroundColor Gray

try {
    Wait-Process -Id $watcher.Id, $nextjs.Id
} finally {
    Write-Host "Stopping processes..." -ForegroundColor Yellow
    Stop-Process -Id $watcher.Id, $nextjs.Id -Force -ErrorAction SilentlyContinue
}
