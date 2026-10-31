# Uninstall only integration that targets this installation. Preserve user data.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'App-Runtime.ps1')
$runtime = Get-AppRuntime
foreach ($name in @('GooglePhotosWallpaperRefresh', 'GooglePhotosWallpaperRotation')) {
    $task = Get-ScheduledTask -TaskName $name -TaskPath '\' -ErrorAction SilentlyContinue
    if ($task -and @($task.Actions | Where-Object { $_.Execute -eq $runtime.Windowless }).Count -gt 0) {
        Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
    }
}
$path = Join-Path ([Environment]::GetFolderPath('Startup')) 'Google Photos Wallpaper.lnk'
if (Test-Path -LiteralPath $path) {
    $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($path)
    if ($shortcut.TargetPath -eq $runtime.Windowless) { Remove-Item -LiteralPath $path }
}
