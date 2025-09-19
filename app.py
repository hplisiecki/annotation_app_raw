import os
import sys
import csv
import sqlite3
from datetime import datetime
import re, html, time

from PySide6.QtCore import Qt, QSettings, QByteArray, QStandardPaths
from PySide6.QtGui import QAction, QIcon, QCloseEvent, QKeySequence, QFont, QCursor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QMessageBox, QLabel,
    QFileDialog, QStyle, QFrame, QSizePolicy,
    QToolBar, QWidgetAction, QButtonGroup, QScrollArea
)

# ================== App config ==================
APP_NAME = "TweetTagger"
ORG_NAME = "YourOrg"

APP_DIR = os.path.join(os.path.expanduser("~"), ".tweet_tagger")
DB_PATH = os.path.join(APP_DIR, "annotations.sqlite3")

ICON_FALLBACK = None

# --- Sizing knobs ---
TILE_MIN_SIDE = 96          # minimum square size for a tile
TILE_MAX_SIDE = 220         # maximum square size for a tile
CHOICE_BTN_MIN_W = 330   # min width we allow each follow-up option to shrink to
CARD_SIDE_MARGINS = 16   # matches your card contents margins (left/right)
ROW_SPACING = 10         # matches ChoiceRow spacing
TILES_SPACING = 12       # matches tiles row spacing
ROOT_SIDE_MARGINS = 18   # matches root layout L/R margins

# Categories (+ “Other”)
LABELS = [
    ("IMIGRACJA",   "imigracja"),
    ("ZAUFANIE",    "zaufanie"),
    ("KLIMAT",      "klimat"),
    ("ZDROWIE",     "zdrowie"),
    ("SPRAWCZOŚĆ",  "sprawczosc"),
    ("NAUKOWCY",    "naukowcy"),
    ("SZCZEPIONKI", "szczepionki"),
    ("INNE", "inne"),
]

# Follow-up questions per topic
DETAIL_QUESTIONS = {
    "zdrowie": (
        "W odniesieniu do zdrowia fizycznego i samopoczucia, nadawca wskazuje, że:",
        [
            "jego stan jest dobry",
            "jego stan jest zły",
            "stan innych ludzi jest dobry",
            "stan innych ludzi jest zły",
            "Nie dotyczy / trudno powiedzieć",
        ],
    ),
    "zaufanie": (
        "W odniesieniu do zaufania do nieznajomych, nadawca wskazuje że:",
        [
            "nie ma zaufania",
            "ma zaufanie",
            "inni ludzie nie mają zaufania",
            "inni ludzie mają zaufanie",
            "Nie dotyczy / trudno powiedzieć",
        ],
    ),
    "klimat": (
        "W odniesieniu do gotowości do zmiany stylu życia dla klimatu, nadawca wskazuje że:",
        [
            "nie ma gotowości",
            "ma gotowość",
            "inni ludzie wyrażają brak gotowości",
            "inni ludzie wyrażają gotowość",
            "Nie dotyczy / trudno powiedzieć",
        ],
    ),
    "sprawczosc": (
        "W odniesieniu do możliwości wpływania na politykę w Polsce, nadawca wskazuje że:",
        [
            "ma możliwość wpływu",
            "nie ma możliwości wpływu",
            "inni ludzie mają możliwość wpływu",
            "inni ludzie nie mają możliwości wpływu",
            "Nie dotyczy / trudno powiedzieć",
        ],
    ),
    "imigracja": (
        "W odniesieniu do przyjmowania imigrantów, nadawca wskazuje że:",
        [
            "jest przeciwny imigracji",
            "popiera imigrację",
            "inni ludzie sprzeciwiają się imigracji",
            "inni ludzie popierają imigrację",
            "Nie dotyczy / trudno powiedzieć",
        ],
    ),
    "szczepionki": (
        "W odniesieniu do zaufania wobec szczepień i szczepionek, nadawca wskazuje że:",
        [
            "nie ma zaufania",
            "ma zaufanie",
            "inni ludzie nie mają zaufania",
            "inni ludzie mają zaufanie",
            "Nie dotyczy / trudno powiedzieć",
        ],
    ),
    "naukowcy": (
        "W odniesieniu do zaufania do nauki i naukowców, nadawca wskazuje że:",
        [
            "nie ma zaufania",
            "ma zaufanie",
            "inni ludzie nie mają zaufania",
            "inni ludzie mają zaufanie",
            "Nie dotyczy / trudno powiedzieć",
        ],
    ),
}

# Intent question (for “INNE”)
INTENT_QUESTION = (
    "Główna intencja wypowiedzi nadawcy to:",
    [
        "Informowanie i dzielenie się treściami",
        "Poszukiwanie informacji i opinii",
        "Perswazja i mobilizacja",
        "Ocena i reakcje emocjonalne",
        "Autoprezentacja",
        "Rozrywka",
    ],
)

PRIMARY = "#7c3aed"

STYLE = f"""
* {{ font-size: 20px; }}
QWidget {{ background: #131933; color: #f1f5f9; }}
QLabel#muted {{ color: #cbd5e1; }}

QToolBar {{
    background: #0f152b;
    border-bottom: 1px solid #334155;
}}

QFrame#Card {{
    background: #0f1530;
    border: 1px solid #475569;
    border-radius: 14px;
}}

QLabel#TweetText {{
    border: none;
    background: transparent;
    padding: 12px;
}}

QPushButton {{
    background: #162045;
    border: 1px solid #475569;
    border-radius: 10px;
    padding: 10px 14px;
}}
QPushButton:hover {{ background: #1a2853; }}
QPushButton#primary {{
    background: {PRIMARY};
    border: none;
    color: #eef2ff;
    font-weight: 600;
}}
QPushButton#primary:hover {{ background: #6d28d9; }}
QPushButton#ghost {{
    background: transparent;
    border: 1px solid #64748b;
    color: #e2e8f0;
}}

/* Tiles (square) */
QPushButton#TileButton {{
    background: #0e1533;
    border: 2px solid #3b82f6;
    color: #e9d5ff;
    font-weight: 600;
    border-radius: 14px;
    padding: 0;
}}
QPushButton#TileButton:hover {{ border-color: #60a5fa; }}
QPushButton#TileButton:checked {{
    background: {PRIMARY};
    border-color: #a78bfa;
    color: #ffffff;
}}

/* Follow-up choice buttons */
QPushButton#ChoiceBtn {{
    background: #0e1533;
    border: 1px solid #475569;
    border-radius: 12px;
    padding: 12px 14px;
    text-align: center;
}}
QPushButton#ChoiceBtn:hover {{ border-color: #64748b; }}
QPushButton#ChoiceBtn:checked {{
    background: {PRIMARY};
    border-color: #a78bfa;
    color: #ffffff;
}}

/* Tweet zoom buttons (tiny, inside tweet card, top-right) */
QPushButton#ZoomBtn {{
    background: rgba(22,32,69,0.8);
    border: 1px solid #475569;
    border-radius: 8px;
    padding: 2px 8px;
    min-width: 28px;
}}
QPushButton#ZoomBtn:hover {{ background: #1a2853; }}

"""
STYLE_MENUS = """
/* ===== Menubar (Windows/Linux in-window) ===== */
QMenuBar {
    background: #0f152b;
    border-bottom: 1px solid #334155;
}
QMenuBar::item {
    padding: 6px 12px;
    margin: 2px 4px;
    color: #e2e8f0;
    background: transparent;
    border-radius: 6px;
}
QMenuBar::item:selected { /* hover */
    background: #1a2853;
    color: #ffffff;
}
QMenuBar::item:pressed {
    background: #233066;
}

/* ===== Dropdown menus ===== */
QMenu {
    background: #0f1530;
    border: 1px solid #475569;
    padding: 6px 0;
}
QMenu::separator {
    height: 1px;
    background: #334155;
    margin: 6px 10px;
}
QMenu::item {
    padding: 8px 18px;
    color: #e2e8f0;
    background: transparent;
}
QMenu::item:selected {      /* hover item */
    background: #1a2853;
    color: #ffffff;
}
QMenu::item:disabled {
    color: #94a3b8;
}
"""

STYLE = STYLE + STYLE_MENUS

# ================== DB helpers & schema ==================
def _column_exists(con, table, column) -> bool:
    cur = con.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return any(r[1] == column for r in cur.fetchall())

def ensure_db():
    os.makedirs(APP_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS datasets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            source_path TEXT,
            created_at TEXT NOT NULL,
            cursor INTEGER DEFAULT 0,
            total  INTEGER DEFAULT 0,
            exported INTEGER DEFAULT 0
        )
    """)

    # base binary columns (incl. inne)
    cols = ", ".join(f"{col} INTEGER DEFAULT 0" for _, col in LABELS)
    # detail columns (except 'inne')
    detail_cols = ", ".join(f"{col}_detail INTEGER DEFAULT -1" for _, col in LABELS if col != "inne")

    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS tweets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dataset_id INTEGER NOT NULL,
            idx INTEGER NOT NULL,
            text TEXT NOT NULL,
            annotated INTEGER DEFAULT 0,
            {cols},
            {detail_cols},
            intent INTEGER DEFAULT -1,
            stance INTEGER DEFAULT 0,
            time_spent_ms INTEGER DEFAULT 0,
            FOREIGN KEY(dataset_id) REFERENCES datasets(id)
        )
    """)
    con.commit()

    # Migrations (fix missing columns in existing DBs)
    for _, col in LABELS:
        if not _column_exists(con, "tweets", col):
            cur.execute(f"ALTER TABLE tweets ADD COLUMN {col} INTEGER DEFAULT 0")
            con.commit()
    for _, col in LABELS:
        if col == "inne":
            continue
        det = f"{col}_detail"
        if not _column_exists(con, "tweets", det):
            cur.execute(f"ALTER TABLE tweets ADD COLUMN {det} INTEGER DEFAULT -1")
            con.commit()
    if not _column_exists(con, "tweets", "intent"):
        cur.execute("ALTER TABLE tweets ADD COLUMN intent INTEGER DEFAULT -1")
        con.commit()
    if not _column_exists(con, "tweets", "stance"):
        cur.execute("ALTER TABLE tweets ADD COLUMN stance INTEGER DEFAULT 0")
        con.commit()
    if not _column_exists(con, "tweets", "time_spent_ms"):
        cur.execute("ALTER TABLE tweets ADD COLUMN time_spent_ms INTEGER DEFAULT 0")
        con.commit()

    return con

def create_dataset_from_csv(con, csv_path):
    rows = []
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if "tweets" not in reader.fieldnames:
            raise ValueError("CSV musi mieć kolumnę 'tweets'.")
        for r in reader:
            txt = (r.get("tweets") or "").strip()
            if txt:
                rows.append(txt)
    if not rows:
        raise ValueError("Brak tweetów do zaimportowania.")

    cur = con.cursor()
    cur.execute("""
        INSERT INTO datasets (name, source_path, created_at, cursor, total, exported)
        VALUES (?, ?, ?, 0, ?, 0)
    """, (
        os.path.basename(csv_path),
        os.path.abspath(csv_path),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        len(rows),
    ))
    ds_id = cur.lastrowid

    cur.executemany("""
        INSERT INTO tweets (dataset_id, idx, text)
        VALUES (?, ?, ?)
    """, [(ds_id, i, t) for i, t in enumerate(rows)])

    con.commit()
    return ds_id, len(rows)

def load_active_dataset(con):
    settings = QSettings(ORG_NAME, APP_NAME)
    ds_id = settings.value("active_dataset_id", type=int)
    if not ds_id:
        return None

    cur = con.cursor()
    cur.execute("SELECT id, cursor, total, exported FROM datasets WHERE id=?", (ds_id,))
    row = cur.fetchone()
    if not row:
        return None
    _id, cursor, total, exported = row
    if exported:
        return None
    return _id, cursor, total

def set_active_dataset(ds_id):
    settings = QSettings(ORG_NAME, APP_NAME)
    if ds_id is None:
        settings.remove("active_dataset_id")
    else:
        settings.setValue("active_dataset_id", ds_id)

def get_tweet_row(con, ds_id, idx):
    cur = con.cursor()
    detail_cols = [f"{col}_detail" for _, col in LABELS if col != "inne"]
    select_cols = ", ".join([
        *(col for _, col in LABELS),
        *detail_cols,
        "COALESCE(intent, -1)",
        "COALESCE(time_spent_ms,0)"
    ])
    cur.execute(f"""
        SELECT id, text, annotated, {select_cols}
        FROM tweets
        WHERE dataset_id=? AND idx=?
    """, (ds_id, idx))
    return cur.fetchone()

def save_labels_for(con, tweet_id, label_values: dict, mark_annotated=True):
    sets = []
    vals = []
    for _, col in LABELS:
        sets.append(f"{col}=?")
        vals.append(1 if label_values.get(col, 0) else 0)
    if mark_annotated:
        sets.append("annotated=?")
        vals.append(1)
    vals.append(tweet_id)
    sql = f"UPDATE tweets SET {', '.join(sets)} WHERE id=?"
    cur = con.cursor()
    cur.execute(sql, vals)
    con.commit()

def save_detail(con, tweet_id: int, topic_col: str, option_idx: int):
    cur = con.cursor()
    cur.execute(f"UPDATE tweets SET {topic_col}_detail=? , annotated=1 WHERE id=?", (int(option_idx), tweet_id))
    con.commit()

def clear_detail(con, tweet_id: int, topic_col: str):
    cur = con.cursor()
    cur.execute(f"UPDATE tweets SET {topic_col}_detail=-1 WHERE id=?", (tweet_id,))
    con.commit()

def save_intent(con, tweet_id: int, option_idx: int):
    cur = con.cursor()
    cur.execute("UPDATE tweets SET intent=?, annotated=1 WHERE id=?", (int(option_idx), tweet_id))
    con.commit()

def clear_intent(con, tweet_id: int):
    cur = con.cursor()
    cur.execute("UPDATE tweets SET intent=-1 WHERE id=?", (tweet_id,))
    con.commit()

def set_dataset_cursor(con, ds_id, new_cursor):
    cur = con.cursor()
    cur.execute("UPDATE datasets SET cursor=? WHERE id=?", (new_cursor, ds_id))
    con.commit()

def count_annotated(con, ds_id):
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM tweets WHERE dataset_id=? AND annotated=1", (ds_id,))
    done = cur.fetchone()[0]
    cur.execute("SELECT total FROM datasets WHERE id=?", (ds_id,))
    total = cur.fetchone()[0]
    return done, total

def export_dataset_to_csv(con, ds_id, out_path):
    cur = con.cursor()
    cols_db = [col for _, col in LABELS]
    detail_cols = [f"{col}_detail" for _, col in LABELS if col != "inne"]
    select_cols = ", ".join([
        "text",
        *cols_db,
        *detail_cols,
        "COALESCE(intent,-1)",
        "COALESCE(time_spent_ms,0)"
    ])
    cur.execute(f"""
        SELECT {select_cols}
        FROM tweets
        WHERE dataset_id=?
        ORDER BY idx ASC
    """, (ds_id,))
    rows = cur.fetchall()

    headers = ["tweets"] \
        + [name for name, _ in LABELS] \
        + [f"{name}_doprecyz." for name, col in LABELS if col != "inne"] \
        + ["Intencja", "Czas_s"]

    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in rows:
            text = r[0]
            label_vals = [int(v or 0) for v in r[1:1+len(LABELS)]]
            det_start = 1 + len(LABELS)
            det_end = det_start + len(detail_cols)
            details_vals = [int(v) for v in r[det_start:det_end]]
            intent_val = int(r[det_end])
            t_ms = int(r[det_end+1] or 0)
            t_sec = round(t_ms / 1000.0, 3)
            w.writerow([text, *label_vals, *details_vals, intent_val, t_sec])

# ================== UI helpers ==================
class SquareTile(QPushButton):
    """A square, checkable tile; height is controlled by parent row."""
    def __init__(self, caption: str):
        super().__init__(caption)
        self.setObjectName("TileButton")
        self.setCheckable(True)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)  # height set by parent
        self.setFocusPolicy(Qt.NoFocus)
        f = self.font(); f.setPointSize(f.pointSize() + 1); self.setFont(f)

class ChoiceRow(QWidget):
    """
    One row of centered, evenly-sized radio-like buttons (exclusive).
    """
    def __init__(self, on_choice):
        super().__init__()
        self.on_choice = on_choice
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: list[QPushButton] = []

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(10)

    def build(self, options: list[str], current_idx: int | None):
        # clear previous
        for b in self.buttons:
            self.group.removeButton(b)
            b.setParent(None)
        self.buttons = []

        for i, txt in enumerate(options):
            btn = QPushButton(txt)
            btn.setObjectName("ChoiceBtn")
            btn.setCheckable(True)
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setMinimumHeight(48)
            btn.setMaximumHeight(60)
            btn.setMinimumWidth(CHOICE_BTN_MIN_W)
            self.group.addButton(btn, i)
            self.layout.addWidget(btn, 1)
            self.buttons.append(btn)

        if current_idx is not None and 0 <= current_idx < len(self.buttons):
            self.buttons[current_idx].setChecked(True)

        self.group.idToggled.connect(self._on_toggled)

    def _on_toggled(self, idx: int, checked: bool):
        if checked:
            self.on_choice(idx)

# ================== Main window ==================
class TaggerWindow(QMainWindow):
    def __init__(self, con):
        super().__init__()
        self.con = con
        self.ds_id = None
        self.cursor = 0
        self.total = 0
        self._loading = False

        self._current_tweet_id = None
        self._last_start_mono = None

        self.setWindowTitle("Tagowanie Tweetów")
        self.setMinimumSize(1040, 720)

        self.setStyleSheet(STYLE)
        f = QFont(); f.setPointSize(10)
        self.setFont(f)

        icon = QIcon(ICON_FALLBACK) if ICON_FALLBACK and os.path.exists(ICON_FALLBACK) \
               else (QIcon.fromTheme("notebook") or self.style().standardIcon(QStyle.SP_FileDialogInfoView))
        self.setWindowIcon(icon)

        # Toolbar

        self.act_import = QAction("Importuj CSV", self)
        self.act_import.setShortcut(QKeySequence("Ctrl+I"))
        self.act_import.triggered.connect(self.on_import_csv)

        self.act_export = QAction("Eksportuj", self)
        self.act_export.setShortcut(QKeySequence("Ctrl+E"))
        self.act_export.triggered.connect(self.on_export)

        # Extra actions used in the menu bar
        self.act_quit = QAction("Zakończ", self)
        self.act_quit.setShortcut(QKeySequence.Quit)
        self.act_quit.setMenuRole(QAction.QuitRole)  # macOS: moves to app menu
        self.act_quit.triggered.connect(self.close)

        self.act_about = QAction("O TweetTagger", self)
        self.act_about.setMenuRole(QAction.AboutRole)  # macOS: moves to app menu
        self.act_about.triggered.connect(
            lambda: QMessageBox.information(
                self, "O TweetTagger",
                "TweetTagger — lekka aplikacja do adnotacji.\n© IFIS PAN"
            )
        )



        # ---- Menu bar (native on macOS) ----
        mb = self.menuBar()  # on macOS this becomes the system menu bar
        # File
        m_file = mb.addMenu("Plik")
        m_file.addAction(self.act_import)
        m_file.addAction(self.act_export)
        m_file.addSeparator()
        m_file.addAction(self.act_quit)

        # Help
        m_help = mb.addMenu("Pomoc")
        m_help.addAction(self.act_about)

        # Make it feel native on macOS, keep toolbar on other OSes
        if sys.platform == "darwin":
            # Use the OS menu bar (default), and hide the in-window toolbar
            mb.setNativeMenuBar(True)
        else:
            # On Windows/Linux keep the toolbar (and an in-window menu if you want)
            mb.setNativeMenuBar(False)  # visible inside the window (optional)

        self.status_lbl = QLabel("Brak sesji"); self.status_lbl.setObjectName("muted")
        wa = QWidgetAction(self)
        w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(8,0,8,0)
        h.addWidget(self.status_lbl); h.addStretch(1)
        wa.setDefaultWidget(w)

        # Central layout
        central = QWidget()
        root = QVBoxLayout(central); root.setContentsMargins(18, 16, 18, 16); root.setSpacing(14)

        header = QHBoxLayout()
        self.lbl_pos = QLabel("—/—"); self.lbl_pos.setObjectName("muted")
        header.addWidget(self.lbl_pos); header.addStretch(1)
        root.addLayout(header)

        # Tweet card
        tweet_card = QFrame(); tweet_card.setObjectName("Card")
        tv = QVBoxLayout(tweet_card); tv.setContentsMargins(16, 12, 16, 12); tv.setSpacing(8)

        # zoom controls inside tweet card (top-right)
        zoom_row = QHBoxLayout(); zoom_row.setContentsMargins(0,0,0,0)
        zoom_row.addStretch(1)
        self.btn_zoom_minus = QPushButton("−"); self.btn_zoom_minus.setObjectName("ZoomBtn")
        self.btn_zoom_plus  = QPushButton("+"); self.btn_zoom_plus.setObjectName("ZoomBtn")
        self.btn_zoom_minus.clicked.connect(lambda: self._adjust_tweet_font(-1))
        self.btn_zoom_plus.clicked.connect(lambda: self._adjust_tweet_font(+1))
        zoom_row.addWidget(self.btn_zoom_minus); zoom_row.addWidget(self.btn_zoom_plus)
        tv.addLayout(zoom_row)

        self.tweet_view = QLabel()
        self.tweet_view.setObjectName("TweetText")
        self.tweet_view.setWordWrap(True)
        self.tweet_view.setAlignment(Qt.AlignCenter)
        self.tweet_view.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.tweet_view.setOpenExternalLinks(True)
        self.tweet_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._tweet_font_pt = 12
        self._current_tweet_text = ""  # <— add this line
        ft = QFont(self.font()); ft.setPointSize(self._tweet_font_pt); self.tweet_view.setFont(ft)

        tv.addWidget(self.tweet_view, 1)
        root.addWidget(tweet_card, 1)

        # Tiles row (kept shallow; tiles themselves are sized square by parent)
        self.tiles_card = QFrame(); self.tiles_card.setObjectName("Card")
        tiles_sp = self.tiles_card.sizePolicy()
        tiles_sp.setVerticalPolicy(QSizePolicy.Fixed)
        tiles_sp.setHorizontalPolicy(QSizePolicy.Expanding)
        self.tiles_card.setSizePolicy(tiles_sp)

        self.tl = QHBoxLayout(self.tiles_card)
        self.tl.setContentsMargins(16, 10, 16, 10)
        self.tl.setSpacing(12)

        self.tiles: dict[str, SquareTile] = {}
        for (label, col) in LABELS:
            tile = SquareTile(label)
            tile.toggled.connect(self.on_tile_toggled)
            self.tl.addWidget(tile, 1)
            self.tiles[col] = tile
        root.addWidget(self.tiles_card)

        # Follow-up panel (elastic height; scroll whenever content taller than viewport)
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.NoFrame)
        self.detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.detail_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.detail_host = QWidget()
        self.detail_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)  # content reports its min height
        self.detail_vbox = QVBoxLayout(self.detail_host)
        self.detail_vbox.setContentsMargins(0, 0, 0, 0)
        self.detail_vbox.setSpacing(10)
        self.detail_scroll.setWidget(self.detail_host)

        # Give it a small base minimum so it can shrink when the window gets short.
        # We do NOT set a large minimum or a maximum — the layout will give it extra space.
        self.detail_scroll.setMinimumHeight(140)

        # Make the scroll area the ONLY vertically stretchable section:
        # tweet_card and tiles_card remain fixed; this consumes the leftover.
        root.addWidget(self.detail_scroll, 1)

        # Navigation
        nav_card = QFrame(); nav_card.setObjectName("Card")
        nv = QHBoxLayout(nav_card); nv.setContentsMargins(12, 10, 12, 10); nv.setSpacing(10)
        self.btn_back = QPushButton("← Wstecz"); self.btn_back.setObjectName("ghost"); self.btn_back.clicked.connect(self.on_back)
        self.btn_next = QPushButton("Dalej →"); self.btn_next.setObjectName("primary"); self.btn_next.clicked.connect(self.on_next)
        nv.addWidget(self.btn_back); nv.addStretch(1); nv.addWidget(self.btn_next)
        root.addWidget(nav_card)

        # Progress
        self.progress = QLabel("Postęp: —"); self.progress.setObjectName("muted")
        root.addWidget(self.progress)

        self.setCentralWidget(central)
        self._make_shortcuts()
        self.restore_window_state()
        self.update_ui_enabled(False)

        # Resume session
        state = load_active_dataset(self.con)
        if state:
            self.load_dataset(*state)
        else:
            self._show_tweet_centered("Zaimportuj CSV z kolumną 'tweets'…")
            self._clear_detail_panels()

        # size the tiles nicely at start
        self._resize_tiles_square()
        self._enforce_min_window_width()

    def _enforce_min_window_width(self):
        """Prevent shrinking below the width where either tiles or follow-up rows would overflow."""
        # tiles requirement
        n_tiles = len(self.tiles)
        tiles_row = (
                ROOT_SIDE_MARGINS * 2 +
                CARD_SIDE_MARGINS * 2 +
                n_tiles * TILE_MIN_SIDE +
                (n_tiles - 1) * TILES_SPACING
        )

        # worst follow-up row requirement: 5 buttons
        n_btn = 5
        followups_row = (
                ROOT_SIDE_MARGINS * 2 +
                CARD_SIDE_MARGINS * 2 +
                n_btn * CHOICE_BTN_MIN_W +
                (n_btn - 1) * ROW_SPACING
        )

        required = max(tiles_row, followups_row, 800)  # 800 is a sane floor
        # Only raise the minimum; don't force growing if the user already has a wider window.
        self.setMinimumWidth(int(required))

    def _update_detail_host_minheight(self):
        """Make the scroll area show a vertical scrollbar whenever total content is taller than its viewport."""
        layout = self.detail_vbox
        if not layout:
            return
        m = layout.contentsMargins()
        spacing = layout.spacing()

        total = m.top() + m.bottom()
        for i in range(layout.count()):
            item = layout.itemAt(i)
            w = item.widget() if item else None
            if w is not None:
                total += w.sizeHint().height()
                if i < layout.count() - 1:
                    total += spacing

        # Make content large enough (in minimum height sense) to trigger the scrollbar when needed
        self.detail_host.setMinimumHeight(total)

    # ---------- Helpers ----------
    def _adjust_tweet_font(self, delta: int):
        self._tweet_font_pt = max(8, min(28, self._tweet_font_pt + delta))
        # Re-render the HTML with the new font size
        self._show_tweet_centered(self._current_tweet_text)

    def _autolink_html(self, text: str) -> str:
        esc = html.escape(text)
        esc = re.sub(r'(https?://\S+)', r'<a href="\\1">\\1</a>', esc)
        return f'<div style="text-align:center; line-height:1.45; font-size:{self._tweet_font_pt}pt;">{esc}</div>'

    def _show_tweet_centered(self, text: str):
        self._current_tweet_text = text  # <— remember the plain text
        esc = html.escape(text)
        esc = re.sub(r'(https?://\S+)', r'<a href="\\1">\\1</a>', esc)
        html_snippet = (
            f'<div style="text-align:center; line-height:1.45; font-size:{self._tweet_font_pt}pt;">{esc}</div>'
        )
        self.tweet_view.setText(html_snippet)

    def _stop_timer(self):
        if self._current_tweet_id is None or self._last_start_mono is None:
            return
        elapsed_ms = int((time.monotonic() - self._last_start_mono) * 1000)
        if elapsed_ms > 0:
            cur = self.con.cursor()
            cur.execute(
                "UPDATE tweets SET time_spent_ms = COALESCE(time_spent_ms,0) + ? WHERE id=?",
                (elapsed_ms, self._current_tweet_id)
            )
            self.con.commit()
        self._last_start_mono = None

    def _start_timer(self, tweet_id: int):
        self._current_tweet_id = tweet_id
        self._last_start_mono = time.monotonic()

    def _make_shortcuts(self):
        act_next = QAction(self); act_next.setShortcut(QKeySequence.MoveToNextChar); act_next.triggered.connect(self.on_next); self.addAction(act_next)
        act_prev = QAction(self); act_prev.setShortcut(QKeySequence.MoveToPreviousChar); act_prev.triggered.connect(self.on_back); self.addAction(act_prev)
        act_next2 = QAction(self); act_next2.setShortcut(QKeySequence("Ctrl+Return")); act_next2.triggered.connect(self.on_next); self.addAction(act_next2)

    # ---------- Tile sizing ----------
    def _resize_tiles_square(self):
        """Make every tile a perfect square based on available row width."""
        if not hasattr(self, "tl") or not self.tiles:
            return
        left = self.tl.contentsMargins().left()
        right = self.tl.contentsMargins().right()
        spacing = self.tl.spacing()
        n = len(self.tiles)
        content_w = max(0, self.tiles_card.width() - left - right)
        cell_w = (content_w - spacing * (n - 1)) / n if n else 0
        side = int(max(TILE_MIN_SIDE, min(cell_w, TILE_MAX_SIDE)))
        for btn in self.tiles.values():
            btn.setMinimumHeight(side)
            btn.setMaximumHeight(side)
        row_h = side + self.tl.contentsMargins().top() + self.tl.contentsMargins().bottom()
        self.tiles_card.setMinimumHeight(row_h)
        self.tiles_card.setMaximumHeight(row_h)

    # ---------- Follow-up panel ----------
    def _clear_detail_panels(self):
        while self.detail_vbox.count():
            item = self.detail_vbox.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)

    def _make_detail_panel(self, title: str, options: list[str], current_idx: int | None, on_choice_cb):
        card = QFrame(); card.setObjectName("Card")
        lay = QVBoxLayout(card); lay.setContentsMargins(16, 12, 16, 10); lay.setSpacing(10)

        lab = QLabel(title)
        lab.setWordWrap(True)
        lab.setAlignment(Qt.AlignCenter)  # centered question text
        lay.addWidget(lab)

        row = ChoiceRow(on_choice_cb)
        row.build(options, current_idx)
        lay.addWidget(row)
        return card

    def _measure_card_height_for_three(self) -> int:
        """
        Build an offscreen reference card (worst-case question), measure its sizeHint,
        and reserve height for EXACTLY 3 such cards (no first-click jump).
        """
        ref_title = "W odniesieniu do możliwości wpływania na politykę w Polsce, nadawca wskazuje że:"
        ref_opts = [
            "opcja 1", "opcja 2", "opcja 3", "opcja 4", "Nie dotyczy / trudno powiedzieć"
        ]
        ref = self._make_detail_panel(ref_title, ref_opts, None, lambda _: None)
        ref.setParent(self)  # keep within app for style metrics
        h = ref.sizeHint().height() + 12  # small buffer per card
        ref.setParent(None)
        spacing = 10
        cushion = 20
        return h * 3 + spacing * 2 + cushion

    def _rebuild_detail_panels(self):
        """Render follow-ups for all active categories (+ intent if 'inne')."""
        self._clear_detail_panels()

        if not self.ds_id:
            return

        row = get_tweet_row(self.con, self.ds_id, self.cursor)
        if not row:
            return

        labels_count = len(LABELS)
        label_vals = {col: bool(v) for (col, v) in zip([c for _, c in LABELS], row[3:3 + labels_count])}
        detail_cols = [c for _, c in LABELS if c != "inne"]
        details_start = 3 + labels_count
        details_vals = {}
        for i, det_col in enumerate(detail_cols):
            details_vals[f"{det_col}_detail"] = int(row[details_start + i])
        intent_val = int(row[details_start + len(detail_cols)])

        active_topics = [col for col, active in label_vals.items() if active and col in DETAIL_QUESTIONS]
        want_intent = label_vals.get("inne", False)

        for col in active_topics:
            qtxt, opts = DETAIL_QUESTIONS[col]
            cur_idx = details_vals.get(f"{col}_detail", -1)
            cur_idx = cur_idx if cur_idx >= 0 else None

            def make_cb(topic=col):
                return lambda idx: self._save_detail_choice(topic, idx)

            panel = self._make_detail_panel(qtxt, opts, cur_idx, make_cb())
            self.detail_vbox.addWidget(panel)
        self._update_detail_host_minheight()
        self._enforce_min_window_width()

        if want_intent:
            qtxt, opts = INTENT_QUESTION
            cur_idx = intent_val if intent_val >= 0 else None
            panel = self._make_detail_panel(qtxt, opts, cur_idx, self._save_intent_choice)
            self.detail_vbox.addWidget(panel)

    # ---------- Save handlers ----------
    def _save_detail_choice(self, topic_col: str, idx: int):
        if self._loading or not self.ds_id:
            return
        row = get_tweet_row(self.con, self.ds_id, self.cursor)
        if not row:
            return
        tweet_id = row[0]
        save_detail(self.con, tweet_id, topic_col, idx)
        self.refresh_progress()

    def _save_intent_choice(self, idx: int):
        if self._loading or not self.ds_id:
            return
        row = get_tweet_row(self.con, self.ds_id, self.cursor)
        if not row:
            return
        tweet_id = row[0]
        save_intent(self.con, tweet_id, idx)
        self.refresh_progress()

    # ---------- Required follow-ups validation ----------
    def _validate_required_followups(self) -> tuple[bool, str]:
        """
        Returns (ok, message).
        ok == False -> message explains what is missing.
        """
        row = get_tweet_row(self.con, self.ds_id, self.cursor)
        if not row:
            return True, ""

        labels_count = len(LABELS)
        vals = {col: bool(v) for (col, v) in zip([c for _, c in LABELS], row[3:3 + labels_count])}
        detail_cols = [c for _, c in LABELS if c != "inne"]
        details_start = 3 + labels_count
        details_vals = {}
        for i, det_col in enumerate(detail_cols):
            details_vals[f"{det_col}_detail"] = int(row[details_start + i])
        intent_val = int(row[details_start + len(detail_cols)])

        # check every active topic has detail set
        for col in DETAIL_QUESTIONS.keys():
            if vals.get(col, False):
                if int(details_vals.get(f"{col}_detail", -1)) < 0:
                    # find display name
                    disp = next(name for name, c in LABELS if c == col)
                    return False, f"Zaznacz odpowiedź w pytaniu doprecyzowującym dla kategorii „{disp}”."
        # INNE -> intent required
        if vals.get("inne", False) and intent_val < 0:
            return False, "Zaznacz odpowiedź w pytaniu o główną intencję wypowiedzi (dla „INNE”)."

        return True, ""

    # ---------- Logic ----------
    def update_ui_enabled(self, enabled: bool):
        self.tweet_view.setEnabled(enabled)
        for tile in self.tiles.values():
            tile.setEnabled(enabled)
        self.btn_back.setEnabled(enabled)
        self.btn_next.setEnabled(enabled)
        self.act_export.setEnabled(self.ds_id is not None)
        self.detail_scroll.setEnabled(enabled)

    def load_dataset(self, ds_id, cursor, total):
        self._stop_timer()
        self.ds_id = ds_id
        self.cursor = max(0, min(cursor, total - 1 if total else 0))
        self.total = total
        set_active_dataset(ds_id)
        self.status_lbl.setText(f"Sesja #{ds_id}")
        self.update_ui_enabled(True)
        self.refresh_progress()
        self.load_current_tweet()

    def refresh_progress(self):
        if not self.ds_id:
            self.progress.setText("Postęp: —"); self.lbl_pos.setText("—/—"); return
        done, total = count_annotated(self.con, self.ds_id)
        self.progress.setText(f"Postęp: {done}/{total}")
        self.lbl_pos.setText(f"{self.cursor+1}/{self.total}")
        self.btn_back.setEnabled(self.ds_id is not None and self.cursor > 0)
        self.btn_next.setEnabled(self.ds_id is not None and self.total > 0)

    def load_current_tweet(self):
        self._stop_timer()

        if not self.ds_id or self.total == 0:
            self._show_tweet_centered("Zaimportuj CSV z kolumną 'tweets'…")
            for t in self.tiles.values(): t.setChecked(False)
            self._current_tweet_id = None
            self._loading = False
            self._clear_detail_panels()
            return

        row = get_tweet_row(self.con, self.ds_id, self.cursor)
        if not row: return
        self._loading = True
        tweet_id = row[0]
        text = row[1]

        labels_count = len(LABELS)
        label_vals_seq = row[3:3+labels_count]

        self._show_tweet_centered(text)
        for (name, col), val in zip(LABELS, label_vals_seq):
            self.tiles[col].setChecked(bool(val))

        self._loading = False
        self._start_timer(tweet_id)
        self._rebuild_detail_panels()
        self._resize_tiles_square()

    def on_tile_toggled(self, _checked: bool):
        if self._loading or not self.ds_id:
            return

        # read current DB state BEFORE change to detect which category got unticked
        row = get_tweet_row(self.con, self.ds_id, self.cursor)
        if not row:
            return
        tweet_id = row[0]
        labels_count = len(LABELS)
        prev_vals = {col: bool(v) for (col, v) in zip([c for _, c in LABELS], row[3:3+labels_count])}

        # save new labels
        label_values = {col: self.tiles[col].isChecked() for _, col in LABELS}
        save_labels_for(self.con, tweet_id, label_values, mark_annotated=True)

        # wipe follow-ups for any category that just got unticked
        for _, col in LABELS:
            was = prev_vals.get(col, False)
            now = label_values.get(col, False)
            if was and not now:
                if col == "inne":
                    clear_intent(self.con, tweet_id)
                elif col in DETAIL_QUESTIONS:
                    clear_detail(self.con, tweet_id, col)

        self.refresh_progress()
        self._rebuild_detail_panels()

    def on_next(self):
        if not self.ds_id: return

        ok, msg = self._validate_required_followups()
        if not ok:
            QMessageBox.information(self, "Brak odpowiedzi", msg)
            return

        if self.cursor >= self.total - 1:
            done, total = count_annotated(self.con, self.ds_id)
            if done == total:
                self._stop_timer()
                resp = QMessageBox.question(
                    self, "Zakończono anotacje",
                    "Oznaczono wszystkie tweety.\nCzy chcesz wyeksportować do CSV teraz?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
                )
                if resp == QMessageBox.Yes: self.on_export()
                return
            else:
                self._stop_timer()
                missing = total - done
                resp = QMessageBox.question(
                    self, "Nie wszystkie tweety oznaczone",
                    f"Pozostało {missing} nieoznaczonych tweetów.\nCzy mimo to chcesz wyeksportować?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                if resp == QMessageBox.Yes: self.on_export()
                return

        self.cursor += 1
        set_dataset_cursor(self.con, self.ds_id, self.cursor)
        self.refresh_progress()
        self.load_current_tweet()

    def on_back(self):
        if not self.ds_id or self.cursor <= 0: return
        self.cursor -= 1
        set_dataset_cursor(self.con, self.ds_id, self.cursor)
        self.refresh_progress()
        self.load_current_tweet()

    def on_import_csv(self):
        if self.ds_id is not None:
            QMessageBox.information(
                self, "Import zablokowany",
                "Aby zaimportować nowy plik, najpierw wyeksportuj bieżący CSV."
            )
            return
        path, _ = QFileDialog.getOpenFileName(self, "Wybierz plik CSV", "", "CSV (*.csv)")
        if not path: return
        try:
            ds_id, total = create_dataset_from_csv(self.con, path)
        except Exception as e:
            QMessageBox.critical(self, "Błąd importu", str(e)); return
        self.load_dataset(ds_id, cursor=0, total=total)

    def on_export(self):
        if not self.ds_id:
            QMessageBox.information(self, "Brak sesji", "Najpierw zaimportuj plik CSV.")
            return
        self._stop_timer()

        # build default filename
        cur = self.con.cursor()
        cur.execute("SELECT name FROM datasets WHERE id=?", (self.ds_id,))
        name = cur.fetchone()[0] or f"dataset_{self.ds_id}"
        default_name = os.path.splitext(name)[0] + "_annotated.csv"

        # pick a safe, writable default dir
        docs_dir = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or os.path.expanduser("~")
        settings = QSettings(ORG_NAME, APP_NAME)
        last_dir = settings.value("last_export_dir", docs_dir)
        start_path = os.path.join(last_dir, default_name)

        out_path, _ = QFileDialog.getSaveFileName(
            self, "Zapisz CSV z oznaczeniami", start_path, "CSV (*.csv)"
        )

        if not out_path:
            row = get_tweet_row(self.con, self.ds_id, self.cursor)
            if row: self._start_timer(row[0])
            return

        # ensure the target directory is writable
        target_dir = os.path.dirname(out_path) or docs_dir
        if not os.path.isdir(target_dir):
            try:
                os.makedirs(target_dir, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "Błąd zapisu", f"Nie można utworzyć folderu:\n{target_dir}\n\n{e}")
                row = get_tweet_row(self.con, self.ds_id, self.cursor)
                if row: self._start_timer(row[0])
                return

        if not os.access(target_dir, os.W_OK):
            QMessageBox.critical(
                self, "Błąd zapisu",
                "Wybrany folder nie pozwala na zapis. Wybierz inny (np. Dokumenty)."
            )
            row = get_tweet_row(self.con, self.ds_id, self.cursor)
            if row: self._start_timer(row[0])
            return

        # do the export
        try:
            export_dataset_to_csv(self.con, self.ds_id, out_path)
            # remember last successful folder
            settings.setValue("last_export_dir", target_dir)
        except Exception as e:
            QMessageBox.critical(self, "Błąd eksportu", str(e))
            row = get_tweet_row(self.con, self.ds_id, self.cursor)
            if row: self._start_timer(row[0])
            return

        QMessageBox.information(self, "Eksport zakończony", f"Zapisano plik:\n{os.path.basename(out_path)}")

        set_active_dataset(None)
        self.ds_id = None; self.cursor = 0; self.total = 0
        self.status_lbl.setText("Brak sesji")
        self._current_tweet_id = None
        self._last_start_mono = None
        self._show_tweet_centered("Zaimportuj CSV z kolumną 'tweets'…")
        for t in self.tiles.values(): t.setChecked(False)
        self.update_ui_enabled(False)
        self.refresh_progress()

    def save_window_state(self):
        settings = QSettings(ORG_NAME, APP_NAME)
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())

    def restore_window_state(self):
        settings = QSettings(ORG_NAME, APP_NAME)
        geo = settings.value("geometry")
        if isinstance(geo, QByteArray): self.restoreGeometry(geo)
        st = settings.value("windowState")
        if isinstance(st, QByteArray): self.restoreState(st)

    def closeEvent(self, event: QCloseEvent):
        self._stop_timer()
        self.save_window_state()
        event.accept()

    # keep squares on window resize
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._resize_tiles_square()
        self._update_detail_host_minheight()  # <— add this

def main():
    app = QApplication(sys.argv)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationName(APP_NAME)

    con = ensure_db()
    win = TaggerWindow(con)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
