
import os, sqlite3, time, logging
import streamlit as st

from backend import db_conn
db_conn().close()  # ensure tv_cache.db and shows table exist at startup
from backend import (
    parse_show_line, search_choices, add_or_update_show, all_shows, generate_offline_html, DB_PATH
)

logging.basicConfig(level=logging.INFO)
st.set_page_config(page_title="TV Guide GUI", page_icon="🎬", layout="centered")

st.title("🎬 TV Guide — GUI")
st.caption("Validate shows, cache metadata & posters locally, and generate an offline HTML.")

with st.sidebar:
    st.subheader("Config")
    out_dir = st.text_input("Output folder", os.path.join(os.path.dirname(__file__), "..", "outputs"))
    st.caption("Set these env vars before running: TMDB_API_KEY / API_TMDB_KEY or API_TMDB_TOKEN; optional OMDB_API_KEY.")

tab1, tab2, tab3, tab4 = st.tabs(["📝 Shows", "⬇️ Fetch / Cache", "🔗 Links", "🎨 Design & Generate"])

with tab1:
    st.subheader("Paste or upload shows")
    default_list = "\n".join([
        "Bosch (2014) [tv]",
        "Bosch: Legacy (2022) [tv]",
        "Only Murders in the Building (2021) [tv]",
        "The White Lotus (2021) [tv]",
        "Severance (2022) [tv]",
        "Baby Reindeer (2024) [tv]",
    ])
    txt = st.text_area("One per line", height=180, value=default_list)
    up = st.file_uploader("Or upload shows.txt", type=["txt"])
    if up is not None:
        txt = up.read().decode("utf-8")

    if st.button("Validate & Select Matches", type="primary"):
        shows = [parse_show_line(x) for x in txt.splitlines()]
        shows = [s for s in shows if s]
        if not shows:
            st.warning("No shows parsed."); st.stop()

        picks = {}
        for s in shows:
            st.write("---")
            st.write(f"**{s.title}**  \n_{s.type} • {s.year or '—'}_")
            choices = search_choices(s.title, s.year, s.type)
            if not choices:
                st.error("No TMDB matches found.")
                continue
            labels = [f"{cid}: {label}" for (cid,label) in choices]
            sel = st.selectbox("Pick the correct title", labels, key=f"pick_{s.title}")
            tmdb_id = int(sel.split(":")[0])
            cat = st.selectbox("Category", [
                "Suggestions for Wayne & Sandra",
                "Also shows I like (additional options)",
                "Popular with others"
            ], key=f"cat_{s.title}")
            picks[s.title] = (s, tmdb_id, cat)

        if picks and st.button("Add/Update Selected"):
            for t,(s, tmdb_id, cat) in picks.items():
                add_or_update_show(s, tmdb_id, category=cat)
                st.success(f"Saved: {s.title}")
            st.info("Switch to **Fetch / Cache** to refresh posters/metadata any time.")

with tab2:
    st.subheader("Fetch / Refresh cached details")
    if not os.path.exists(DB_PATH):
        st.warning("No database yet — use the **Shows** tab first.")
    else:
        conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT title, tmdb_id FROM shows ORDER BY title").fetchall()
        conn.close()
        if not rows:
            st.warning("No shows saved yet.")
        else:
            names = [r["title"] for r in rows]
            to_get = st.multiselect("Select shows", names, default=names)
            if st.button("Fetch now", type="primary"):
                from backend import tmdb_details, download_poster_data_uri, omdb_rt_value, db_conn
                conn = db_conn()
                prog = st.progress(0.0, text="Fetching…")
                for i, name in enumerate(to_get):
                    r = conn.execute("SELECT * FROM shows WHERE title=?", (name,)).fetchone()
                    if not r: continue
                    det = tmdb_details(r["type"], r["tmdb_id"])
                    poster_path = det.get("poster_path")
                    poster = download_poster_data_uri(poster_path) if poster_path else None
                    tomato = omdb_rt_value(r["title"], r["year"])
                    conn.execute("UPDATE shows SET poster_data_uri=?, tomato=?, last_updated=? WHERE id=?", (poster, tomato, int(time.time()), r["id"]))
                    conn.commit()
                    prog.progress((i+1)/len(to_get), text=f"Fetched {i+1}/{len(to_get)}: {name}")
                conn.close()
                st.success("Done.")

with tab3:
    st.subheader("Personal links (optional)")
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id,title,personal_url FROM shows ORDER BY title").fetchall()
    for r in rows:
        v = st.text_input(r["title"], value=r["personal_url"] or "", key=f"url_{r['id']}")
        if st.button(f"Save link: {r['title']}", key=f"btn_{r['id']}"):
            conn.execute("UPDATE shows SET personal_url=? WHERE id=?", (v, r["id"])); conn.commit(); st.success("Saved.")
    conn.close()

with tab4:
    st.subheader("Design & Generate")
    brand = st.color_picker("Brand color", "#11b3a4")
    card  = st.color_picker("Card background", "#EAF7F4")
    bg    = st.color_picker("Page background", "#0e1e21")
    shows = all_shows()
    st.write(f"{len(shows)} shows in library.")
    if st.button("Generate Offline HTML", type="primary"):
        out = os.path.join(out_dir, "TV-Guide-Dad-Sandra_OFFLINE.html")
        generate_offline_html(shows, out, {"brand":brand, "card":card, "bg":bg})
        with open(out, "rb") as f:
            st.download_button("Download HTML", f.read(), file_name="TV-Guide-Dad-Sandra_OFFLINE.html", mime="text/html")
        st.success(f"Generated: {out}")

