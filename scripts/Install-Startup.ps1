[CmdletBinding(SupportsShouldProcess)]
param([string]$ConfigPath = '')
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'App-Runtime.ps1')
$runtime = Get-AppRuntime
if (-not $ConfigPath) { $ConfigPath = $runtime.Config }
$projectRoot = $runtime.Root
$python = $runtime.Windowless
$config = (Resolve-Path -LiteralPath $ConfigPath).Path
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Run Setup.cmd first.' }
if ($config -match '["\r\n]') { throw 'The configuration path is invalid.' }
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Startup')) 'Google Photos Wallpaper.lnk'
if ($PSCmdlet.ShouldProcess($shortcutPath, 'Start the wallpaper app at Windows sign-in')) {
    $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $python
    $shortcut.Arguments = $runtime.GuiPrefix + '--config "' + $config + '" gui'
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.Description = 'Google Photos Wallpaper'
    $shortcut.Save()
    Write-Output 'Google Photos Wallpaper will open when you sign in to Windows.'
}
