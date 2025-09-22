@echo off
setlocal
REM === TV Guide GUI launcher (root) ===
REM This batch file launches the PowerShell starter in .\scripts\

REM Jump to the folder this BAT lives in (the project root)
cd /d "%~dp0"

REM Run the PowerShell launcher (handles venv + deps + Streamlit)
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\Start-TVGuide.ps1"

endlocal

pause
