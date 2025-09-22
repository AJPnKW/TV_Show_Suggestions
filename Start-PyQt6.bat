@echo off
setlocal
cd /d "%~dp0"
start "TV Show Suggestions" powershell -NoProfile -NoExit -ExecutionPolicy Bypass -File ".\scripts\Start-PyQt6.ps1"
endlocal
