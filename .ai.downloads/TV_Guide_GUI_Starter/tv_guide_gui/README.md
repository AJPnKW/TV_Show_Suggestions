# TV Guide GUI (Streamlit)

Generate an **offline, single-page HTML** TV guide with **embedded TMDB posters** and your custom layout.

## Quick start
1) Install Python 3.9+ and deps:
   ```bash
   pip install -r requirements.txt
   ```
2) Set keys (system variables you already use are supported):
   - TMDB: `TMDB_API_KEY` or `API_TMDB_KEY`  (or v4 bearer `API_TMDB_TOKEN`)
   - OMDb: `OMDB_API_KEY` or `API_OMDB_KEY`   (optional; RT critic %)
3) Run the GUI:
   ```bash
   streamlit run app.py
   ```

**Flow**
- **Shows** → paste or upload list, validate against TMDB, pick exact matches, assign category.
- **Fetch / Cache** → pulls metadata + posters and **stores base64 in SQLite** so you never re-download unless you refresh.
- **Links** → optional per-show personal page URL (e.g., your Google Drive show page).
- **Design & Generate** → outputs a fully **offline HTML** file (posters embedded).

This project stores `tmdb_id`, `imdb_id` (when available), and has a slot for `tvmaze_id` so you can cross-link sources later.
