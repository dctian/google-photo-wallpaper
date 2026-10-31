[CmdletBinding()]
param([string]$Python = 'python', [string]$NsisCompiler = '')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Push-Location -LiteralPath $root
try {
    & $Python packaging/runtime_policy.py
    if ($LASTEXITCODE -ne 0) { throw 'The Python runtime does not meet the release security baseline.' }
    & $Python -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency consistency check failed.' }
    & $Python packaging/tray_source.py
    if ($LASTEXITCODE -ne 0) { throw 'Matching tray library source verification failed.' }
    & $Python packaging/prepare.py
    if ($LASTEXITCODE -ne 0) { throw 'Runtime notice preparation failed.' }
    & $Python -m PyInstaller --noconfirm packaging/windows.spec
    if ($LASTEXITCODE -ne 0) { throw 'Application bundle failed.' }
    & $Python packaging/audit_bundle.py
    if ($LASTEXITCODE -ne 0) { throw 'Bundle privacy and source-replacement audit failed.' }
    & '.\dist\GooglePhotoWallpaper\GooglePhotoWallpaper-cli.exe' --self-test
    if ($LASTEXITCODE -ne 0) { throw 'Bundled application self-test failed.' }
    if (-not $NsisCompiler) {
        $tools = Join-Path $root '.state\tools'
        New-Item -ItemType Directory -Path $tools -Force | Out-Null
        $archive = Join-Path $tools 'nsis-3.13.zip'
        $expected = 'ba63dffc4410ee89193e1cb5a41989991bd77c61068da17e3156d136b7b0b3d8'
        if (-not (Test-Path -LiteralPath $archive)) {
            Invoke-WebRequest -Uri 'https://downloads.sourceforge.net/project/nsis/NSIS%203/3.13/nsis-3.13.zip' -OutFile $archive
        }
        if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLower() -ne $expected) { throw 'NSIS checksum mismatch.' }
        $NsisCompiler = Join-Path $tools 'nsis-3.13\makensis.exe'
        if (-not (Test-Path -LiteralPath $NsisCompiler)) { Expand-Archive -LiteralPath $archive -DestinationPath $tools }
    }
    $version = & $Python -c 'from photo_cache import __version__; print(__version__)'
    if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid application version.' }
    $output = Join-Path $root "dist\google-photo-wallpaper-$version-windows-x64-setup.exe"
    & $NsisCompiler "/DVERSION=$version" "/DPAYLOAD=$(Join-Path $root 'dist\GooglePhotoWallpaper')" "/DOUTPUT=$output" 'packaging\installer.nsi'
    if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
    Copy-Item -LiteralPath 'build\runtime-licenses\runtime-inventory.json' -Destination 'dist\runtime-inventory.json' -Force
    Write-Output "Installer ready: $output"
}
finally { Pop-Location }
