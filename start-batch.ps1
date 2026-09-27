$ErrorActionPreference = "Stop"
$batchPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $batchPython)) {
    $batchPython = 'python'
}
& $batchPython (Join-Path $PSScriptRoot 'batch_gui.py')
exit $LASTEXITCODE
