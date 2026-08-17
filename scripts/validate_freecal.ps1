$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "[1/5] Checking Python..."
$pythonCommand = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCommand = @("py", "-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCommand = @("python")
} else {
    throw "Python was not found. Install Python 3.11 or newer."
}

function Invoke-Python {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    if ($pythonCommand.Count -gt 1) {
        & $pythonCommand[0] $pythonCommand[1] @Arguments
    } else {
        & $pythonCommand[0] @Arguments
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed (exit=$LASTEXITCODE)"
    }
}

Write-Host "[2/5] Preparing virtual environment..."
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Invoke-Python -Arguments @("-m", "venv", ".venv")
}
$venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

Write-Host "[3/5] Installing dependencies..."
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade pip." }
& $venvPython -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "Failed to install dependencies." }

Write-Host "[4/5] Running tests..."
& $venvPython -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed." }

Write-Host "[5/5] Fetching Freecal mem230522 for 2026-08..."
& $venvPython freecal_cli.py 230522 --month 2026-08 --pretty
if ($LASTEXITCODE -ne 0) { throw "Freecal live fetch failed." }

Write-Host ""
Write-Host "Validation completed. If JSON with event_count and events is shown above, the live fetch succeeded."
