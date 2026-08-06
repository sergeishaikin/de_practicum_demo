param(
    [switch]$NoCache,
    [string[]]$Service
)
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
$DockerArgs = @("compose", "--env-file", ".env", "-f", "docker-compose.yml", "-f", "docker-compose.extended.yml", "build")
if ($NoCache) { $DockerArgs += "--no-cache" }
if ($Service) { $DockerArgs += $Service }
Write-Host "Building local data platform images..." -ForegroundColor Cyan
docker @DockerArgs
if ($LASTEXITCODE -ne 0) { throw "Image build failed." }
