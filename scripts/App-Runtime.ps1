# Shared path resolution; never embed the build machine's directories.
function Get-AppRuntime {
    $resourceRoot = Split-Path $PSScriptRoot -Parent
    $installedRoot = Split-Path $resourceRoot -Parent
    $cli = Join-Path $installedRoot 'GooglePhotoWallpaper-cli.exe'
    $gui = Join-Path $installedRoot 'GooglePhotoWallpaper.exe'
    if ((Test-Path -LiteralPath $cli -PathType Leaf) -and (Test-Path -LiteralPath $gui -PathType Leaf)) {
        return [pscustomobject]@{
            Root = $installedRoot; Console = $cli; Windowless = $gui
            ModuleArgs = @(); ScheduledPrefix = '--run-task '; GuiPrefix = ''
            Config = (Join-Path $env:LOCALAPPDATA 'GooglePhotosWallpaper\config.json')
        }
    }
    return [pscustomobject]@{
        Root = $resourceRoot
        Console = (Join-Path $resourceRoot '.venv\Scripts\python.exe')
        Windowless = (Join-Path $resourceRoot '.venv\Scripts\pythonw.exe')
        ModuleArgs = @('-m', 'photo_cache')
        ScheduledPrefix = ('"' + (Join-Path $PSScriptRoot 'run_hidden.pyw') + '" ')
        GuiPrefix = '-m photo_cache '
        Config = (Join-Path $resourceRoot 'config.json')
    }
}
