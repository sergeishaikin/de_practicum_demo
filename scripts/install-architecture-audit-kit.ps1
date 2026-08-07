<#
.SYNOPSIS
Install (or refresh) the Architecture Audit Kit into this repository.

.DESCRIPTION
The kit lives in its own repository and is not vendored here; this script
syncs a local checkout into the agent-discoverable layout. Both targets need
the same shape, because every SKILL.md reaches its shared material with a
relative `../../references/...` path — so `references/`, `schemas/`, `policy/`
and `assets/` must sit next to `skills/`, not inside it.

  -Target Codex   -> .agents/    (Codex reads $REPO_ROOT/.agents/skills)
  -Target Claude  -> .claude/    (project-level skills for Claude Code)
  -Target Both    -> both of the above

For Claude Code the kit can instead be installed once as a plugin, which
avoids per-project copies entirely:

  /plugin marketplace add <kit-path>
  /plugin install architecture-audit-kit@architecture-audit-kit

Both target directories are gitignored.

.EXAMPLE
./scripts/install-architecture-audit-kit.ps1 -Kit C:\tools\architecture-audit-kit

.EXAMPLE
./scripts/install-architecture-audit-kit.ps1 -Kit C:\tools\architecture-audit-kit -Target Claude
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Kit,

    [ValidateSet("Codex", "Claude", "Both")]
    [string]$Target = "Both"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Parts = @("skills", "references", "schemas", "policy", "assets")

if (-not (Test-Path $Kit)) { throw "Kit not found: $Kit" }
foreach ($part in $Parts) {
    if (-not (Test-Path (Join-Path $Kit $part))) {
        throw "Kit is incomplete, missing '$part': $Kit"
    }
}

$targets = switch ($Target) {
    "Codex"  { @(".agents") }
    "Claude" { @(".claude") }
    "Both"   { @(".agents", ".claude") }
}

foreach ($dir in $targets) {
    Write-Host "Installing Architecture Audit Kit into $dir/" -ForegroundColor Cyan
    foreach ($part in $Parts) {
        $dest = Join-Path $RepoRoot "$dir\$part"
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
        Copy-Item (Join-Path $Kit "$part\*") $dest -Recurse -Force
    }
    $skillCount = (Get-ChildItem "$RepoRoot\$dir\skills" -Recurse -Filter SKILL.md).Count
    Write-Host "  $skillCount skills installed" -ForegroundColor Green
}

Write-Host ""
Write-Host "The deterministic CLI is separate; install it from the kit checkout:" -ForegroundColor Yellow
Write-Host "  py -m pip install -e `"$Kit`"    # then: aak --version"
