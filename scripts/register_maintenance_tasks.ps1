[CmdletBinding(SupportsShouldProcess = $true)]
param([string]$ProjectRoot = '', [string]$BackupAt = '02:30', [switch]$IncludeAI)
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) { $ProjectRoot = Split-Path -Parent $PSScriptRoot }
$projectPath = (Resolve-Path -LiteralPath $ProjectRoot).Path
$runnerPath = Join-Path $projectPath 'scripts\run_maintenance.ps1'
if (-not (Test-Path -LiteralPath $runnerPath -PathType Leaf)) { throw 'Maintenance runner was not found.' }
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$powershellPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$tasksToRegister = @(
    @{Name='QLNH-DatabaseBackup'; Task='backup'; Trigger=(New-ScheduledTaskTrigger -Daily -At $BackupAt)},
    @{Name='QLNH-PaymentReconciliation'; Task='reconcile'; Trigger=(New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5))}
)
if ($IncludeAI) { $tasksToRegister += @{Name='QLNH-AIEvaluation'; Task='ai-evaluate'; Trigger=(New-ScheduledTaskTrigger -Daily -At '03:30')} }
foreach ($entry in $tasksToRegister) {
    $existing = Get-ScheduledTask -TaskName $entry.Name -ErrorAction SilentlyContinue
    if ($existing) { throw "Task $($entry.Name) already exists; review it before changing. No overwrite." }
    $arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -ProjectRoot "{1}" -Task {2}' -f $runnerPath,$projectPath,$entry.Task
    $action = New-ScheduledTaskAction -Execute $powershellPath -Argument $arguments -WorkingDirectory $projectPath
    $principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
    if ($PSCmdlet.ShouldProcess($entry.Name, 'Register maintenance under the current Windows account')) {
        Register-ScheduledTask -TaskName $entry.Name -Action $action -Trigger $entry.Trigger -Settings $settings -Principal $principal -Description 'QLNH: maintenance task; Windows account password is not stored.' | Out-Null
    }
}
