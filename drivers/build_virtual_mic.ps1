param([string]$GoExe = "")
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $GoExe) {
    $GoCommand = Get-Command go -ErrorAction SilentlyContinue
    if ($GoCommand) { $GoExe = $GoCommand.Source }
}
if (-not $GoExe) {
    $ToolchainDirectory = Join-Path $ProjectRoot 'work/go-toolchain'
    $GoExe = Join-Path $ToolchainDirectory 'go/bin/go.exe'
    if (-not (Test-Path -LiteralPath $GoExe)) {
        New-Item -ItemType Directory -Force -Path $ToolchainDirectory | Out-Null
        $GoArchive = Join-Path $ToolchainDirectory 'go1.27.3.windows-amd64.zip'
        if (-not (Test-Path -LiteralPath $GoArchive)) {
            Invoke-WebRequest -Uri 'https://go.dev/dl/go1.27.3.windows-amd64.zip' -OutFile $GoArchive
        }
        if ((Get-FileHash -LiteralPath $GoArchive -Algorithm SHA256).Hash -ine 'f26081f438319757f8a1b46d7d0b2c5ec7583d4038e485e0aa725cfde7885fff') {
            throw 'Go toolchain archive hash mismatch'
        }
        Expand-Archive -LiteralPath $GoArchive -DestinationPath $ToolchainDirectory -Force
    }
}
$PreviousLocation = Get-Location
try {
    Set-Location -LiteralPath (Join-Path $ProjectRoot 'native/virtual-mic')
    $env:CGO_ENABLED = '0'
    $env:GOTOOLCHAIN = 'local'
    $env:GOCACHE = Join-Path $ProjectRoot 'work/go-cache'
    New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot 'bin') | Out-Null
    & $GoExe test ./...
    if ($LASTEXITCODE -ne 0) { throw 'Virtual microphone backend checks failed' }
    & $GoExe build -trimpath -ldflags '-s -w' -o (Join-Path $ProjectRoot 'bin/speak-sound-mic.exe') ./cmd/speak-sound-mic
    if ($LASTEXITCODE -ne 0) { throw 'Building virtual microphone backend failed' }
    Write-Host 'Built bin/speak-sound-mic.exe. No driver was installed and no system security setting was changed.'
} finally { Set-Location -LiteralPath $PreviousLocation }
