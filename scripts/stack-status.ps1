$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
$ComposeArgs = @("--env-file", ".env", "-f", "docker-compose.yml", "-f", "docker-compose.extended.yml")
docker compose @ComposeArgs ps -a
if ($LASTEXITCODE -ne 0) { throw "Failed to read stack status." }
