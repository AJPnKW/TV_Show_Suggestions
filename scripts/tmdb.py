# scripts/tmdb.py
import os, base64
from typing import Optional, Dict, List, Tuple
from urllib.parse import urlencode, urlparse
import requests

TMDB_KEY    = (os.environ.get("TMDB_API_KEY") or os.environ.get("API_TMDB_KEY") or "").strip()
TMDB_BEARER = (os.environ.get("API_TMDB_TOKEN") or os.environ.get("TMDB_BEARER") or "").strip()
OMDB_KEY    = (os.environ.get("OMDB_API_KEY") or os.environ.get("API_OMDB_KEY") or "").strip()

USER_AGENT = "TVShowSuggestions/1.2 (PyQt6; Windows)"

def _auth():
    headers = {"User-Agent": USER_AGENT}
    params = {}
    if TMDB_BEARER:
        headers["Authorization"] = f"Bearer {TMDB_BEARER}"
    elif TMDB_KEY:
        params["api_key"] = TMDB_KEY
    else:
        raise RuntimeError("TMDB key/token missing. Set TMDB_API_KEY or API_TMDB_TOKEN")
    return headers, params

def tmdb_get(path: str, params: Dict=None, timeout: float=20.0):
    headers, base = _auth()
    q = dict(base); q.update(params or {})
    url = f"https://api.themoviedb.org/3{path}"
    r = requests.get(url, headers=headers, params=q, timeout=timeout)
    r.raise_for_status()
    return r.json()

def tmdb_config() -> Tuple[str,str]:
    j = tmdb_get("/configuration")
    images = j.get("images",{})
    base = images.get("secure_base_url","https://image.tmdb.org/t/p/")
    sizes = images.get("poster_sizes",["w500","w780","original"])
    size = "w500" if "w500" in sizes else ("w780" if "w780" in sizes else (sizes[-1] if sizes else "original"))
    return base, size

def search(media: str, title: str, year: Optional[int]):
    q = {"query": title}
    if year:
        q["first_air_date_year" if media=="tv" else "year"] = year
    j = tmdb_get(f"/search/{media}", q, timeout=15)
    return j.get("results", [])

def details(media: str, tmdb_id: int):
    return tmdb_get(f"/{media}/{tmdb_id}", {"append_to_response":"external_ids"}, timeout=20)

def poster_data_uri(poster_path: Optional[str]) -> Optional[str]:
    if not poster_path:
        return None
    base, size = tmdb_config()
    url = f"{base}{size}{poster_path}"
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25)
    r.raise_for_status()
    mime = "image/png" if url.lower().endswith(".png") else "image/jpeg"
    return "data:%s;base64,%s" % (mime, base64.b64encode(r.content).decode("ascii"))

# ---------- IMDb helpers ----------
def _extract_imdb_id(text: str) -> Optional[str]:
    text = (text or "").strip()
    if not text:
        return None
    if text.startswith("tt") and text[2:].isdigit():
        return text
    try:
        p = urlparse(text)
        if "imdb.com" in p.netloc:
            parts = [x for x in p.path.split("/") if x]
            for seg in parts:
                if seg.startswith("tt") and seg[2:].isdigit():
                    return seg
    except Exception:
        pass
    return None

def find_by_imdb(text: str) -> Optional[Dict]:
    """Return a dict with keys: media ('tv'|'movie'), id (tmdb id)."""
    imdb_id = _extract_imdb_id(text)
    if not imdb_id:
        return None
    j = tmdb_get(f"/find/{imdb_id}", {"external_source": "imdb_id"}, timeout=12)
    tv = (j.get("tv_results") or [])
    mv = (j.get("movie_results") or [])
    if tv:
        return {"media":"tv", "id": tv[0]["id"]}
    if mv:
        return {"media":"movie", "id": mv[0]["id"]}
    return None

# ---------- Smart search ----------
_ALIASES = {
    "dept. q": "department q",
    "true detective: night country": "true detective",
}

def smart_search(media: str, title: str, year: Optional[int]):
    """Try with (title,year) -> alias -> colon-trim -> no-year."""
    t0 = title.strip()
    res = search(media, t0, year)
    if res: return res

    alias = _ALIASES.get(t0.lower())
    if alias:
        res = search(media, alias, year)
        if res: return res

    if ":" in t0:
        left = t0.split(":")[0].strip()
        res = search(media, left, year)
        if res: return res

    # Last resort: drop year
    res = search(media, t0, None)
    return res

# ---------- OMDb (Rotten Tomatoes %) ----------
def omdb_rt_value(title: str, year: Optional[int], timeout: float=8.0) -> Optional[str]:
    key = OMDB_KEY
    if not key:
        return None
    q = {"t": title, "type":"series", "apikey": key}
    if year:
        q["y"] = str(year)
    r = requests.get("https://www.omdbapi.com/?" + urlencode(q),
                     headers={"User-Agent": USER_AGENT}, timeout=timeout)
    r.raise_for_status()
    j = r.json()
    if j.get("Response")!="True":
        return None
    for it in j.get("Ratings",[]):
        if it.get("Source")=="Rotten Tomatoes":
            return it.get("Value")
    return None
