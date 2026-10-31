[CmdletBinding()]
param(
    [string]$ConfigPath = (Join-Path (Split-Path $PSScriptRoot -Parent) 'config.json')
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'

try {
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        throw 'The project virtual environment is missing. Complete the Python setup first.'
    }
    if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
        throw 'The configuration file is missing. Create config.json before refreshing.'
    }
    $resolvedConfig = (Resolve-Path -LiteralPath $ConfigPath).Path
    Push-Location -LiteralPath $projectRoot
    try {
        & $pythonPath -m photo_cache --config $resolvedConfig refresh
        $refreshExitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    exit $refreshExitCode
}
catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
}
