import os, sys, re, traceback, datetime
from typing import Optional
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QFileDialog, QLabel, QInputDialog, QMessageBox,
    QListWidget, QListWidgetItem, QComboBox, QLineEdit, QTableWidget, QTableWidgetItem,
    QProgressBar, QSplitter, QCheckBox
)
from PyQt6.QtCore import Qt

from store import norm_title, upsert_show, list_shows, update_personal_url, update_poster_rt, delete_show, recategorize, load_config, save_config
from tmdb import search, details, poster_data_uri, omdb_rt_value
from generator import generate_html, OUTPUTS_DIR

CATEGORIES = [
    "Suggestions for Wayne & Sandra",
    "Also shows I like (additional options)",
    "Popular with others"
]

def parse_show_line(line: str):
    s = line.strip()
    if not s or s.startswith("#"): return None
    m = re.match(r"^(.*?)\s*(?:\((\d{4})\))?\s*(?:\[(tv|movie)\])?$", s)
    if not m: return {"title": s, "year": None, "type":"tv"}
    title = m.group(1).strip()
    year = int(m.group(2)) if m.group(2) else None
    media = m.group(3) or "tv"
    return {"title": title, "year": year, "type": media}

class ShowsTab(QWidget):
    def __init__(self, log_cb):
        super().__init__()
        self.log = log_cb

        lay = QVBoxLayout(self)
        self.text = QTextEdit()
        self.text.setPlaceholderText("One per line, e.g.\nBosch (2014) [tv]\nSeverance (2022) [tv]")
        lay.addWidget(self.text)

        btns = QHBoxLayout()
        self.btnLoad = QPushButton("Load list…")
        self.btnValidate = QPushButton("Validate & Add")
        self.cat = QComboBox(); self.cat.addItems(CATEGORIES)
        btns.addWidget(self.btnLoad); btns.addWidget(QLabel("Category:")); btns.addWidget(self.cat); btns.addStretch(); btns.addWidget(self.btnValidate)
        lay.addLayout(btns)

        actions = QHBoxLayout()
        self.btnDelete = QPushButton("Delete selected")
        self.btnRecat = QPushButton("Recategorize selected…")
        actions.addWidget(self.btnDelete); actions.addWidget(self.btnRecat); actions.addStretch()
        lay.addLayout(actions)

        self.list = QListWidget()
        self.list.setSelectionMode(self.list.SelectionMode.ExtendedSelection)
        lay.addWidget(QLabel("Library:"))
        lay.addWidget(self.list)

        self.btnLoad.clicked.connect(self.load_file)
        self.btnValidate.clicked.connect(self.validate_add)
        self.btnDelete.clicked.connect(self.delete_selected)
        self.btnRecat.clicked.connect(self.recat_selected)
        self.refresh_list()

    def load_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open shows.txt", "", "Text files (*.txt);;All files (*.*)")
        if path:
            with open(path, "r", encoding="utf-8") as f:
                self.text.setPlainText(f.read())

    def validate_add(self):
        lines = [x for x in self.text.toPlainText().splitlines() if x.strip()]
        if not lines:
            QMessageBox.information(self, "Nothing to do", "Paste or load a list first."); return
        for ln in lines:
            si = parse_show_line(ln)
            if not si: continue
            media = si["type"]; title = si["title"]; year = si["year"]
            try:
                results = search(media, title, year)
            except Exception as e:
                self.log(f"TMDB search failed for {title}: {e}")
                continue
            if not results:
                self.log(f"No TMDB results: {title}"); continue
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
                desc = det.get("overview") or ""
                network = ""
                if media=="tv":
                    nets = det.get("networks") or []
                    if nets: network = nets[0].get("name","")
                genres = ", ".join([g["name"] for g in det.get("genres",[])])
                release = (det.get("first_air_date") or det.get("release_date") or "")[:4]
                status = det.get("status") or ""
                seasons = det.get("number_of_seasons") or None
                episodes = det.get("number_of_episodes") or None
                imdb_id = None
                ex = det.get("external_ids") or {}
                if ex: imdb_id = ex.get("imdb_id")
                tomato = omdb_rt_value(title, year)
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
        self.refresh_list()

    def refresh_list(self):
        self.list.clear()
        for s in list_shows():
            it = QListWidgetItem(f"{s['title']}  —  {s.get('category','')}")
            self.list.addItem(it)

    def delete_selected(self):
        sel = self.list.selectedItems()
        if not sel: return
        if QMessageBox.question(self, "Confirm", f"Delete {len(sel)} show(s)?") != QMessageBox.StandardButton.Yes:
            return
        for i in sel:
            delete_show(i.text().split("  —  ")[0])
            self.log(f"Deleted: {i.text()}")
        self.refresh_list()

    def recat_selected(self):
        sel = self.list.selectedItems()
        if not sel: return
        cat, ok = QInputDialog.getItem(self, "Category", "Pick new category", CATEGORIES, 0, False)
        if not ok: return
        for i in sel:
            title = i.text().split("  —  ")[0]
            recategorize(title, cat)
            self.log(f"Recategorized: {title} -> {cat}")
        self.refresh_list()

class FetchTab(QWidget):
    def __init__(self, log_cb):
        super().__init__()
        self.log = log_cb
        lay = QVBoxLayout(self)
        self.list = QListWidget(); self.list.setSelectionMode(self.list.SelectionMode.ExtendedSelection)
        self.btn = QPushButton("Fetch / Refresh selected")
        self.pbar = QProgressBar(); self.pbar.setValue(0)
        lay.addWidget(QLabel("Select shows to fetch posters + RT critic %:"))
        lay.addWidget(self.list); lay.addWidget(self.btn); lay.addWidget(self.pbar)
        self.btn.clicked.connect(self.on_fetch)
        self.refresh()

    def refresh(self):
        self.list.clear()
        for s in list_shows():
            it = QListWidgetItem(s["title"]); self.list.addItem(it)

    def on_fetch(self):
        sel = self.list.selectedItems()
        if not sel:
            self.log("Select one or more shows first."); return
        titles = [i.text() for i in sel]
        n = len(titles)
        for i, title in enumerate(titles, start=1):
            try:
                sh = [x for x in list_shows() if x["title"]==title]
                if not sh: continue
                sh = sh[0]
                det = details(sh["type"], sh["tmdb_id"])
                ppath = det.get("poster_path")
                pdata = poster_data_uri(ppath) if ppath else None
                tomato = omdb_rt_value(sh["title"], sh["year"])
                update_poster_rt(sh["title"], pdata, tomato or sh.get("tomato"))
                self.log(f"Fetched {title}")
            except Exception as e:
                self.log(f"Fetch failed for {title}: {e}")
            self.pbar.setValue(int(i/n*100))

class LinksTab(QWidget):
    def __init__(self, log_cb):
        super().__init__()
        self.log = log_cb
        lay = QVBoxLayout(self)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Title", "Personal URL"])
        self.btnSave = QPushButton("Save links")
        lay.addWidget(self.table); lay.addWidget(self.btnSave)
        self.btnSave.clicked.connect(self.save)
        self.refresh()

    def refresh(self):
        shows = list_shows()
        self.table.setRowCount(len(shows))
        for r, s in enumerate(shows):
            self.table.setItem(r, 0, QTableWidgetItem(s["title"]))
            self.table.setItem(r, 1, QTableWidgetItem(s.get("personal_url") or ""))
        self.table.resizeColumnsToContents()

    def save(self):
        rows = self.table.rowCount()
        for r in range(rows):
            title = self.table.item(r,0).text()
            url = self.table.item(r,1).text()
            update_personal_url(title, url)
        self.log("Saved links.")

class GenerateTab(QWidget):
    def __init__(self, log_cb):
        super().__init__()
        self.log = log_cb
        lay = QVBoxLayout(self)

        # Config load/save
        self.cfg = load_config()

        paths = QHBoxLayout()
        self.outPath = QLineEdit(self.cfg.get("output_path") or os.path.join(OUTPUTS_DIR, "TV-Guide-Dad-Sandra_OFFLINE.html"))
        self.btnBrowse = QPushButton("Browse…")
        paths.addWidget(QLabel("Output file:")); paths.addWidget(self.outPath); paths.addWidget(self.btnBrowse)
        lay.addLayout(paths)

        colors = QHBoxLayout()
        t = self.cfg.get("theme", {})
        self.brand = QLineEdit(t.get("brand","#11b3a4")); self.card = QLineEdit(t.get("card","#EAF7F4")); self.bg = QLineEdit(t.get("bg","#0e1e21"))
        colors.addWidget(QLabel("Brand")); colors.addWidget(self.brand)
        colors.addWidget(QLabel("Card")); colors.addWidget(self.card)
        colors.addWidget(QLabel("BG")); colors.addWidget(self.bg)
        lay.addLayout(colors)

        self.btnGen = QPushButton("Generate Offline HTML")
        self.btnSaveCfg = QPushButton("Save Settings")
        btns = QHBoxLayout(); btns.addWidget(self.btnGen); btns.addWidget(self.btnSaveCfg); btns.addStretch()
        lay.addLayout(btns)

        self.btnBrowse.clicked.connect(self.pick_out)
        self.btnGen.clicked.connect(self.generate)
        self.btnSaveCfg.clicked.connect(self.save_cfg)

    def pick_out(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save HTML", self.outPath.text(), "HTML files (*.html)")
        if path: self.outPath.setText(path)

    def save_cfg(self):
        cfg = {
            "output_path": self.outPath.text().strip(),
            "theme": {"brand": self.brand.text().strip(), "card": self.card.text().strip(), "bg": self.bg.text().strip()}
        }
        save_config(cfg)
        self.log("Settings saved.")

    def generate(self):
        from store import list_shows
        shows = list_shows()
        if not shows:
            QMessageBox.information(self, "No shows", "Add some shows first."); return
        theme = {"brand": self.brand.text().strip(), "card": self.card.text().strip(), "bg": self.bg.text().strip()}
        outfile = self.outPath.text().strip()
        try:
            generate_html(shows, outfile, theme)
            self.log(f"Generated: {outfile}")
            QMessageBox.information(self, "Done", f"Saved: {outfile}")
        except Exception as e:
            self.log(f"Generate failed: {e}")
            QMessageBox.critical(self, "Error", str(e))

class SettingsTab(QWidget):
    def __init__(self, log_cb):
        super().__init__()
        self.log = log_cb
        lay = QVBoxLayout(self)
        self.chkUsage = QCheckBox("Verbose console logging")
        self.chkUsage.setChecked(False)
        lay.addWidget(self.chkUsage)
        lay.addStretch()

class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TV Show Suggestions — PyQt6")
        central = QWidget(); self.setCentralWidget(central)
        v = QVBoxLayout(central)

        self.tabs = QTabWidget()
        v.addWidget(self.tabs)

        self.logView = QTextEdit(); self.logView.setReadOnly(True); v.addWidget(self.logView)

        self.showsTab = ShowsTab(self._log)
        self.fetchTab = FetchTab(self._log)
        self.linksTab = LinksTab(self._log)
        self.genTab = GenerateTab(self._log)
        self.settingsTab = SettingsTab(self._log)

        self.tabs.addTab(self.showsTab, "Shows")
        self.tabs.addTab(self.fetchTab, "Fetch")
        self.tabs.addTab(self.linksTab, "Links")
        self.tabs.addTab(self.genTab, "Generate")
        self.tabs.addTab(self.settingsTab, "Settings")

    def _log(self, msg: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.logView.append(f"[{ts}] {msg}")
        # also write to file
        try:
            os.makedirs("logs", exist_ok=True)
            with open(os.path.join("logs","app.log"), "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {msg}\n")
        except Exception:
            pass

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    os.makedirs("outputs", exist_ok=True)
    app = QApplication(sys.argv)
    w = Main(); w.resize(980, 760); w.show()
    try:
        sys.exit(app.exec())
    except Exception as e:
        tb = traceback.format_exc()
        print(tb)
