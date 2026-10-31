[CmdletBinding()]
param(
    [string]$ConfigPath = ''
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'App-Runtime.ps1')
$runtime = Get-AppRuntime
if (-not $ConfigPath) { $ConfigPath = $runtime.Config }
$projectRoot = $runtime.Root
$pythonPath = $runtime.Console

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
        $moduleArgs = $runtime.ModuleArgs
        & $pythonPath @moduleArgs --config $resolvedConfig refresh
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
