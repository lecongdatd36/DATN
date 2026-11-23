[CmdletBinding()]
param(
    [ValidateSet('backup', 'reconcile', 'ai-evaluate')][string]$Task = 'backup',
    [string]$ProjectRoot = ''
)
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) { $ProjectRoot = Split-Path -Parent $PSScriptRoot }
$projectPath = (Resolve-Path -LiteralPath $ProjectRoot).Path
$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
Set-Location -LiteralPath $projectPath
switch ($Task) {
    'backup' { & $pythonPath manage.py backup_database }
    'reconcile' { & $pythonPath manage.py query_pending_zalopay --limit 100 }
    'ai-evaluate' {
        $aiPythonPath = Join-Path $projectPath 'artifacts\ai\venv\Scripts\python.exe'
        & $pythonPath scripts/refresh_apriori.py --ai-python $aiPythonPath --provenance unverified
    }
}
exit $LASTEXITCODE
