# scripts/main.py
import os
import sys
import re
import base64
import traceback
import datetime
import concurrent.futures
from typing import Optional, List, Dict, Tuple

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QFileDialog, QLabel, QInputDialog, QMessageBox,
    QListWidget, QListWidgetItem, QComboBox, QLineEdit, QTableWidget, QTableWidgetItem,
    QProgressBar, QCheckBox, QHeaderView, QSpinBox
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QRunnable, QThreadPool

from store import (
    norm_title, upsert_show, list_shows, update_personal_url,
    update_poster_rt, delete_show, recategorize, load_config, save_config
)
from tmdb import (
    search, smart_search, details, poster_data_uri,
    omdb_rt_value, find_by_imdb
)
from generator import generate_html, OUTPUTS_DIR

# ------------ constants / helpers ------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
POSTER_DIR = os.path.join(PROJECT_ROOT, "assets", "posters")
os.makedirs(POSTER_DIR, exist_ok=True)

CATEGORIES = [
    "Suggestions for Wayne & Sandra",
    "Also shows I like (additional options)",
    "Popular with others"
]

def _save_poster_file(title: str, data_uri: Optional[str], out_dir: str = POSTER_DIR) -> Optional[str]:
    """Save a data: URI poster to assets/posters/<safe>.jpg|.png and return the path."""
    if not data_uri:
        return None
    os.makedirs(out_dir, exist_ok=True)
    try:
        head, b64 = data_uri.split(",", 1)
    except ValueError:
        return None
    ext = ".png" if "png" in head.lower() else ".jpg"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("_")
    path = os.path.join(out_dir, f"{safe}{ext}")
    with open(path, "wb") as f:
        f.write(base64.b64decode(b64))
    return path

def parse_show_line(line: str) -> Optional[Dict]:
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    m = re.match(r"^(.*?)\s*(?:\((\d{4})\))?\s*(?:\[(tv|movie)\])?$", s)
    if not m:
        return {"title": s, "year": None, "type": "tv"}
    title = m.group(1).strip()
    year = int(m.group(2)) if m.group(2) else None
    media = m.group(3) or "tv"
    return {"title": title, "year": year, "type": media}

# ------------ threading: FETCH ------------
class FetchSignals(QObject):
    progress = pyqtSignal(int)           # 0..100
    note = pyqtSignal(str)               # log line
    finished = pyqtSignal(int, int)      # ok, fail

class FetchWorker(QRunnable):
    def __init__(self, titles: List[str], max_workers: int = 5, fetch_rt: bool = True):
        super().__init__()
        self.titles = titles
        self.max_workers = max_workers
        self.fetch_rt = fetch_rt
        self.signals = FetchSignals()
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def _one(self, title: str) -> Tuple[str, Optional[str]]:
        sh_list = [x for x in list_shows() if x["title"] == title]
        if not sh_list:
            return (title, "Not in DB")
        sh = sh_list[0]
        try:
            det = details(sh["type"], sh["tmdb_id"])
            if self._cancel:
                return (title, "Cancelled")
            ppath = det.get("poster_path")
            pdata = poster_data_uri(ppath) if ppath else None
            if pdata:
                _save_poster_file(sh["title"], pdata)
            tomato = omdb_rt_value(sh["title"], sh.get("year")) if self.fetch_rt else None
            update_poster_rt(sh["title"], pdata, tomato or sh.get("tomato"))
            return (title, None)
        except Exception as e:
            return (title, str(e))

    def run(self) -> None:
        total = len(self.titles)
        if total == 0:
            self.signals.finished.emit(0, 0)
            return
        ok = fail = done = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futs = {ex.submit(self._one, t): t for t in self.titles}
            for fut in concurrent.futures.as_completed(futs):
                title, err = fut.result()
                done += 1
                if err is None:
                    ok += 1
                    self.signals.note.emit(f"Fetched {title}")
                elif err == "Cancelled":
                    self.signals.note.emit(f"Cancelled {title}")
                else:
                    fail += 1
                    self.signals.note.emit(f"Fetch failed for {title}: {err}")
                self.signals.progress.emit(int(done / total * 100))
                if self._cancel:
                    break
        self.signals.finished.emit(ok, fail)

# ------------ threading: FAST ADD ------------
class AddSignals(QObject):
    progress = pyqtSignal(int)
    note = pyqtSignal(str)
    finished = pyqtSignal(int, int)

class AddWorker(QRunnable):
    """Fast Add: smart search + save without interactive pick (parallel)."""
    def __init__(self, items: List[Dict], default_category: str, max_workers: int = 5, fetch_rt: bool = True):
        super().__init__()
        self.items = items
        self.default_category = default_category
        self.max_workers = max_workers
        self.fetch_rt = fetch_rt
        self.signals = AddSignals()
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def _save_one(self, media: str, title: str, year: Optional[int]) -> Tuple[str, Optional[str]]:
        try:
            results = smart_search(media, title, year)
            if not results:
                return (title, "No TMDB results")
            r = results[0]  # best guess
            tmdb_id = int(r["id"])
            det = details(media, tmdb_id)
            if self._cancel:
                return (title, "Cancelled")
            poster_path = det.get("poster_path")
            p_data = poster_data_uri(poster_path) if poster_path else None
            if p_data:
                _save_poster_file(title, p_data)
            desc = det.get("overview") or ""
            network = ""
            if media == "tv":
                nets = det.get("networks") or []
                if nets:
                    network = nets[0].get("name", "")
            genres = ", ".join([g["name"] for g in det.get("genres", [])])
            release = (det.get("first_air_date") or det.get("release_date") or "")[:4]
            status = det.get("status") or ""
            seasons = det.get("number_of_seasons") or None
            episodes = det.get("number_of_episodes") or None
            imdb_id = (det.get("external_ids") or {}).get("imdb_id")
            tomato = omdb_rt_value(title, year) if self.fetch_rt else None
            row = dict(
                title=title, title_norm=norm_title(title), year=year, type=media,
                tmdb_id=tmdb_id, imdb_id=imdb_id, tvmaze_id=None,
                network=network, rating="", genres=genres, release=release,
                status=status, seasons=seasons, episodes=episodes, description=desc,
                services="", poster_data_uri=p_data, tomato=tomato, popcorn=None,
                category=self.default_category, personal_url=None
            )
            upsert_show(row)
            return (title, None)
        except Exception as e:
            return (title, str(e))

    def run(self) -> None:
        total = len(self.items)
        if total == 0:
            self.signals.finished.emit(0, 0)
            return
        ok = fail = done = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futs = {ex.submit(self._save_one, it["type"], it["title"], it["year"]): it for it in self.items}
            for fut in concurrent.futures.as_completed(futs):
                title, err = fut.result()
                done += 1
                if err is None:
                    ok += 1
                    self.signals.note.emit(f"Saved: {title}")
                else:
                    fail += 1
                    if "No TMDB results" in (err or ""):
                        self.signals.note.emit(f"No TMDB results: {title}")
                    else:
                        self.signals.note.emit(f"Error saving {title}: {err}")
                self.signals.progress.emit(int(done / total * 100))
                if self._cancel:
                    break
        self.signals.finished.emit(ok, fail)

# ------------ Shows tab ------------
class ShowsTab(QWidget):
    def __init__(self, log_cb, on_library_changed, get_settings):
        super().__init__()
        self.log = log_cb
        self.on_library_changed = on_library_changed
        self.get_settings = get_settings

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Step 1 — Add Shows. Use Fast Add (auto) or Validate & Add (manual pick)."))

        # Add / validate area
        self.text = QTextEdit()
        self.text.setPlaceholderText("One per line, e.g.\nBosch (2014) [tv]\nSeverance (2022) [tv]\nDepartment Q (2024) [tv]")
        root.addWidget(self.text)

        row1 = QHBoxLayout()
        self.btnLoad = QPushButton("Load list…")
        self.btnValidate = QPushButton("Validate & Add (manual)")
        self.btnFastAdd = QPushButton("Fast Add (auto, multi-threaded)")
        self.cat = QComboBox()
        self.cat.addItems(CATEGORIES)
        row1.addWidget(self.btnLoad)
        row1.addWidget(QLabel("Default category:"))
        row1.addWidget(self.cat)
        row1.addStretch()
        row1.addWidget(self.btnValidate)
        row1.addWidget(self.btnFastAdd)
        root.addLayout(row1)

        # IMDb direct add
        row2 = QHBoxLayout()
        self.imdbBox = QLineEdit()
        self.imdbBox.setPlaceholderText("Paste IMDb URL or ID (e.g., https://www.imdb.com/title/tt27995114/)")
        self.btnAddImdb = QPushButton("Add via IMDb")
        row2.addWidget(self.imdbBox)
        row2.addWidget(self.btnAddImdb)
        root.addLayout(row2)

        # Library editor (table)
        lib_hdr = QHBoxLayout()
        lib_hdr.addWidget(QLabel("Your library (edit category inline, then Save):"))
        lib_hdr.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search…")
        self.btnLibRefresh = QPushButton("Refresh")
        self.btnSaveCats = QPushButton("Save changes")
        lib_hdr.addWidget(self.search)
        lib_hdr.addWidget(self.btnLibRefresh)
        lib_hdr.addWidget(self.btnSaveCats)
        root.addLayout(lib_hdr)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Title", "Category"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self.table)

        actions = QHBoxLayout()
        self.btnDelete = QPushButton("Delete selected")
        self.btnRecat = QPushButton("Recategorize selected…")
        actions.addWidget(self.btnDelete)
        actions.addWidget(self.btnRecat)
        actions.addStretch()
        root.addLayout(actions)

        # connections
        self.btnLoad.clicked.connect(self.load_file)
        self.btnValidate.clicked.connect(self.validate_add_manual)
        self.btnFastAdd.clicked.connect(self.fast_add)
        self.btnLibRefresh.clicked.connect(self.rebuild_table)
        self.search.textChanged.connect(self.rebuild_table)
        self.btnSaveCats.clicked.connect(self.save_category_changes)
        self.btnDelete.clicked.connect(self.delete_selected_rows)
        self.btnRecat.clicked.connect(self.recat_selected_rows)
        self.btnAddImdb.clicked.connect(self.add_via_imdb)

        self.rebuild_table()

    def load_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open shows.txt", "", "Text files (*.txt);;All files (*.*)")
        if path:
            with open(path, "r", encoding="utf-8") as f:
                self.text.setPlainText(f.read())

    def validate_add_manual(self) -> None:
        lines = [x for x in self.text.toPlainText().splitlines() if x.strip()]
        if not lines:
            QMessageBox.information(self, "Nothing to do", "Paste or load a list first.")
            return
        for ln in lines:
            si = parse_show_line(ln)
            if not si:
                continue
            media = si["type"]; title = si["title"]; year = si["year"]
            try:
                results = smart_search(media, title, year)
            except Exception as e:
                self.log(f"TMDB search failed for {title}: {e}")
                continue
            if not results:
                self.log(f"No TMDB results: {title}")
                continue
            opts = []
            for r in results[:10]:
                t = r.get("name") or r.get("title") or ""
                y = (r.get("first_air_date") or r.get("release_date") or "")[:4]
                opts.append(f"{r['id']}: {t} ({y})")
            choice, ok = QInputDialog.getItem(self, "Pick a match", f"{title}", opts, 0, False)
            if not ok:
                self.log(f"Skipped: {title}")
                continue

            tmdb_id = int(choice.split(":")[0])
            try:
                det = details(media, tmdb_id)
                poster_path = det.get("poster_path")
                p_data = poster_data_uri(poster_path) if poster_path else None
                if p_data:
                    _save_poster_file(title, p_data)
                desc = det.get("overview") or ""
                network = ""
                if media == "tv":
                    nets = det.get("networks") or []
                    if nets:
                        network = nets[0].get("name", "")
                genres = ", ".join([g["name"] for g in det.get("genres", [])])
                release = (det.get("first_air_date") or det.get("release_date") or "")[:4]
                status = det.get("status") or ""
                seasons = det.get("number_of_seasons") or None
                episodes = det.get("number_of_episodes") or None
                imdb_id = (det.get("external_ids") or {}).get("imdb_id")
                fetch_rt = self.get_settings().get("fetch_rt", True)
                tomato = omdb_rt_value(title, year) if fetch_rt else None
                row = dict(
                    title=title, title_norm=norm_title(title), year=year, type=media,
                    tmdb_id=tmdb_id, imdb_id=imdb_id, tvmaze_id=None,
                    network=network, rating="", genres=genres, release=release,
                    status=status, seasons=seasons, episodes=episodes, description=desc,
                    services="", poster_data_uri=p_data, tomato=tomato, popcorn=None,
                    category=self.cat.currentText(), personal_url=None
                )
                upsert_show(row)
                self.log(f"Saved: {title}")
            except Exception as e:
                self.log(f"Error saving {title}: {e}")

        self.rebuild_table()
        self.on_library_changed()

    def fast_add(self) -> None:
        lines = [x for x in self.text.toPlainText().splitlines() if x.strip()]
        items = [parse_show_line(ln) for ln in lines if parse_show_line(ln)]
        if not items:
            QMessageBox.information(self, "Nothing to do", "Paste or load a list first.")
            return
        s = self.get_settings()
        worker = AddWorker(
            items,
            default_category=self.cat.currentText(),
            max_workers=s.get("max_workers", 5),
            fetch_rt=s.get("fetch_rt", True)
        )
        worker.signals.note.connect(self.log)
        def done(ok, fail):
            self.log(f"Fast Add done — OK: {ok}, Failed: {fail}")
            self.rebuild_table()
            self.on_library_changed()
        worker.signals.finished.connect(done)
        QThreadPool.globalInstance().start(worker)

    def add_via_imdb(self) -> None:
        text = self.imdbBox.text().strip()
        if not text:
            return
        m = find_by_imdb(text)
        if not m:
            QMessageBox.information(self, "Not found", "Could not resolve IMDb ID on TMDB.")
            return
        media, tmdb_id = m["media"], m["id"]
        try:
            det = details(media, tmdb_id)
            title = det.get("name") or det.get("title") or "Unknown"
            year = int((det.get("first_air_date") or det.get("release_date") or "0000")[:4] or 0) or None
            poster_path = det.get("poster_path")
            p_data = poster_data_uri(poster_path) if poster_path else None
            if p_data:
                _save_poster_file(title, p_data)
            desc = det.get("overview") or ""
            network = ""
            if media == "tv":
                nets = det.get("networks") or []
                if nets:
                    network = nets[0].get("name", "")
            genres = ", ".join([g["name"] for g in det.get("genres", [])])
            release = (det.get("first_air_date") or det.get("release_date") or "")[:4]
            status = det.get("status") or ""
            seasons = det.get("number_of_seasons") or None
            episodes = det.get("number_of_episodes") or None
            imdb_id = (det.get("external_ids") or {}).get("imdb_id")
            fetch_rt = self.get_settings().get("fetch_rt", True)
            tomato = omdb_rt_value(title, year) if fetch_rt else None
            row = dict(
                title=title, title_norm=norm_title(title), year=year, type=media,
                tmdb_id=tmdb_id, imdb_id=imdb_id, tvmaze_id=None,
                network=network, rating="", genres=genres, release=release,
                status=status, seasons=seasons, episodes=episodes, description=desc,
                services="", poster_data_uri=p_data, tomato=tomato, popcorn=None,
                category=self.cat.currentText(), personal_url=None
            )
            upsert_show(row)
            self.log(f"Saved (IMDb): {title}")
            self.rebuild_table()
            self.on_library_changed()
        except Exception as e:
            self.log(f"IMDb add failed: {e}")

    # ---- library table helpers ----
    def rebuild_table(self) -> None:
        shows = list_shows()
        q = self.search.text().strip().lower()
        if q:
            shows = [s for s in shows if q in s["title"].lower()]
        self.table.setRowCount(len(shows))
        for r, s in enumerate(shows):
            self.table.setItem(r, 0, QTableWidgetItem(s["title"]))
            combo = QComboBox()
            combo.addItems(CATEGORIES)
            cat = s.get("category") or CATEGORIES[0]
            try:
                combo.setCurrentIndex(CATEGORIES.index(cat))
            except ValueError:
                combo.setCurrentIndex(0)
            self.table.setCellWidget(r, 1, combo)
        self.table.resizeRowsToContents()

    def _selected_titles(self) -> List[str]:
        rows = set(idx.row() for idx in self.table.selectedIndexes())
        titles: List[str] = []
        for r in rows:
            it = self.table.item(r, 0)
            if it:
                titles.append(it.text())
        return titles

    def save_category_changes(self) -> None:
        rows = self.table.rowCount()
        for r in range(rows):
            title = self.table.item(r, 0).text()
            combo = self.table.cellWidget(r, 1)
            recategorize(title, combo.currentText())
        self.log("Saved category changes.")
        self.on_library_changed()

    def delete_selected_rows(self) -> None:
        titles = self._selected_titles()
        if not titles:
            return
        if QMessageBox.question(self, "Confirm", f"Delete {len(titles)} show(s)?") != QMessageBox.StandardButton.Yes:
            return
        for t in titles:
            delete_show(t)
            self.log(f"Deleted: {t}")
        self.rebuild_table()
        self.on_library_changed()

    def recat_selected_rows(self) -> None:
        titles = self._selected_titles()
        if not titles:
            return
        cat, ok = QInputDialog.getItem(self, "Category", "Pick new category", CATEGORIES, 0, False)
        if not ok:
            return
        for t in titles:
            recategorize(t, cat)
        self.log(f"Recategorized {len(titles)} show(s) -> {cat}")
        self.rebuild_table()
        self.on_library_changed()

# ------------ Fetch tab (parallel) ------------
class FetchTab(QWidget):
    def __init__(self, log_cb, get_settings):
        super().__init__()
        self.log = log_cb
        self.get_settings = get_settings
        self.pool = QThreadPool.globalInstance()
        self.worker: Optional[FetchWorker] = None

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Step 2 — Posters & Ratings: select shows and Fetch (parallel)."))

        bar = QHBoxLayout()
        self.btnRefresh = QPushButton("Refresh list")
        self.btnSelAll = QPushButton("Select all")
        self.btnClear = QPushButton("Clear")
        self.btnCancel = QPushButton("Cancel")
        bar.addStretch()
        bar.addWidget(self.btnRefresh)
        bar.addWidget(self.btnSelAll)
        bar.addWidget(self.btnClear)
        bar.addWidget(self.btnCancel)
        lay.addLayout(bar)

        self.list = QListWidget()
        self.list.setSelectionMode(self.list.SelectionMode.ExtendedSelection)
        lay.addWidget(self.list)

        self.btnFetch = QPushButton("Fetch / Refresh selected")
        lay.addWidget(self.btnFetch)

        self.pbar = QProgressBar()
        self.pbar.setValue(0)
        lay.addWidget(self.pbar)

        self.btnFetch.clicked.connect(self.on_fetch)
        self.btnRefresh.clicked.connect(self.refresh)
        self.btnSelAll.clicked.connect(lambda: self.list.selectAll())
        self.btnClear.clicked.connect(lambda: self.list.clearSelection())
        self.btnCancel.clicked.connect(self.on_cancel)

        self.refresh()

    def refresh(self) -> None:
        self.list.clear()
        for s in list_shows():
            self.list.addItem(QListWidgetItem(s["title"]))

    def set_busy(self, busy: bool) -> None:
        for w in (self.btnFetch, self.btnRefresh, self.btnSelAll, self.btnClear):
            w.setEnabled(not busy)
        self.btnCancel.setEnabled(busy)

    def on_cancel(self) -> None:
        if self.worker:
            self.worker.cancel()
            self.log("Cancel requested…")

    def on_fetch(self) -> None:
        sel = self.list.selectedItems()
        if not sel:
            self.log("Select one or more shows first.")
            return
        titles = [i.text() for i in sel]
        self.pbar.setValue(0)
        self.set_busy(True)
        s = self.get_settings()
        self.worker = FetchWorker(
            titles,
            max_workers=s.get("max_workers", 5),
            fetch_rt=s.get("fetch_rt", True)
        )
        self.worker.signals.progress.connect(self.pbar.setValue)
        self.worker.signals.note.connect(self.log)
        def done(ok, fail):
            self.set_busy(False)
            self.log(f"Finished fetch — OK: {ok}, Failed: {fail}")
        self.worker.signals.finished.connect(done)
        self.pool.start(self.worker)

# ------------ Links tab ------------
class LinksTab(QWidget):
    def __init__(self, log_cb):
        super().__init__()
        self.log = log_cb
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Step 3 — Personal Links: add your Google/Drive page per show (optional)."))

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Title", "Personal URL"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.btnSave = QPushButton("Save links")
        lay.addWidget(self.table)
        lay.addWidget(self.btnSave)
        self.btnSave.clicked.connect(self.save)

        self.refresh()

    def refresh(self) -> None:
        shows = list_shows()
        self.table.setRowCount(len(shows))
        for r, s in enumerate(shows):
            self.table.setItem(r, 0, QTableWidgetItem(s["title"]))
            self.table.setItem(r, 1, QTableWidgetItem(s.get("personal_url") or ""))
        self.table.resizeRowsToContents()

    def save(self) -> None:
        rows = self.table.rowCount()
        for r in range(rows):
            title = self.table.item(r, 0).text()
            url = self.table.item(r, 1).text()
            update_personal_url(title, url)
        self.log("Saved links.")

# ------------ Generate tab ------------
class GenerateTab(QWidget):
    def __init__(self, log_cb, get_settings):
        super().__init__()
        self.log = log_cb
        self.get_settings = get_settings

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Step 4 — Generate Page: pick colors/file, then Generate."))

        self.cfg = load_config()
        paths = QHBoxLayout()
        self.outPath = QLineEdit(self.cfg.get("output_path") or os.path.join(OUTPUTS_DIR, "TV-Guide-Dad-Sandra_OFFLINE.html"))
        self.btnBrowse = QPushButton("Browse…")
        paths.addWidget(QLabel("Output file:"))
        paths.addWidget(self.outPath)
        paths.addWidget(self.btnBrowse)
        lay.addLayout(paths)

        colors = QHBoxLayout()
        t = self.cfg.get("theme", {})
        self.brand = QLineEdit(t.get("brand", "#11b3a4"))
        self.card = QLineEdit(t.get("card", "#EAF7F4"))
        self.bg = QLineEdit(t.get("bg", "#0e1e21"))
        colors.addWidget(QLabel("Brand"))
        colors.addWidget(self.brand)
        colors.addWidget(QLabel("Card"))
        colors.addWidget(self.card)
        colors.addWidget(QLabel("BG"))
        colors.addWidget(self.bg)
        lay.addLayout(colors)

        self.btnGen = QPushButton("Generate Offline HTML")
        self.btnSaveCfg = QPushButton("Save Settings")
        self.btnOneClick = QPushButton("Build My Page (fetch missing → generate)")
        btns = QHBoxLayout()
        btns.addWidget(self.btnGen)
        btns.addWidget(self.btnSaveCfg)
        btns.addWidget(self.btnOneClick)
        btns.addStretch()
        lay.addLayout(btns)

        self.btnBrowse.clicked.connect(self.pick_out)
        self.btnGen.clicked.connect(self.generate)
        self.btnSaveCfg.clicked.connect(self.save_cfg)
        self.btnOneClick.clicked.connect(self.one_click)

    def pick_out(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save HTML", self.outPath.text(), "HTML files (*.html)")
        if path:
            self.outPath.setText(path)

    def save_cfg(self) -> None:
        cfg = {
            "output_path": self.outPath.text().strip(),
            "theme": {"brand": self.brand.text().strip(), "card": self.card.text().strip(), "bg": self.bg.text().strip()}
        }
        save_config(cfg)
        self.log("Settings saved.")

    def generate(self) -> None:
        shows = list_shows()
        if not shows:
            QMessageBox.information(self, "No shows", "Add some shows first.")
            return
        theme = {"brand": self.brand.text().strip(), "card": self.card.text().strip(), "bg": self.bg.text().strip()}
        outfile = self.outPath.text().strip()
        try:
            generate_html(shows, outfile, theme)
            self.log(f"Generated: {outfile}")
            QMessageBox.information(self, "Done", f"Saved: {outfile}")
        except Exception as e:
            self.log(f"Generate failed: {e}")
            QMessageBox.critical(self, "Error", str(e))

    def one_click(self) -> None:
        # fetch missing → generate
        missing = [s["title"] for s in list_shows() if not s.get("poster_data_uri") or not s.get("tomato")]
        if not missing:
            self.generate()
            return
        s = self.get_settings()
        worker = FetchWorker(missing, max_workers=s.get("max_workers", 5), fetch_rt=s.get("fetch_rt", True))
        worker.signals.note.connect(self.log)
        def after(ok, fail):
            self.log(f"Background fetch done — OK: {ok}, Failed: {fail}")
            self.generate()
        worker.signals.finished.connect(after)
        QThreadPool.globalInstance().start(worker)

# ------------ Settings tab ------------
class SettingsTab(QWidget):
    def __init__(self, get_settings, set_settings):
        super().__init__()
        self.get_settings = get_settings
        self.set_settings = set_settings

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Step 5 — Settings"))

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Max workers"))
        self.spinWorkers = QSpinBox()
        self.spinWorkers.setRange(1, 16)
        self.spinWorkers.setValue(self.get_settings().get("max_workers", 5))
        row1.addWidget(self.spinWorkers)
        row1.addStretch()
        lay.addLayout(row1)

        self.chkRT = QCheckBox("Fetch Rotten Tomatoes critic % (via OMDb)")
        self.chkRT.setChecked(self.get_settings().get("fetch_rt", True))
        lay.addWidget(self.chkRT)
        lay.addStretch()

        self.spinWorkers.valueChanged.connect(self._changed)
        self.chkRT.stateChanged.connect(self._changed)

    def _changed(self, *args):
        self.set_settings({"max_workers": self.spinWorkers.value(), "fetch_rt": self.chkRT.isChecked()})

# ------------ Main window ------------
class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TV Show Suggestions — PyQt6")
        self._settings = {"max_workers": 5, "fetch_rt": True}

        central = QWidget()
        self.setCentralWidget(central)
        v = QVBoxLayout(central)

        self.tabs = QTabWidget()
        v.addWidget(self.tabs)

        self.logView = QTextEdit()
        self.logView.setReadOnly(True)
        v.addWidget(self.logView)

        getset = lambda: self._settings
        setset = lambda d: self._settings.update(d)

        self.showsTab = ShowsTab(self._log, self._library_changed, getset)
        self.fetchTab = FetchTab(self._log, getset)
        self.linksTab = LinksTab(self._log)
        self.genTab = GenerateTab(self._log, getset)
        self.settingsTab = SettingsTab(getset, setset)

        self.tabs.addTab(self.showsTab, "1) Add Shows")
        self.tabs.addTab(self.fetchTab, "2) Posters & Ratings")
        self.tabs.addTab(self.linksTab, "3) Personal Links")
        self.tabs.addTab(self.genTab, "4) Generate Page")
        self.tabs.addTab(self.settingsTab, "5) Settings")

        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _log(self, msg: str) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.logView.append(f"[{ts}] {msg}")
        try:
            os.makedirs(os.path.join(PROJECT_ROOT, "logs"), exist_ok=True)
            with open(os.path.join(PROJECT_ROOT, "logs", "app.log"), "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {msg}\n")
        except Exception:
            pass

    def _on_tab_changed(self, idx: int) -> None:
        w = self.tabs.widget(idx)
        if isinstance(w, FetchTab):
            w.refresh()
        if isinstance(w, LinksTab):
            w.refresh()

    def _library_changed(self) -> None:
        self.fetchTab.refresh()
        self.linksTab.refresh()

if __name__ == "__main__":
    os.makedirs(os.path.join(PROJECT_ROOT, "data"), exist_ok=True)
    os.makedirs(os.path.join(PROJECT_ROOT, "outputs"), exist_ok=True)
    app = QApplication(sys.argv)
    w = Main()
    w.resize(1000, 760)
    w.show()
    try:
        sys.exit(app.exec())
    except Exception:
        print(traceback.format_exc())
