$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent "C:\Users\Lenovo\PROJECTS\TV_Show_Suggestions\scripts\Finalize-PyQt6.ps1")  # scripts\
Set-Location ..\

if (-not (Test-Path .\.venv)) { python -m venv .venv }
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip | Out-Null
pip install -r requirements.txt | Out-Null

Write-Host "[INFO] Starting PyQt6 GUI..." -ForegroundColor Cyan
python .\scripts\main.py

Write-Host ""
Write-Host "App exited. Press Enter to close this window..." -ForegroundColor Cyan
Read-Host
