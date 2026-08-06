param(
    [Parameter(Position = 0)]
    [ValidateSet("up", "down", "build", "status", "logs", "reset")]
    [string]$Command = "status",
    [string]$Service,
    [int]$Tail = 200,
    [switch]$NoCache,
    [switch]$NoFollow,
    [switch]$Force
)
$ErrorActionPreference = "Stop"
switch ($Command) {
    "up" { & "$PSScriptRoot\scripts\stack-up.ps1" }
    "down" { & "$PSScriptRoot\scripts\stack-down.ps1" }
    "build" {
        $BuildArgs = @{}
        if ($NoCache) { $BuildArgs["NoCache"] = $true }
        if ($Service) { $BuildArgs["Service"] = @($Service) }
        & "$PSScriptRoot\scripts\stack-build.ps1" @BuildArgs
    }
    "status" { & "$PSScriptRoot\scripts\stack-status.ps1" }
    "logs" {
        $LogArgs = @{ Tail = $Tail }
        if ($Service) { $LogArgs["Service"] = $Service }
        if ($NoFollow) { $LogArgs["NoFollow"] = $true }
        & "$PSScriptRoot\scripts\stack-logs.ps1" @LogArgs
    }
    "reset" {
        $ResetArgs = @{}
        if ($Force) { $ResetArgs["Force"] = $true }
        & "$PSScriptRoot\scripts\stack-reset.ps1" @ResetArgs
    }
}
