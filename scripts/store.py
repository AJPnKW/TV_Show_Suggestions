# scripts/store.py
import os, json, sqlite3, threading, shutil, datetime

# ---------- Paths locked to project ROOT ----------
SCRIPT_DIR   = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
DATA_DIR     = os.path.join(PROJECT_ROOT, "data")
BACKUP_DIR   = os.path.join(PROJECT_ROOT, "backups")

DB_PATH      = os.path.join(DATA_DIR, "tv_cache.db")
CONFIG_PATH  = os.path.join(DATA_DIR, "config.json")
PERSONAL_JSON= os.path.join(DATA_DIR, "personal_links.json")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

# Legacy/stray locations we might have used earlier
LEGACY_DB_CANDIDATES = [
    os.path.join(SCRIPT_DIR, "data", "tv_cache.db"),
    os.path.join(SCRIPT_DIR, "tv_cache.db"),
    os.path.join(PROJECT_ROOT, "scripts", "data", "tv_cache.db"),
]
LEGACY_CFG_CANDIDATES = [
    os.path.join(SCRIPT_DIR, "data", "config.json"),
    os.path.join(PROJECT_ROOT, "scripts", "data", "config.json"),
]

# ---------- One-time migration of legacy files ----------
def _migrate_legacy():
    try:
        # DB
        if not os.path.exists(DB_PATH):
            for cand in LEGACY_DB_CANDIDATES:
                if os.path.exists(cand):
                    os.makedirs(DATA_DIR, exist_ok=True)
                    shutil.copy2(cand, DB_PATH)
                    break
        # Config
        if not os.path.exists(CONFIG_PATH):
            for cand in LEGACY_CFG_CANDIDATES:
                if os.path.exists(cand):
                    shutil.copy2(cand, CONFIG_PATH)
                    break
    except Exception:
        # Migration best-effort; continue even if copy fails
        pass

_migrate_legacy()

# ---------- DB helpers ----------
_CONN = None
_LOCK = threading.Lock()

def db_conn() -> sqlite3.Connection:
    global _CONN
    if _CONN is None:
        _CONN = sqlite3.connect(DB_PATH, isolation_level=None, check_same_thread=False)
        _CONN.row_factory = sqlite3.Row
        _ensure_schema(_CONN)
    return _CONN

def _ensure_schema(conn: sqlite3.Connection):
    with conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS shows (
            id INTEGER PRIMARY KEY,
            title TEXT UNIQUE,
            title_norm TEXT,
            year INTEGER,
            type TEXT,               -- 'tv' or 'movie'
            tmdb_id INTEGER,
            imdb_id TEXT,
            tvmaze_id INTEGER,
            network TEXT,
            rating TEXT,             -- TV-MA, etc.
            genres TEXT,             -- comma-separated
            release TEXT,            -- year string
            status TEXT,             -- Ongoing/Ended/etc.
            seasons INTEGER,
            episodes INTEGER,
            description TEXT,
            services TEXT,           -- reserved
            poster_data_uri TEXT,    -- base64 data: URI
            tomato TEXT,             -- RT critics %
            popcorn TEXT,            -- RT audience %
            category TEXT,
            personal_url TEXT,
            created_at TEXT,
            updated_at TEXT
        );""")

def _now():
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

# ---------- Title normalization used by main.py ----------
def norm_title(s: str) -> str:
    return (s or "").strip().lower()

# ---------- CRUD the GUI expects ----------
def upsert_show(row: dict):
    """
    Insert or update by title.
    Row keys expected: (title, title_norm, year, type, tmdb_id, imdb_id, tvmaze_id,
    network, rating, genres, release, status, seasons, episodes, description,
    services, poster_data_uri, tomato, popcorn, category, personal_url)
    """
    with _LOCK:
        conn = db_conn()
        with conn:
            conn.execute("""
            INSERT INTO shows (
                title, title_norm, year, type, tmdb_id, imdb_id, tvmaze_id,
                network, rating, genres, release, status, seasons, episodes,
                description, services, poster_data_uri, tomato, popcorn,
                category, personal_url, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(title) DO UPDATE SET
                title_norm=excluded.title_norm,
                year=excluded.year,
                type=excluded.type,
                tmdb_id=excluded.tmdb_id,
                imdb_id=excluded.imdb_id,
                tvmaze_id=excluded.tvmaze_id,
                network=excluded.network,
                rating=excluded.rating,
                genres=excluded.genres,
                release=excluded.release,
                status=excluded.status,
                seasons=excluded.seasons,
                episodes=excluded.episodes,
                description=excluded.description,
                services=excluded.services,
                poster_data_uri=excluded.poster_data_uri,
                tomato=excluded.tomato,
                popcorn=excluded.popcorn,
                category=excluded.category,
                personal_url=excluded.personal_url,
                updated_at=excluded.updated_at
            """, (
                row.get("title"),
                row.get("title_norm") or norm_title(row.get("title") or ""),
                row.get("year"),
                row.get("type"),
                row.get("tmdb_id"),
                row.get("imdb_id"),
                row.get("tvmaze_id"),
                row.get("network"),
                row.get("rating"),
                row.get("genres"),
                row.get("release"),
                row.get("status"),
                row.get("seasons"),
                row.get("episodes"),
                row.get("description"),
                row.get("services"),
                row.get("poster_data_uri"),
                row.get("tomato"),
                row.get("popcorn"),
                row.get("category"),
                row.get("personal_url"),
                _now(),
                _now(),
            ))

def list_shows() -> list[dict]:
    conn = db_conn()
    cur = conn.execute("SELECT * FROM shows ORDER BY title ASC")
    return [dict(r) for r in cur.fetchall()]

def update_personal_url(title: str, url: str):
    with _LOCK:
        conn = db_conn()
        conn.execute("UPDATE shows SET personal_url=?, updated_at=? WHERE title=?",
                     (url, _now(), title))

def update_poster_rt(title: str, poster_data_uri: str | None, tomato: str | None):
    with _LOCK:
        conn = db_conn()
        if poster_data_uri is not None and tomato is not None:
            conn.execute("UPDATE shows SET poster_data_uri=?, tomato=?, updated_at=? WHERE title=?",
                         (poster_data_uri, tomato, _now(), title))
        elif poster_data_uri is not None:
            conn.execute("UPDATE shows SET poster_data_uri=?, updated_at=? WHERE title=?",
                         (poster_data_uri, _now(), title))
        elif tomato is not None:
            conn.execute("UPDATE shows SET tomato=?, updated_at=? WHERE title=?",
                         (tomato, _now(), title))

def delete_show(title: str):
    with _LOCK:
        conn = db_conn()
        conn.execute("DELETE FROM shows WHERE title=?", (title,))

def recategorize(title: str, category: str):
    with _LOCK:
        conn = db_conn()
        conn.execute("UPDATE shows SET category=?, updated_at=? WHERE title=?",
                     (category, _now(), title))

# ---------- Simple JSON config ----------
def load_config() -> dict:
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.loads(f.read() or "{}")
    except Exception:
        pass
    return {}

def save_config(cfg: dict):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg or {}, f, indent=2)
    except Exception:
        pass
