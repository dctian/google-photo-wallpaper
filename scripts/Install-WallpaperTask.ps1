[CmdletBinding(SupportsShouldProcess)]
param([string]$ConfigPath = '')
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'App-Runtime.ps1')
$runtime = Get-AppRuntime
if (-not $ConfigPath) { $ConfigPath = $runtime.Config }
$projectRoot = $runtime.Root
$resolvedConfig = (Resolve-Path -LiteralPath $ConfigPath).Path
$launcher = Join-Path $PSScriptRoot 'run_hidden.pyw'
$python = $runtime.Windowless
foreach ($path in @($resolvedConfig, $launcher, $python)) {
    if ($path -match '["\r\n]' -or -not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw 'The wallpaper task requires valid installed application paths.'
    }
}
$configData = Get-Content -LiteralPath $resolvedConfig -Raw | ConvertFrom-Json
$interval = 10
if ($null -ne $configData.wallpaper_interval_minutes) { $interval = $configData.wallpaper_interval_minutes }
if ($interval -isnot [int] -and $interval -isnot [long]) { throw 'The wallpaper interval must be a whole number.' }
if ($interval -lt 1 -or $interval -gt 1440) { throw 'Invalid wallpaper interval.' }
$taskName = 'GooglePhotosWallpaperRotation'
$description = 'Synchronized local photo wallpaper rotation: ' + $resolvedConfig
$existing = Get-ScheduledTask -TaskName $taskName -TaskPath '\' -ErrorAction SilentlyContinue
if ($existing -and $existing.Description -ne $description) { throw 'The wallpaper rotation task belongs to another configuration.' }
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$principal = New-ScheduledTaskPrincipal -UserId $sid -LogonType Interactive -RunLevel Limited
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes($interval) -RepetitionInterval (New-TimeSpan -Minutes $interval)
$arguments = $runtime.ScheduledPrefix + '--config "' + $resolvedConfig + '" --wallpaper-next'
$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $projectRoot
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
if ($PSCmdlet.ShouldProcess($taskName, 'Install synchronized wallpaper rotation')) {
    Register-ScheduledTask -TaskName $taskName -TaskPath '\' -Description $description -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
    Write-Output "Installed synchronized wallpaper rotation every $interval minutes."
}
