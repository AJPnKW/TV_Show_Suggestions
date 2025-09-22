\
@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [INFO] Creating venv...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Python launcher not found. Ensure Python is installed.
    pause
    exit /b 1
  )
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
if exist "requirements.txt" ( pip install -r requirements.txt ) else ( pip install PyQt6 requests Jinja2 )

echo.
echo [INFO] Starting GUI...
python ".\main.py"

echo.
echo App exited. Press any key to close...
pause >nul
endlocal
