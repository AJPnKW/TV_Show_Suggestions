param(
  [string]$Root = "C:\Users\Lenovo\PROJECTS\TV_Show_Suggestions"
)

$ErrorActionPreference = "Stop"
function Info($m){ Write-Host "[INFO] $m" -ForegroundColor Cyan }
function Ok($m){ Write-Host "[OK]   $m" -ForegroundColor Green }
function Warn($m){ Write-Warning $m }
function Ensure-Dir($p){ if(-not (Test-Path $p)){ New-Item -ItemType Directory -Force -Path $p | Out-Null; Ok "Created $p" } }

# 1) Ensure standard folders
$dirs = @("$Root\scripts", "$Root\templates", "$Root\data", "$Root\outputs", "$Root\logs", "$Root\assets")
$dirs | ForEach-Object { Ensure-Dir $_ }

# 2) Move Python + PS files into scripts\
function Move-IfExists($src,$dst){
  if(Test-Path $src){
    $dstDir = Split-Path $dst -Parent
    Ensure-Dir $dstDir
    Move-Item -Force -Path $src -Destination $dst
    Ok "Moved: $src -> $dst"
  }
}
$pyNames = @("main.py","store.py","tmdb.py","generator.py")
foreach($n in $pyNames){ Move-IfExists "$Root\$n" "$Root\scripts\$n" }

# If a PS launcher exists at root, move it into scripts (we’ll rewrite it anyway)
Move-IfExists "$Root\Start-PyQt6.ps1" "$Root\scripts\Start-PyQt6.ps1"

# 3) Patch Python path handling to use PROJECT_ROOT (parent of scripts)
$filesToPatch = @("$Root\scripts\store.py","$Root\scripts\generator.py","$Root\scripts\main.py")
foreach($f in $filesToPatch){
  if(-not (Test-Path $f)) { continue }
  $txt = Get-Content $f -Raw

  # Insert robust path block after the first import section (idempotent)
  if($txt -notmatch "PROJECT_ROOT\s*=\s*os\.path\.abspath\("){
    $txt = $txt -replace "import os(.*)\n", {
@"
import os$($args[0])
# --- Standardized project paths ---
SCRIPT_DIR   = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
DATA_DIR     = os.path.join(PROJECT_ROOT, "data")
TEMPLATES_DIR= os.path.join(PROJECT_ROOT, "templates")
OUTPUTS_DIR  = os.path.join(PROJECT_ROOT, "outputs")
LOGS_DIR     = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

"@
  }
  # Replace any older constants to use standardized ones
  $txt = $txt -replace 'DB_PATH\s*=\s*os\.path\.join\([^)]+\)', 'DB_PATH = os.path.join(DATA_DIR, "tv_cache.db")'
  $txt = $txt -replace 'CONFIG_PATH\s*=\s*os\.path\.join\([^)]+\)', 'CONFIG_PATH = os.path.join(DATA_DIR, "config.json")'
  $txt = $txt -replace 'TEMPLATES_DIR\s*=\s*os\.path\.join\([^)]+\)', 'TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "templates")'
  $txt = $txt -replace 'OUTPUTS_DIR\s*=\s*os\.path\.join\([^)]+\)', 'OUTPUTS_DIR = os.path.join(PROJECT_ROOT, "outputs")'
  # Make sure generator imports still work if used directly
  $txt = $txt -replace 'FileSystemLoader\([^)]+\)', 'FileSystemLoader(TEMPLATES_DIR)'

  Set-Content -Path $f -Value $txt -Encoding UTF8
  Ok "Patched: $([System.IO.Path]::GetFileName($f))"
}

# 4) Write / overwrite the PowerShell launcher in scripts\
$ps1 = "$Root\scripts\Start-PyQt6.ps1"
@"
`$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent `"$PSCommandPath`")  # scripts\

# go to project root
Set-Location ..\

if (-not (Test-Path .\.venv)) { python -m venv .venv }
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip | Out-Null
if (Test-Path .\requirements.txt) { pip install -r requirements.txt | Out-Null } else { pip install PyQt6 requests Jinja2 | Out-Null }

Write-Host "[INFO] Starting GUI..." -ForegroundColor Cyan
python .\scripts\main.py

Write-Host ""
Write-Host "App exited. Press Enter to close..." -ForegroundColor Cyan
Read-Host
"@ | Set-Content -Path $ps1 -Encoding UTF8
Ok "Wrote scripts\Start-PyQt6.ps1"

# 5) Root BAT launcher that keeps console open + calls the PS launcher
$bat = "$Root\Start-PyQt6.bat"
@"
@echo off
setlocal
cd /d "%~dp0"
REM Run the PowerShell launcher in .\scripts\ (venv, deps, app)
start "TV Show Suggestions" powershell -NoProfile -NoExit -ExecutionPolicy Bypass -File ".\scripts\Start-PyQt6.ps1"
endlocal
"@ | Set-Content -Path $bat -Encoding ASCII
Ok "Wrote Start-PyQt6.bat (root)"

Info "Done. Launch with:  Start-PyQt6.bat"
