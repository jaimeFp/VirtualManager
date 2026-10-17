$ErrorActionPreference = "Stop"

# Script location:
# AgentManager/scripts/utils/start-agent-dev.ps1
#
# Move two directories up to reach AgentManager.
$AgentDir = Split-Path -Parent (
    Split-Path -Parent $PSScriptRoot
)

$EnvFile = Join-Path $AgentDir "dev.env"
$AgentModule = Join-Path $AgentDir "src\virtualmanager_agent\__main__.py"
$Certificate = Join-Path $AgentDir "certs\server.crt"

Write-Host "[VirtualManager] Starting Agent..."
Write-Host "[VirtualManager] Agent directory: $AgentDir"

if (-not (Test-Path $EnvFile)) {
    Write-Error "Development environment file not found: $EnvFile"
    exit 1
}

if (-not (Test-Path $AgentModule)) {
    Write-Error "Agent module not found: $AgentModule"
    exit 1
}

if (-not (Test-Path $Certificate)) {
    Write-Error "Server certificate not found: $Certificate"
    exit 1
}

Get-Content $EnvFile | ForEach-Object {
    $Line = $_.Trim()

    if (
        $Line -and
        -not $Line.StartsWith("#") -and
        $Line.Contains("=")
    ) {
        $Parts = $Line.Split("=", 2)

        $Name = $Parts[0].Trim()
        $Value = $Parts[1].Trim()

        Set-Item -Path "Env:$Name" -Value $Value
    }
}

$AgentConfig = Join-Path $AgentDir "config\agent.json"
$HasAgentCredential = $false
if (Test-Path $AgentConfig) {
    try {
        $SavedConfig = Get-Content -Raw -LiteralPath $AgentConfig | ConvertFrom-Json
        $HasAgentCredential = -not [string]::IsNullOrWhiteSpace($SavedConfig.agent_token)
    } catch {
        $HasAgentCredential = $false
    }
}

if (-not $env:VIRTUALMANAGER_ENROLLMENT_TOKEN -and -not $HasAgentCredential) {
    Write-Error "VIRTUALMANAGER_ENROLLMENT_TOKEN is required until this agent is enrolled."
    exit 1
}

Set-Location $AgentDir
$env:PYTHONPATH = Join-Path $AgentDir "src"

Write-Host "[VirtualManager] Environment loaded."
Write-Host "[VirtualManager] Starting AgentManager..."

python -m virtualmanager_agent
