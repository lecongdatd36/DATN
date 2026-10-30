[CmdletBinding()]
param([string]$ProjectRoot = '')
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
}
$projectPath = (Resolve-Path -LiteralPath $ProjectRoot).Path
$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
$updatePath = Join-Path $projectPath 'scripts\update_forecast_daily.py'
Set-Location -LiteralPath $projectPath
& $pythonPath $updatePath --source mo_phong
exit $LASTEXITCODE
