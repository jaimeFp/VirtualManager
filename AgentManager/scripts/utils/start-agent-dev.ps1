```powershell
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$AgentDir = Join-Path $ProjectRoot "AgentManager"

$EnvFile = Join-Path $AgentDir "dev.env"
$AgentScript = Join-Path $AgentDir "src\agent.py"
$Certificate = Join-Path $AgentDir "certs\server.crt"

Write-Host "[VirtualManager] Starting Agent..."

if (-not (Test-Path $EnvFile)) {
    Write-Error "Development environment file not found: $EnvFile"
    exit 1
}

if (-not (Test-Path $AgentScript)) {
    Write-Error "Agent script not found: $AgentScript"
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

if (-not $env:VIRTUALMANAGER_AGENT_TOKEN) {
    Write-Error "VIRTUALMANAGER_AGENT_TOKEN is not defined."
    exit 1
}

Set-Location $AgentDir

Write-Host "[VirtualManager] Agent directory: $AgentDir"

python .\src\agent.py
```