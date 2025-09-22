\
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path .\.venv)) { python -m venv .venv }
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip | Out-Null
pip install -r requirements.txt | Out-Null

Write-Host "[INFO] Starting GUI..." -ForegroundColor Cyan
python .\main.py

Write-Host ""
Write-Host "App exited. Press Enter to close..." -ForegroundColor Cyan
Read-Host
