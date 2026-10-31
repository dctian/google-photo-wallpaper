$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    python -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)"
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 or later and add it to PATH.' }
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 or later is required.' }
    }
    & '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    if (-not (Test-Path -LiteralPath 'config.json')) {
        & '.\.venv\Scripts\python.exe' -m photo_cache init
        if ($LASTEXITCODE -ne 0) { throw 'Configuration creation failed.' }
    }
    Write-Output 'Ready. Open Start-App.cmd to sign in and choose albums.'
}
finally { Pop-Location }
