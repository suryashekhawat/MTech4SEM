# Start eICU-CRD demo download in the background (PowerShell).
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$OutDir = Join-Path $Root "data\eicu-crd-demo"
$LogFile = Join-Path $OutDir "download.log"
$PidFile = Join-Path $OutDir "download.pid"
$Script = Join-Path $Root "scripts\download_eicu_crd_demo.py"

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

if (Test-Path $PidFile) {
    $oldPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($oldPid -and (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {
        Write-Host "Download already running (PID $oldPid)."
        Write-Host "Log: $LogFile"
        exit 0
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

$python = @("python", "python3", "py") | ForEach-Object {
    if (Get-Command $_ -ErrorAction SilentlyContinue) { $_; break }
} | Select-Object -First 1

if (-not $python) {
    Write-Error "Python not found. Install Python 3 and retry."
}

$proc = Start-Process -FilePath $python -ArgumentList @(
    $Script, "--log-file", $LogFile
) -RedirectStandardOutput $LogFile -RedirectStandardError $LogFile -WindowStyle Hidden -PassThru

$proc.Id | Set-Content $PidFile

Write-Host "eICU-CRD demo download started in background."
Write-Host "  PID:  $($proc.Id)"
Write-Host "  Log:  $LogFile"
Write-Host "  Data: $OutDir"
Write-Host ""
Write-Host "Tail progress:  Get-Content -Wait $LogFile"
