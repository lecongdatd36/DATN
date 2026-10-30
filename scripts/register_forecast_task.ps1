# Run as the Windows account that owns this project.
[CmdletBinding(SupportsShouldProcess = $true)]
param([string]$ProjectRoot = '')
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
}
$projectPath = (Resolve-Path -LiteralPath $ProjectRoot).Path
$taskName = 'QLNH-DailyOrderForecast-mo_phong'
$taskPath = '\'
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$zone = Get-TimeZone
$vietnamZone = [System.TimeZoneInfo]::FindSystemTimeZoneById('SE Asia Standard Time')
Write-Host "Windows timezone: $($zone.Id) ($($zone.DisplayName))"
if ($zone.BaseUtcOffset -ne $vietnamZone.BaseUtcOffset -or $zone.SupportsDaylightSavingTime) {
    throw 'Windows timezone differs from Vietnam UTC+07:00. No task registered and no system time changed. Set the timezone deliberately or configure a timezone-aware external scheduler.'
}
foreach ($relativePath in @('.venv\Scripts\python.exe', 'artifacts\ai\forecast_venv\Scripts\python.exe', 'scripts\run_forecast_daily.ps1', 'scripts\update_forecast_daily.py')) {
    if (-not (Test-Path -LiteralPath (Join-Path $projectPath $relativePath) -PathType Leaf)) {
        throw "Required file missing: $relativePath"
    }
}
$tasks = @(Get-ScheduledTask -ErrorAction Stop)
$sameName = @($tasks | Where-Object { $_.TaskName -eq $taskName -and $_.TaskPath -eq $taskPath })
$otherUpdates = @($tasks | Where-Object {
    $actionText = ($_.Actions | ForEach-Object { "$($_.Execute) $($_.Arguments)" }) -join ' '
    $isThisTask = $_.TaskName -eq $taskName -and $_.TaskPath -eq $taskPath
    -not $isThisTask -and $actionText -match '(update_forecast_daily\.py|run_forecast_daily\.ps1)'
})
if ($otherUpdates.Count -gt 0) {
    $otherUpdates | Select-Object TaskName, TaskPath, State | Format-Table | Out-Host
    throw 'Another forecast updater task exists. Review/consolidate it before registering; no duplicate was created.'
}
if ($sameName.Count -gt 0) {
    $oldActionText = ($sameName[0].Actions | ForEach-Object { "$($_.Execute) $($_.Arguments)" }) -join ' '
    if ($oldActionText -notmatch '(update_forecast_daily\.py|run_forecast_daily\.ps1)') {
        throw 'Task name is occupied by an unrelated action; refusing to overwrite it.'
    }
}
$runnerPath = Join-Path $projectPath 'scripts\run_forecast_daily.ps1'
$powershellPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -ProjectRoot "{1}"' -f $runnerPath, $projectPath
$action = New-ScheduledTaskAction -Execute $powershellPath -Argument $arguments -WorkingDirectory $projectPath
$triggers = @(
    (New-ScheduledTaskTrigger -Daily -At '07:00'),
    (New-ScheduledTaskTrigger -AtLogOn -User $identity)
)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 15) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$task = New-ScheduledTask -Action $action -Trigger $triggers -Settings $settings -Principal $principal `
    -Description 'QLNH demo order forecast: 07:00 Vietnam; catch up on availability/logon; offline AI; no business-data writes.'
if ($PSCmdlet.ShouldProcess("$taskPath$taskName", 'Register/update one daily 07:00 Vietnam forecast task')) {
    Register-ScheduledTask -TaskName $taskName -TaskPath $taskPath -InputObject $task -Force | Out-Null
    Get-ScheduledTask -TaskName $taskName -TaskPath $taskPath | Select-Object TaskName, State
    Get-ScheduledTaskInfo -TaskName $taskName -TaskPath $taskPath | Select-Object LastRunTime, LastTaskResult, NextRunTime
    Write-Host 'Registered. PC must be powered on and this account logged on. Missed runs catch up when available or at next logon. No password stored.'
}
