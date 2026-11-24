[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ConfigPath = '',
    [ValidatePattern('^[^\\/\r\n]{1,128}$')]
    [string]$TaskName = 'GooglePhotosWallpaperRefresh',
    [ValidateRange(1, 24)]
    [int]$IntervalHours = 1,
    [ValidateSet('Install', 'Status', 'On', 'Off')]
    [string]$Mode = 'Install'
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'App-Runtime.ps1')
$runtime = Get-AppRuntime
if (-not $ConfigPath) { $ConfigPath = $runtime.Config }
$projectRoot = $runtime.Root
$pythonPath = $runtime.Console
$pythonWindowlessPath = $runtime.Windowless
$launcherPath = Join-Path $PSScriptRoot 'run_hidden.pyw'

$resolvedConfig = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ConfigPath)
$description = 'Google Photos wallpaper cache: ' + $resolvedConfig
$existingTask = Get-ScheduledTask -TaskName $TaskName -TaskPath '\' -ErrorAction SilentlyContinue
if ($Mode -eq 'Status') {
    if (-not $existingTask) { @{ state = 'off'; next_run = $null } | ConvertTo-Json -Compress; return }
    if ($existingTask.Description -ne $description) {
        @{ state = 'other_config'; next_run = $null } | ConvertTo-Json -Compress; return
    }
    $info = $existingTask | Get-ScheduledTaskInfo
    $enabled = $existingTask.Settings.Enabled -and $existingTask.State -ne 'Disabled'
    $next = if ($enabled -and $info.NextRunTime.Year -gt 2000) { $info.NextRunTime.ToUniversalTime().ToString('o') } else { $null }
    @{ state = $(if ($enabled) { 'on' } else { 'off' }); next_run = $next;
       running = ($existingTask.State -eq 'Running'); last_result = $info.LastTaskResult } | ConvertTo-Json -Compress
    return
}
if ($existingTask -and $existingTask.Description -ne $description) {
    throw 'A task with this name belongs to another configuration. Choose a different -TaskName.'
}
if ($Mode -eq 'Off') {
    if ($existingTask -and $PSCmdlet.ShouldProcess($TaskName, 'Turn off hourly photo downloads')) {
        Disable-ScheduledTask -InputObject $existingTask | Out-Null
    }
    Write-Output 'Hourly downloads are off. An already-running batch can finish; manual downloads still work.'
    return
}
if ($Mode -eq 'On' -and $existingTask) {
    if ($PSCmdlet.ShouldProcess($TaskName, 'Turn on hourly photo downloads')) {
        Enable-ScheduledTask -InputObject $existingTask | Out-Null
    }
    Write-Output 'Hourly downloads are on. The existing schedule was preserved.'
    return
}

foreach ($requiredFile in @($pythonPath, $pythonWindowlessPath, $launcherPath, $ConfigPath)) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw 'Setup is incomplete. The virtual environment, hidden launcher, and configuration must exist.'
    }
}
$resolvedConfig = (Resolve-Path -LiteralPath $ConfigPath).Path
foreach ($argumentPath in @($resolvedConfig, $launcherPath)) {
    if ($argumentPath -match '["\r\n]') {
        throw 'Task paths cannot contain quotes or line breaks.'
    }
}

# Read-only local preflight also permits resuming an interrupted collection.
# It does not trigger a cloud download or rewrite the last successful refresh.
Push-Location -LiteralPath $projectRoot
try {
    $moduleArgs = $runtime.ModuleArgs
    & $pythonPath @moduleArgs --config $resolvedConfig status --require-schedulable
    if ($LASTEXITCODE -ne 0) {
        throw 'Choose albums, sign in, and prepare a valid local collection before installing the scheduled task.'
    }
}
finally {
    Pop-Location
}

$description = 'Google Photos wallpaper cache: ' + $resolvedConfig
$existingTask = Get-ScheduledTask -TaskName $TaskName -TaskPath '\' -ErrorAction SilentlyContinue
if ($existingTask -and $existingTask.Description -ne $description) {
    throw 'A task with this name belongs to another configuration. Choose a different -TaskName.'
}

$currentUserSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$principal = New-ScheduledTaskPrincipal -UserId $currentUserSid -LogonType Interactive -RunLevel Limited
$triggerTime = (Get-Date).AddHours($IntervalHours)
# An omitted repetition duration means repeat indefinitely, without an expiry date.
$trigger = New-ScheduledTaskTrigger -Once -At $triggerTime -RepetitionInterval (New-TimeSpan -Hours $IntervalHours)
$actionArguments = $runtime.ScheduledPrefix + '--config "' + $resolvedConfig + '"'
$action = New-ScheduledTaskAction -Execute $pythonWindowlessPath -Argument $actionArguments -WorkingDirectory $projectRoot
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)

if ($PSCmdlet.ShouldProcess($TaskName, "Register wallpaper refresh every $IntervalHours hour(s)")) {
    Register-ScheduledTask -TaskName $TaskName -TaskPath '\' -Description $description `
        -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
    Write-Output "Installed $TaskName every $IntervalHours hour(s), while you are signed in."
}
