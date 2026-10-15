param(
    [string]$PythonExe = "",
    [ValidateSet("tiny", "base", "small", "medium", "large-v3-turbo")]
    [string]$WhisperModel = "small",
    [switch]$SkipModels
)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
if (-not $PythonExe) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $PythonExe = (& py -3.12 -c "import sys; print(sys.executable)")
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $PythonExe = (Get-Command python).Source
    }
}
if (-not $PythonExe) { throw "Install Python 3.12 x64 from python.org, then run setup.ps1 again." }
& $PythonExe -c "import sys; assert sys.version_info[:2] == (3,12) and sys.maxsize > 2**32, 'Python 3.12 x64 required'"
if ($LASTEXITCODE -ne 0) { throw "Python 3.12 x64 required" }
if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    & $PythonExe -m venv --without-pip .venv
    if ($LASTEXITCODE -ne 0) { throw "Creating virtual environment failed" }
}
$AppPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
# Use the bootstrap interpreter's pip to support embedded Python runtimes too.
& $PythonExe -m pip --python $AppPython install -r requirements-lock.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }
if (-not $SkipModels) {
    & $AppPython tools\download_models.py --whisper $WhisperModel
    if ($LASTEXITCODE -ne 0) { throw "Model download failed; rerun setup.ps1 to resume" }
}
Write-Host "Setup finished. Run start.cmd. See drivers/README.md for open-source microphone routing."
