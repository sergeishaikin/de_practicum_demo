$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
$ComposeArgs = @("--env-file", ".env", "-f", "docker-compose.yml", "-f", "docker-compose.extended.yml")
Write-Host "Starting local data platform..." -ForegroundColor Cyan
if (-not (docker network inspect de_demo_net 2>$null)) {
    docker network create de_demo_net | Out-Null
}
python scripts/validate_runtime_config.py --env-file .env --profile local
if ($LASTEXITCODE -ne 0) { throw "Runtime configuration validation failed." }
docker compose @ComposeArgs up -d
if ($LASTEXITCODE -ne 0) { throw "Failed to start the stack." }
python scripts/bootstrap_stack.py --env-file .env
if ($LASTEXITCODE -ne 0) { throw "Stack readiness/bootstrap failed." }
Write-Host ""
docker compose @ComposeArgs ps
