$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
$ComposeArgs = @("--env-file", ".env", "-f", "docker-compose.yml", "-f", "docker-compose.extended.yml", "--profile", "*")
Write-Host "Stopping local data platform..." -ForegroundColor Cyan
docker compose @ComposeArgs down
if ($LASTEXITCODE -ne 0) { throw "Failed to stop the stack." }
