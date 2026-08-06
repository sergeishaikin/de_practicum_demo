$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
$ComposeArgs = @("--env-file", ".env", "-f", "docker-compose.yml", "-f", "docker-compose.extended.yml")
Write-Host "Starting local data platform..." -ForegroundColor Cyan
docker compose @ComposeArgs up -d
if ($LASTEXITCODE -ne 0) { throw "Failed to start the stack." }
Write-Host ""
docker compose @ComposeArgs ps
