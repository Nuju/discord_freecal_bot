$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "[1/5] Python を確認しています..."
$pythonCommand = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCommand = @("py", "-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCommand = @("python")
} else {
    throw "Python が見つかりません。Python 3.11 以上をインストールしてください。"
}

function Invoke-Python {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    if ($pythonCommand.Count -gt 1) {
        & $pythonCommand[0] $pythonCommand[1] @Arguments
    } else {
        & $pythonCommand[0] @Arguments
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Python コマンドが失敗しました (exit=$LASTEXITCODE)"
    }
}

Write-Host "[2/5] 仮想環境を準備しています..."
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Invoke-Python -Arguments @("-m", "venv", ".venv")
}
$venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

Write-Host "[3/5] 依存ライブラリをインストールしています..."
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip の更新に失敗しました。" }
& $venvPython -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "依存ライブラリのインストールに失敗しました。" }

Write-Host "[4/5] 自動テストを実行しています..."
& $venvPython -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "自動テストに失敗しました。" }

Write-Host "[5/5] フリカレ mem230522 の 2026年8月を実取得します..."
& $venvPython freecal_cli.py 230522 --month 2026-08 --pretty
if ($LASTEXITCODE -ne 0) { throw "フリカレの実取得に失敗しました。" }

Write-Host ""
Write-Host "検証が完了しました。上の JSON に event_count と events が表示されていれば取得成功です。"
