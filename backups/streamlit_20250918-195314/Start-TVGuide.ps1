$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\Lenovo\PROJECTS\TV_Show_Suggestions'
if (-not (Test-Path .\.venv)) { python -m venv .venv }
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip | Out-Null
pip install -r requirements.txt | Out-Null
# Streamlit entry
streamlit run .\scripts\app.py --server.headless true
