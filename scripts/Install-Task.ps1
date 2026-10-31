[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ConfigPath = (Join-Path (Split-Path $PSScriptRoot -Parent) 'config.json'),
    [ValidatePattern('^[^\\/\r\n]{1,128}$')]
    [string]$TaskName = 'GooglePhotosWallpaperRefresh',
    [ValidateRange(1, 24)]
    [int]$IntervalHours = 1
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$pythonWindowlessPath = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
$launcherPath = Join-Path $PSScriptRoot 'run_hidden.pyw'

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
    & $pythonPath -m photo_cache --config $resolvedConfig status --require-schedulable
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
$actionArguments = '"' + $launcherPath + '" --config "' + $resolvedConfig + '"'
$action = New-ScheduledTaskAction -Execute $pythonWindowlessPath -Argument $actionArguments -WorkingDirectory $projectRoot
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)

if ($PSCmdlet.ShouldProcess($TaskName, "Register wallpaper refresh every $IntervalHours hour(s)")) {
    Register-ScheduledTask -TaskName $TaskName -TaskPath '\' -Description $description `
        -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
    Write-Output "Installed $TaskName every $IntervalHours hour(s), while you are signed in."
}
