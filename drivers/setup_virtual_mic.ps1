param([switch]$Install, [switch]$AcceptUsbRestart)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PackageDirectory = Join-Path $ProjectRoot 'downloads'
$Package = Join-Path $PackageDirectory 'USBip-0.9.8.1-x64.exe'
$ExpectedHash = '38cad6d4432b52d5bb9409d9ad03b72fdffc4ada4cd3a48fbeca1a2752a8518a'
$Source = 'https://github.com/vadimgrn/usbip-win2/releases/download/v.0.9.8.1/USBip-0.9.8.1-x64.exe?download=1'
New-Item -ItemType Directory -Force -Path $PackageDirectory | Out-Null
if (-not (Test-Path -LiteralPath $Package)) {
    $TemporaryPackage = $Package + '.download'
    Invoke-WebRequest -Uri $Source -OutFile $TemporaryPackage
    if ((Get-FileHash -LiteralPath $TemporaryPackage -Algorithm SHA256).Hash -ine $ExpectedHash) {
        throw 'Driver download hash mismatch. The package will not be executed.'
    }
    Move-Item -LiteralPath $TemporaryPackage -Destination $Package
}
if ((Get-FileHash -LiteralPath $Package -Algorithm SHA256).Hash -ine $ExpectedHash) {
    throw 'Driver package hash mismatch. The package will not be executed.'
}
$Signature = Get-AuthenticodeSignature -LiteralPath $Package
Write-Host ('Package: ' + $Package)
Write-Host ('Authenticode: ' + $Signature.Status)
if ($Signature.SignerCertificate) { Write-Host ('Signer: ' + $Signature.SignerCertificate.Subject) }
if (-not $Install) {
    Write-Host 'Prepared only. Nothing installed. Installation restarts USB hubs and requires administrator rights.'
    Write-Host 'Read drivers/README.md, then run this script with -Install -AcceptUsbRestart to install.'
    exit 0
}
if (-not $AcceptUsbRestart) { throw 'Installation briefly interrupts USB devices. Pass -AcceptUsbRestart only when ready.' }
if ($Signature.Status -ne 'Valid') { throw 'The installer signature is not valid; refusing automatic installation.' }
$Principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this installation script as Administrator. The main app does not need to run elevated afterward.'
}
$InstallLog = Join-Path $PackageDirectory 'usbip-install.log'
$InstallerProcess = Start-Process -FilePath $Package -ArgumentList @('/SILENT','/NORESTART','/SP-',
    '/COMPONENTS=main,client','/MERGETASKS=!vcredist,!desktopicon',('/LOG="' + $InstallLog + '"')) -Wait -PassThru
if ($InstallerProcess.ExitCode -notin @(0,3010)) { throw ('USB/IP install failed: ' + $InstallerProcess.ExitCode) }
Write-Host 'USB/IP installed. Open Speak Sound and connect the virtual microphone. No boot policy was changed.'
