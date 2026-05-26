[CmdletBinding()]
param(
    [string]$DistroName = "Ubuntu-22.04"
)

$ErrorActionPreference = "Stop"

function Require-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)) {
        throw "Please run this script from an elevated PowerShell window."
    }
}

Require-Admin

Write-Host "[1/5] Enabling WSL optional feature..."
dism.exe /online /Enable-Feature /FeatureName:Microsoft-Windows-Subsystem-Linux /All /NoRestart

Write-Host "[2/5] Enabling Virtual Machine Platform..."
dism.exe /online /Enable-Feature /FeatureName:VirtualMachinePlatform /All /NoRestart

Write-Host "[3/5] Installing/updating Store WSL package..."
if (Get-Command winget.exe -ErrorAction SilentlyContinue) {
    winget install --id Microsoft.WSL --source winget --accept-package-agreements --accept-source-agreements --silent
} else {
    $kernelMsi = Join-Path $env:TEMP "wsl_update_x64.msi"
    Invoke-WebRequest -Uri "https://wslstorestorage.blob.core.windows.net/wslblob/wsl_update_x64.msi" -OutFile $kernelMsi
    Start-Process msiexec.exe -ArgumentList "/i", $kernelMsi, "/qn", "/norestart" -Wait
}

Write-Host "[4/5] Setting WSL default version to 2..."
wsl --set-default-version 2

Write-Host "[5/5] Installing $DistroName..."
wsl --install -d $DistroName --no-launch

Write-Host ""
Write-Host "WSL2 setup requested. Please restart Windows, launch $DistroName once to finish initialization, then run setup.bat again."
