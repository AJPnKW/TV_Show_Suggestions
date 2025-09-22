$ErrorActionPreference = "Stop"
Set-Location "C:\Users\Lenovo\PROJECTS\TV_Show_Suggestions"

function Ok($m){ Write-Host "[OK]  $m" -ForegroundColor Green }
function Info($m){ Write-Host "[INFO] $m" -ForegroundColor Cyan }

# 1) Create/ensure standard folders
"data","outputs","logs","assets","templates","scripts","backups" | %{
  if(-not (Test-Path $_)){ New-Item -ItemType Directory $_ | Out-Null; Ok "Created $_" }
}

# 2) Move Streamlit artifacts to backups\streamlit_YYYYMMDD
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$bak = Join-Path "backups" "streamlit_$stamp"
New-Item -ItemType Directory $bak | Out-Null

$toMove = @(
  ".\scripts\app.py",
  ".\scripts\backend.py",
  ".\scripts\Start-TVGuide.ps1",
  ".\Start-TVGuide.bat"
) | ? { Test-Path $_ }

foreach($p in $toMove){
  Move-Item -Force $p $bak
  Ok "Moved $p -> $bak"
}

# 3) Overwrite requirements.txt for PyQt6 stack
@"
PyQt6>=6.6
requests>=2.31
Jinja2>=3.1
"@ | Set-Content -Encoding UTF8 .\requirements.txt
Ok "Wrote requirements.txt (PyQt6, requests, Jinja2)"

# 4) Ensure root BAT launches the PS script in scripts\
@"
@echo off
setlocal
cd /d "%~dp0"
start "TV Show Suggestions" powershell -NoProfile -NoExit -ExecutionPolicy Bypass -File ".\scripts\Start-PyQt6.ps1"
endlocal
"@ | Set-Content -Encoding ASCII .\Start-PyQt6.bat
Ok "Refreshed Start-PyQt6.bat"

# 5) Ensure scripts\Start-PyQt6.ps1 exists and points at scripts\main.py
@"
`$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent `"$PSCommandPath`")  # scripts\
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
"@ | Set-Content -Encoding UTF8 .\scripts\Start-PyQt6.ps1
Ok "Ensured scripts\Start-PyQt6.ps1"

# 6) Sanity: confirm template + data/config.json exist
if(-not (Test-Path .\templates\page.html.j2)){ throw "Missing templates\page.html.j2" }
if(-not (Test-Path .\data\config.json)){
  @"
{
  "output_path": "C:\\Users\\Lenovo\\PROJECTS\\TV_Show_Suggestions\\outputs\\TV-Guide-Dad-Sandra_OFFLINE.html",
  "theme": {"brand":"#11b3a4","card":"#EAF7F4","bg":"#0e1e21"}
}
"@ | Set-Content -Encoding UTF8 .\data\config.json
  Ok "Created data\\config.json"
}

Ok "Finalize complete. Launch with Start-PyQt6.bat"
