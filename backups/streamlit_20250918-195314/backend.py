
import os, re, json, time, base64, sqlite3, logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple
from urllib.parse import urlencode

import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape

# --- Project paths (folders live at project root) ---
import os
SCRIPT_DIR   = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
DATA_DIR     = os.path.join(PROJECT_ROOT, "data")
TEMPLATES_DIR= os.path.join(PROJECT_ROOT, "templates")
DB_PATH = os.path.join(DATA_DIR, "tv_cache.db")

log = logging.getLogger("tvguide")
log.setLevel(logging.INFO)

APP_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(APP_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "tv_cache.db")

def _get_env(names: List[str]) -> Optional[str]:
    for n in names:
        v = os.environ.get(n)
        if v: return v.strip()
    return None

TMDB_KEY    = _get_env(["TMDB_API_KEY","API_TMDB_KEY"])
TMDB_BEARER = _get_env(["API_TMDB_TOKEN","TMDB_BEARER"])
OMDB_KEY    = _get_env(["OMDB_API_KEY","API_OMDB_KEY"])

def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
    CREATE TABLE IF NOT EXISTS shows(
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
    return conn

def norm_title(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())

# ---------------- TMDB ----------------
def tmdb_get(path: str, params: Dict=None):
    url = f"https://api.themoviedb.org/3{path}"
    params = dict(params or {})
    headers = {"User-Agent": "TVGuideGUI/1.0"}
    if TMDB_BEARER:
        headers["Authorization"] = f"Bearer {TMDB_BEARER}"
    elif TMDB_KEY:
        params["api_key"] = TMDB_KEY
    else:
        raise RuntimeError("TMDB key/token missing: set TMDB_API_KEY or API_TMDB_TOKEN")
    r = requests.get(url, params=params, headers=headers, timeout=25)
    r.raise_for_status()
    return r.json()

def tmdb_config():
    j = tmdb_get("/configuration")
    images = j.get("images",{})
    base = images.get("secure_base_url","https://image.tmdb.org/t/p/")
    sizes = images.get("poster_sizes",["w500","w780","original"])
    for s in ("w500","w780","original"):
        if s in sizes: size=s; break
    else: size=sizes[-1]
    return base, size

def tmdb_search(title: str, year: Optional[int], media: str="tv"):
    q = {"query": title}
    if year:
        (q.update({"first_air_date_year": year}) if media=="tv" else q.update({"year": year}))
    j = tmdb_get(f"/search/{media}", q)
    return j.get("results", [])

def tmdb_details(media: str, tmdb_id: int) -> Dict:
    return tmdb_get(f"/{media}/{tmdb_id}", {"append_to_response": "external_ids"})

def download_poster_data_uri(poster_path: str) -> Optional[str]:
    base,size = tmdb_config()
    url = f"{base}{size}{poster_path}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    mime = "image/png" if url.lower().endswith(".png") else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(r.content).decode('ascii')}"

# ---------------- OMDb → RT critic % ----------------
def omdb_rt_value(title: str, year: Optional[int]) -> Optional[str]:
    key = OMDB_KEY
    if not key: return None
    q = {"t": title, "type":"series", "apikey": key}
    if year: q["y"] = str(year)
    r = requests.get("https://www.omdbapi.com/?" + urlencode(q), timeout=20)
    r.raise_for_status()
    j = r.json()
    if j.get("Response")!="True": return None
    for it in j.get("Ratings",[]):
        if it.get("Source")=="Rotten Tomatoes":
            return it.get("Value")
    return None

@dataclass
class ShowInput:
    title: str
    year: Optional[int] = None
    type: str = "tv"
    category: str = "Suggestions for Wayne & Sandra"
    personal_url: Optional[str] = None

def parse_show_line(line: str) -> Optional[ShowInput]:
    s = line.strip()
    if not s or s.startswith("#"): return None
    m = re.match(r'^(.*?)\s*(?:\((\d{4})\))?\s*(?:\[(tv|movie)\])?$', s)
    if not m: return ShowInput(title=s)
    title = m.group(1).strip()
    year  = int(m.group(2)) if m.group(2) else None
    media = m.group(3) or "tv"
    return ShowInput(title, year, media)

def search_choices(title: str, year: Optional[int], media: str):
    res = tmdb_search(title, year, media)
    out = []
    for r in res[:10]:
        name = r.get("name") or r.get("title") or ""
        y = (r.get("first_air_date") or r.get("release_date") or "")[:4]
        out.append((int(r["id"]), f"{name} ({y})"))
    return out

def add_or_update_show(si: ShowInput, tmdb_id: int, category: Optional[str]=None):
    det = tmdb_details(si.type, tmdb_id)
    poster_path = det.get("poster_path")
    poster = download_poster_data_uri(poster_path) if poster_path else None
    desc = det.get("overview") or ""
    network = ""
    if si.type=="tv":
        nets = det.get("networks") or []
        if nets: network = nets[0].get("name","")
    rating = ""  # extend later with content ratings endpoint
    genres = ", ".join([g["name"] for g in det.get("genres",[])])
    release = (det.get("first_air_date") or det.get("release_date") or "")[:4]
    status = det.get("status") or ""
    seasons = det.get("number_of_seasons") or None
    episodes = det.get("number_of_episodes") or None
    imdb_id = None
    ex = det.get("external_ids") or {}
    if ex: imdb_id = ex.get("imdb_id")

    tomato = omdb_rt_value(si.title, si.year)

    now = int(time.time())
    conn = db_conn()
    try:
        conn.execute("""
        INSERT INTO shows(title,title_norm,year,type,tmdb_id,imdb_id,tvmaze_id,network,rating,genres,release,status,
                          seasons,episodes,description,services,poster_data_uri,tomato,popcorn,category,personal_url,last_updated)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(title_norm) DO UPDATE SET
          year=excluded.year,type=excluded.type,tmdb_id=excluded.tmdb_id,imdb_id=excluded.imdb_id,tvmaze_id=excluded.tvmaze_id,
          network=excluded.network,rating=excluded.rating,genres=excluded.genres,release=excluded.release,status=excluded.status,
          seasons=excluded.seasons,episodes=excluded.episodes,description=excluded.description,services=excluded.services,
          poster_data_uri=excluded.poster_data_uri,tomato=excluded.tomato,popcorn=excluded.popcorn,category=excluded.category,
          personal_url=excluded.personal_url,last_updated=excluded.last_updated
        """, (
            si.title, norm_title(si.title), si.year, si.type, tmdb_id, imdb_id, None, network, rating, genres, release,
            status, seasons, episodes, desc, "", poster, tomato, None, category or si.category, si.personal_url, now
        ))
        conn.commit()
    finally:
        conn.close()

def all_shows():
    conn = db_conn()
    try:
        cur = conn.execute("SELECT * FROM shows ORDER BY title")
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

# -------- HTML generation --------
def generate_offline_html(shows: List[dict], outfile: str, theme: Dict=None):
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        enable_async=False
    )
    tpl = env.get_template("page.html.j2")
    html_text = tpl.render(shows=shows, theme=theme or {})
    with open(outfile, "w", encoding="utf-8") as f:
        f.write(html_text)
    return outfile

