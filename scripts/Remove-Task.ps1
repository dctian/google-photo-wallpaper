[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ConfigPath = (Join-Path (Split-Path $PSScriptRoot -Parent) 'config.json'),
    [ValidatePattern('^[^\\/\r\n]{1,128}$')]
    [string]$TaskName = 'GooglePhotosWallpaperRefresh'
)

$ErrorActionPreference = 'Stop'
$existingTask = Get-ScheduledTask -TaskName $TaskName -TaskPath '\' -ErrorAction SilentlyContinue
if (-not $existingTask) {
    Write-Output "No task named $TaskName is installed."
    return
}

# GetFullPath also works after the configuration itself has been removed.
$resolvedConfig = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ConfigPath)
$expectedDescription = 'Google Photos wallpaper cache: ' + $resolvedConfig
if ($existingTask.Description -ne $expectedDescription) {
    throw 'This task belongs to another configuration. Pass its matching -ConfigPath and -TaskName.'
}

if ($PSCmdlet.ShouldProcess($TaskName, 'Remove scheduled wallpaper refresh')) {
    Unregister-ScheduledTask -TaskName $TaskName -TaskPath '\' -Confirm:$false
    Write-Output "Removed $TaskName. Your cached photos and browser profile remain available."
}
