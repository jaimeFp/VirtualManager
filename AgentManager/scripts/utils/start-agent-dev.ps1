$EnvFile = Join-Path $AgentDir "dev.env"

if (-not (Test-Path $EnvFile)) {
    Write-Error "Development environment file not found: $EnvFile"
    exit 1
}

Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]*)=(.*)$') {
        $Name = $matches[1].Trim()
        $Value = $matches[2].Trim()

        Set-Item -Path "Env:$Name" -Value $Value
    }
}