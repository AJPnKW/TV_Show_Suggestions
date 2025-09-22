import os, base64
from typing import Optional, Dict, List
from urllib.parse import urlencode

import requests

TMDB_KEY    = (os.environ.get("TMDB_API_KEY") or os.environ.get("API_TMDB_KEY") or "").strip()
TMDB_BEARER = (os.environ.get("API_TMDB_TOKEN") or os.environ.get("TMDB_BEARER") or "").strip()
OMDB_KEY    = (os.environ.get("OMDB_API_KEY") or os.environ.get("API_OMDB_KEY") or "").strip()

def _auth():
    headers = {"User-Agent":"TVShowSuggestions/1.0"}
    params = {}
    if TMDB_BEARER:
        headers["Authorization"] = f"Bearer {TMDB_BEARER}"
    elif TMDB_KEY:
        params["api_key"] = TMDB_KEY
    else:
        raise RuntimeError("TMDB key/token missing. Set TMDB_API_KEY or API_TMDB_TOKEN")
    return headers, params

def tmdb_get(path: str, params: Dict=None):
    headers, base = _auth()
    q = dict(base); q.update(params or {})
    url = f"https://api.themoviedb.org/3{path}"
    r = requests.get(url, headers=headers, params=q, timeout=25)
    r.raise_for_status()
    return r.json()

def tmdb_config():
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
    j = tmdb_get(f"/search/{media}", q)
    return j.get("results", [])

def details(media: str, tmdb_id: int):
    return tmdb_get(f"/{media}/{tmdb_id}", {"append_to_response":"external_ids"})

def poster_data_uri(poster_path: str) -> Optional[str]:
    if not poster_path:
        return None
    base, size = tmdb_config()
    url = f"{base}{size}{poster_path}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    mime = "image/png" if url.lower().endswith(".png") else "image/jpeg"
    return "data:%s;base64,%s" % (mime, base64.b64encode(r.content).decode("ascii"))

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
