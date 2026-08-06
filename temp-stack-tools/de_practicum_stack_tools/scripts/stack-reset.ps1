param([switch]$Force)
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
if (-not $Force) {
    Write-Warning "This removes containers, networks, and named volumes."
    Write-Warning "PostgreSQL, MinIO, Airflow logs, and Metabase local data may be deleted."
    $Confirmation = Read-Host "Type RESET to continue"
    if ($Confirmation -ne "RESET") { Write-Host "Reset cancelled."; exit 0 }
}
$ComposeArgs = @("--env-file", ".env", "-f", "docker-compose.yml", "-f", "docker-compose.extended.yml")
Write-Host "Removing stack and persistent volumes..." -ForegroundColor Yellow
docker compose @ComposeArgs down --volumes --remove-orphans
if ($LASTEXITCODE -ne 0) { throw "Stack reset failed." }
Write-Host "Stack and persistent volumes removed." -ForegroundColor Green
