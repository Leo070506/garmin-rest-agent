param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot '..\config.toml'),
    [string]$PythonPath = (Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe'),
    [string]$MorningAt,
    [string]$WeeklyAt,
    [ValidateSet('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday')]
    [string]$WeeklyDay,
    [switch]$UseCodex,
    [switch]$UpdateExisting,
    [switch]$Install
)
$ErrorActionPreference = 'Stop'
$cfgPath = (Resolve-Path -LiteralPath $ConfigPath).Path
$pyPath = (Resolve-Path -LiteralPath $PythonPath).Path
if ($cfgPath.Contains('"') -or $pyPath.Contains('"')) { throw 'Paths cannot contain quotation marks.' }
$planJson = & $pyPath -m garmin_rest_agent --config $cfgPath schedule-plan
if ($LASTEXITCODE -ne 0) { throw 'Could not read the personalized schedule plan.' }
$plan = ($planJson -join [Environment]::NewLine) | ConvertFrom-Json
if ($plan.collection_method -eq 'browser') {
    if ($Install) { throw 'Browser mode requires a browser-capable Codex automation; raw CLI tasks cannot collect it.' }
    Write-Output 'Browser mode: use a Codex automation with browser access. No Windows CLI tasks previewed or installed.'
    return
}
if ($Install -and -not $plan.preferences_configured) { throw 'Complete setup/configure before installing a schedule.' }
$sha = [System.Security.Cryptography.SHA256]::Create()
try { $hash = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($cfgPath))).Replace('-','').Substring(0,8) }
finally { $sha.Dispose() }
$tasks = @()
foreach ($job in $plan.jobs) {
    if ($job.kind -eq 'morning') {
        $at = if ($MorningAt) { $MorningAt } else { $job.time }
        $tasks += @{ Name = "GarminRest-$hash-Morning"; Kind = 'morning'; At = $at; Zone = $job.timezone }
    } else {
        $at = if ($WeeklyAt) { $WeeklyAt } else { $job.time }
        $day = if ($WeeklyDay) { $WeeklyDay } else { $job.weekday }
        $tasks += @{ Name = "GarminRest-$hash-Weekly"; Kind = 'weekly'; At = $at; Day = $day; Zone = $job.timezone }
    }
}
foreach ($task in $tasks) {
    [void][DateTime]::ParseExact($task.At, 'HH:mm', $null)
    if ($Install) {
        $existing = Get-ScheduledTask -TaskName $task.Name -ErrorAction SilentlyContinue
        if ($existing -and (-not $UpdateExisting -or $existing.Description -ne 'Local Garmin sleep and recovery report')) {
            throw "Task already exists: $($task.Name). Review it before using -UpdateExisting."
        }
    }
}
if ($Install -and $UpdateExisting) {
    # Only the two exact project-specific task names are eligible for cancellation.
    foreach ($knownName in @("GarminRest-$hash-Morning", "GarminRest-$hash-Weekly")) {
        if ($knownName -notin @($tasks | ForEach-Object { $_.Name })) {
            $old = Get-ScheduledTask -TaskName $knownName -ErrorAction SilentlyContinue
            if ($old -and $old.Description -eq 'Local Garmin sleep and recovery report') {
                Unregister-ScheduledTask -TaskName $knownName -Confirm:$false
            }
        }
    }
}
foreach ($task in $tasks) {
    $arguments = '-m garmin_rest_agent --config "' + $cfgPath + '" run --kind ' + $task.Kind
    if ($UseCodex) { $arguments += ' --codex' }
    Write-Output ($task.Name + ' -> ' + $pyPath + ' ' + $arguments + ' @ ' + $task.Day + ' ' + $task.At + ' (profile timezone: ' + $task.Zone + '; Windows triggers use system local time)')
    if (-not $Install) { continue }
    $action = New-ScheduledTaskAction -Execute $pyPath -Argument $arguments -WorkingDirectory (Split-Path $cfgPath)
    if ($task.Kind -eq 'morning') { $trigger = New-ScheduledTaskTrigger -Daily -At $task.At }
    else { $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $task.Day -At $task.At }
    # Run only in the current user's logged-in session; no password or elevated privileges stored.
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $task.Name -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal -Description 'Local Garmin sleep and recovery report' -Force:$UpdateExisting | Out-Null
}
if (-not $Install) { Write-Output 'Preview only. Add -Install to register these tasks. System local time is used.' }
