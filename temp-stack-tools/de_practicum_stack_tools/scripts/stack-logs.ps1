param(
    [string]$Service,
    [ValidateRange(1, 10000)]
    [int]$Tail = 200,
    [switch]$NoFollow
)
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
$DockerArgs = @("compose", "--env-file", ".env", "-f", "docker-compose.yml", "-f", "docker-compose.extended.yml", "logs", "--tail", "$Tail")
if (-not $NoFollow) { $DockerArgs += "--follow" }
if ($Service) { $DockerArgs += $Service }
docker @DockerArgs
if ($LASTEXITCODE -ne 0) { throw "Failed to read stack logs." }
