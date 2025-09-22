import os, sqlite3, re, time, json
from typing import List, Dict, Optional

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "tv_cache.db")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

def norm_title(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())

def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL;")
    c.execute("PRAGMA synchronous=NORMAL;")
    c.execute("""    CREATE TABLE IF NOT EXISTS shows(
      id INTEGER PRIMARY KEY,
      title TEXT NOT NULL,
      title_norm TEXT NOT NULL UNIQUE,
      year INTEGER,
      type TEXT DEFAULT 'tv',
      tmdb_id INTEGER,
      imdb_id TEXT,
      tvmaze_id INTEGER,
      network TEXT,
      rating TEXT,
      genres TEXT,
      release TEXT,
      status TEXT,
      seasons INTEGER,
      episodes INTEGER,
      description TEXT,
      services TEXT,
      poster_data_uri TEXT,
      tomato TEXT,
      popcorn TEXT,
      category TEXT DEFAULT 'Suggestions for Wayne & Sandra',
      personal_url TEXT,
      last_updated INTEGER
    );
    """)
    return c

def upsert_show(d: Dict):
    c = conn()
    try:
        d = dict(d)
        d.setdefault("type","tv")
        d.setdefault("category","Suggestions for Wayne & Sandra")
        d.setdefault("services","")
        d.setdefault("last_updated", int(time.time()))
        c.execute("""        INSERT INTO shows(title,title_norm,year,type,tmdb_id,imdb_id,tvmaze_id,network,rating,genres,release,status,
                          seasons,episodes,description,services,poster_data_uri,tomato,popcorn,category,personal_url,last_updated)
        VALUES(:title,:title_norm,:year,:type,:tmdb_id,:imdb_id,:tvmaze_id,:network,:rating,:genres,:release,:status,
               :seasons,:episodes,:description,:services,:poster_data_uri,:tomato,:popcorn,:category,:personal_url,:last_updated)
        ON CONFLICT(title_norm) DO UPDATE SET
          year=excluded.year,type=excluded.type,tmdb_id=excluded.tmdb_id,imdb_id=excluded.imdb_id,tvmaze_id=excluded.tvmaze_id,
          network=excluded.network,rating=excluded.rating,genres=excluded.genres,release=excluded.release,status=excluded.status,
          seasons=excluded.seasons,episodes=excluded.episodes,description=excluded.description,services=excluded.services,
          poster_data_uri=excluded.poster_data_uri,tomato=excluded.tomato,popcorn=excluded.popcorn,category=excluded.category,
          personal_url=excluded.personal_url,last_updated=excluded.last_updated
        """, d)
        c.commit()
    finally:
        c.close()

def list_shows() -> List[Dict]:
    c = conn()
    try:
        rows = c.execute("SELECT * FROM shows ORDER BY title").fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()

def delete_show(title: str):
    c = conn()
    try:
        c.execute("DELETE FROM shows WHERE title_norm=?", (norm_title(title),))
        c.commit()
    finally:
        c.close()

def recategorize(title: str, category: str):
    c = conn()
    try:
        c.execute("UPDATE shows SET category=? WHERE title_norm=?", (category, norm_title(title)))
        c.commit()
    finally:
        c.close()

def update_personal_url(title: str, url: str):
    c = conn()
    try:
        c.execute("UPDATE shows SET personal_url=? WHERE title_norm=?", (url, norm_title(title)))
        c.commit()
    finally:
        c.close()

def update_poster_rt(title: str, poster_data_uri: Optional[str], tomato: Optional[str]):
    c = conn()
    try:
        c.execute("UPDATE shows SET poster_data_uri=?, tomato=?, last_updated=? WHERE title_norm=?",
                  (poster_data_uri, tomato, int(time.time()), norm_title(title)))
        c.commit()
    finally:
        c.close()

def load_config() -> Dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"output_path": os.path.join(PROJECT_ROOT, "outputs", "TV-Guide-Dad-Sandra_OFFLINE.html"),
            "theme": {"brand":"#11b3a4","card":"#EAF7F4","bg":"#0e1e21"}}

def save_config(cfg: Dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
