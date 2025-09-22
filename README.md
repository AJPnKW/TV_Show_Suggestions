# TV Show Suggestions — PyQt6 (Offline Page Generator)

A desktop GUI (PyQt6) that:
- Validates shows via **TMDB** (title/year, tv/movie), you choose the exact match
- Caches metadata + **embedded posters** (base64) in **SQLite**
- Lets you add **personal links** per show (e.g., your Google Drive page)
- Generates a **single, offline HTML** page (responsive) with filters and right-rail actions

## Install (Windows)
```powershell
cd C:\Users\Lenovo\PROJECTS\TV_Show_Suggestions
# unzip project contents here so you see main.py, tmdb.py, store.py, templates\, etc.
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python .\main.py
```
Or double‑click **Start-PyQt6.bat** (creates venv, installs deps, runs the app, keeps the console open).

## API keys (environment variables)
- TMDB: `TMDB_API_KEY` or `API_TMDB_KEY`  (OR v4 bearer: `API_TMDB_TOKEN`)
- OMDb (optional for Rotten Tomatoes critic %): `OMDB_API_KEY` or `API_OMDB_KEY`

## Folders
- `data\tv_cache.db` – created on first run (SQLite)
- `data\config.json` – GUI settings (output path, theme)
- `templates\page.html.j2` – offline HTML template
- `outputs\` – generated pages
- `logs\` – rolling log files

## Notes
- Posters are **embedded** as base64 → the final page works offline (e.g., send on Messenger).
- DB stores `tmdb_id`, `imdb_id`, and placeholder `tvmaze_id` for future cross‑refs.
