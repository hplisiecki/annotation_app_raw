import os
import sys
import csv
import sqlite3
from datetime import datetime
import re, html, time  # <-- time added

from PySide6.QtCore import Qt, QSettings, QByteArray
from PySide6.QtGui import QAction, QIcon, QCloseEvent, QKeySequence, QFont, QCursor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QMessageBox, QLabel,
    QFileDialog, QStyle, QFrame, QSizePolicy,
    QToolBar, QWidgetAction
)

# ================== Konfiguracja ==================
APP_NAME = "TweetTagger"
ORG_NAME = "YourOrg"

APP_DIR = os.path.join(os.path.expanduser("~"), ".tweet_tagger")
DB_PATH = os.path.join(APP_DIR, "annotations.sqlite3")

ICON_FALLBACK = None  # opcjonalnie: ścieżka do .ico

LABELS = [
    ("Imigracja",   "imigracja"),
    ("Zaufanie",    "zaufanie"),
    ("Klimat",      "klimat"),
    ("Zdrowie",     "zdrowie"),
    ("Sprawczość",  "sprawczosc"),
    ("Naukowcy",    "naukowcy"),
    ("Szczepionki", "szczepionki"),
]

# Kolor primary (używany przez "Dalej →" i zaznaczone kafelki)
PRIMARY = "#7c3aed"  # violet

STYLE = f"""
/* Brighter indigo base */
* {{ font-size: 13px; }}
QWidget {{ background: #131933; color: #f1f5f9; }}
QLabel#muted {{ color: #cbd5e1; }}

/* Toolbar */
QToolBar {{
    background: #0f152b;
    border-bottom: 1px solid #334155;
}}

/* Cards */
QFrame#Card {{
    background: #0f1530;
    border: 1px solid #475569;
    border-radius: 14px;
}}

/* Tweet text (QLabel) */
QLabel#TweetText {{
    border: none;
    background: transparent;
    padding: 12px;
}}

/* Buttons */
QPushButton {{
    background: #162045;
    border: 1px solid #475569;
    border-radius: 9px;
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

/* Square TileButton (checkable button that stays square and fills width) */
QPushButton#TileButton {{
    background: #0e1533;
    border: 2px solid #3b82f6;        /* blue ring */
    color: #e9d5ff;                    /* soft violet text */
    font-weight: 600;
    border-radius: 12px;               /* rounded square */
    padding: 0;
}}
QPushButton#TileButton:hover {{
    border-color: #60a5fa;
}}
QPushButton#TileButton:checked {{
    background: {PRIMARY};             /* SAME as Next button */
    border-color: #a78bfa;
    color: #ffffff;
}}
"""

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
    cols = ", ".join(f"{col} INTEGER DEFAULT 0" for _, col in LABELS)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS tweets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dataset_id INTEGER NOT NULL,
            idx INTEGER NOT NULL,
            text TEXT NOT NULL,
            annotated INTEGER DEFAULT 0,
            {cols},
            time_spent_ms INTEGER DEFAULT 0,
            FOREIGN KEY(dataset_id) REFERENCES datasets(id)
        )
    """)
    con.commit()

    # Migration: add time_spent_ms if missing on existing DBs
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


def set_active_dataset(ds_id: int | None):
    settings = QSettings(ORG_NAME, APP_NAME)
    if ds_id is None:
        settings.remove("active_dataset_id")
    else:
        settings.setValue("active_dataset_id", ds_id)


def get_tweet_row(con, ds_id, idx):
    cur = con.cursor()
    cur.execute(f"""
        SELECT id, text, annotated, {", ".join(col for _, col in LABELS)}, COALESCE(time_spent_ms,0)
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
    cur.execute(f"""
        SELECT text, {", ".join(cols_db)}, COALESCE(time_spent_ms,0)
        FROM tweets
        WHERE dataset_id=?
        ORDER BY idx ASC
    """, (ds_id,))
    rows = cur.fetchall()

    headers = ["tweets"] + [name for name, _ in LABELS] + ["Czas_s"]
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in rows:
            text = r[0]
            labels_vals = [int(v or 0) for v in r[1:-1]]
            t_ms = int(r[-1] or 0)
            t_sec = round(t_ms / 1000.0, 3)
            w.writerow([text, *labels_vals, t_sec])

    cur.execute("UPDATE datasets SET exported=1 WHERE id=?", (ds_id,))
    con.commit()

# ================== UI helpers ==================
class SquareTile(QPushButton):
    """
    Kwadratowy, checkable kafelek z etykietą w środku.
    - Cały kafelek jest klikalny.
    - Zostaje *kwadratem* podczas zmiany rozmiaru okna.
    """
    def __init__(self, caption: str):
        super().__init__(caption)
        self.setObjectName("TileButton")
        self.setCheckable(True)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setFocusPolicy(Qt.NoFocus)  # nawigacja strzałkami dla tweeta
        f = self.font(); f.setPointSize(f.pointSize() + 1); self.setFont(f)
        self._resizing = False

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._resizing:
            return
        # Zachowaj kształt kwadratu (bok = min(szerokość, dostępna wysokość))
        side = max(86, min(self.width(), self.parentWidget().height() if self.parentWidget() else self.width()))
        try:
            self._resizing = True
            self.setMinimumHeight(side)
            self.setMaximumHeight(side)
        finally:
            self._resizing = False

# ================== Główne okno ==================
class TaggerWindow(QMainWindow):
    def __init__(self, con):
        super().__init__()
        self.con = con
        self.ds_id = None
        self.cursor = 0
        self.total = 0
        self._loading = False

        # timing state
        self._current_tweet_id = None
        self._last_start_mono = None

        self.setWindowTitle("Tagowanie Tweetów")
        self.setMinimumSize(1020, 660)

        self.setStyleSheet(STYLE)
        f = QFont()
        f.setPointSize(10)  # let Qt choose the platform's system font
        self.setFont(f)
        self.setFont(f)

        icon = QIcon(ICON_FALLBACK) if ICON_FALLBACK and os.path.exists(ICON_FALLBACK) \
               else (QIcon.fromTheme("notebook") or self.style().standardIcon(QStyle.SP_FileDialogInfoView))
        self.setWindowIcon(icon)

        # --- Toolbar ---
        tb = QToolBar("Główne", self); tb.setMovable(False); self.addToolBar(tb)

        self.act_import = QAction("Importuj CSV", self)
        self.act_import.setShortcut(QKeySequence("Ctrl+I"))
        self.act_import.triggered.connect(self.on_import_csv)
        tb.addAction(self.act_import)

        self.act_export = QAction("Eksportuj", self)
        self.act_export.setShortcut(QKeySequence("Ctrl+E"))
        self.act_export.triggered.connect(self.on_export)
        tb.addAction(self.act_export)

        tb.addSeparator()
        self.status_lbl = QLabel("Brak sesji"); self.status_lbl.setObjectName("muted")
        wa = QWidgetAction(self)
        w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(8,0,8,0)
        h.addWidget(self.status_lbl); h.addStretch(1)
        wa.setDefaultWidget(w); tb.addAction(wa)

        # --- Central layout ---
        central = QWidget()
        root = QVBoxLayout(central); root.setContentsMargins(18, 16, 18, 16); root.setSpacing(14)

        header = QHBoxLayout()
        self.lbl_pos = QLabel("—/—"); self.lbl_pos.setObjectName("muted")
        header.addWidget(self.lbl_pos); header.addStretch(1)
        root.addLayout(header)

        # Tweet card (QLabel centered both ways, fills available space)
        tweet_card = QFrame(); tweet_card.setObjectName("Card")
        tv = QVBoxLayout(tweet_card); tv.setContentsMargins(16, 14, 16, 14); tv.setSpacing(8)

        self.tweet_view = QLabel()
        self.tweet_view.setObjectName("TweetText")
        self.tweet_view.setWordWrap(True)
        self.tweet_view.setAlignment(Qt.AlignCenter)  # h + v center inside widget
        self.tweet_view.setTextInteractionFlags(Qt.TextBrowserInteraction)  # links + selection
        self.tweet_view.setOpenExternalLinks(True)
        self.tweet_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        ft = QFont(self.font()); ft.setPointSize(12); self.tweet_view.setFont(ft)

        tv.addWidget(self.tweet_view, 1)
        root.addWidget(tweet_card, 1)

        # Tiles row — pełna szerokość, responsywne, kwadratowe
        tiles_card = QFrame(); tiles_card.setObjectName("Card")
        tiles_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        tl = QHBoxLayout(tiles_card); tl.setContentsMargins(16, 12, 16, 12); tl.setSpacing(12)
        self.tiles: dict[str, SquareTile] = {}
        for (label, col) in LABELS:
            tile = SquareTile(label)
            tile.toggled.connect(self.on_tile_toggled)
            tile.setMinimumSize(86, 86)
            tile.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            tl.addWidget(tile, 1)  # równy stretch
            self.tiles[col] = tile
        root.addWidget(tiles_card, 1)

        # Nawigacja
        nav_card = QFrame(); nav_card.setObjectName("Card")
        nv = QHBoxLayout(nav_card); nv.setContentsMargins(12, 10, 12, 10); nv.setSpacing(10)
        self.btn_back = QPushButton("← Wstecz"); self.btn_back.setObjectName("ghost"); self.btn_back.clicked.connect(self.on_back)
        self.btn_next = QPushButton("Dalej →"); self.btn_next.setObjectName("primary"); self.btn_next.clicked.connect(self.on_next)
        nv.addWidget(self.btn_back); nv.addStretch(1); nv.addWidget(self.btn_next)
        root.addWidget(nav_card)

        # Postęp
        self.progress = QLabel("Postęp: —"); self.progress.setObjectName("muted")
        root.addWidget(self.progress)

        self.setCentralWidget(central)
        self._make_shortcuts()
        self.restore_window_state()
        self.update_ui_enabled(False)

        # Wznów poprzednią sesję
        state = load_active_dataset(self.con)
        if state:
            self.load_dataset(*state)
        else:
            self._show_tweet_centered("Zaimportuj CSV z kolumną 'tweets'…")

    # ---------- Helpers for centered tweet ----------
    def _autolink_html(self, text: str) -> str:
        esc = html.escape(text)
        esc = re.sub(r'(https?://\S+)', r'<a href="\\1">\\1</a>', esc)
        return f'<div style="text-align:center; line-height:1.45; font-size:14pt;">{esc}</div>'

    def _show_tweet_centered(self, text: str):
        self.tweet_view.setText(self._autolink_html(text))

    # ---------- Timing helpers ----------
    def _stop_timer(self):
        """Stop timer for the currently displayed tweet and persist elapsed ms."""
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
        self._last_start_mono = None  # keep current_tweet_id; next _start_timer may overwrite

    def _start_timer(self, tweet_id: int):
        self._current_tweet_id = tweet_id
        self._last_start_mono = time.monotonic()

    def _make_shortcuts(self):
        act_next = QAction(self); act_next.setShortcut(QKeySequence.MoveToNextChar); act_next.triggered.connect(self.on_next); self.addAction(act_next)
        act_prev = QAction(self); act_prev.setShortcut(QKeySequence.MoveToPreviousChar); act_prev.triggered.connect(self.on_back); self.addAction(act_prev)
        act_next2 = QAction(self); act_next2.setShortcut(QKeySequence("Ctrl+Return")); act_next2.triggered.connect(self.on_next); self.addAction(act_next2)

    # ---------- Logika UI ----------
    def update_ui_enabled(self, enabled: bool):
        self.tweet_view.setEnabled(enabled)
        for tile in self.tiles.values():
            tile.setEnabled(enabled)
        self.btn_back.setEnabled(enabled)
        self.btn_next.setEnabled(enabled)
        self.act_export.setEnabled(self.ds_id is not None)

    def load_dataset(self, ds_id, cursor, total):
        # when switching datasets, stop timing previous tweet if any
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
        # Stop timing previous tweet (if any) before showing new one/placeholder
        self._stop_timer()

        if not self.ds_id or self.total == 0:
            self._show_tweet_centered("Zaimportuj CSV z kolumną 'tweets'…")
            for t in self.tiles.values(): t.setChecked(False)
            self._current_tweet_id = None
            return

        row = get_tweet_row(self.con, self.ds_id, self.cursor)
        if not row: return
        self._loading = True
        tweet_id = row[0]
        text = row[1]
        # row[2] = annotated
        label_vals = row[3:3+len(LABELS)]
        # row[-1] is time_spent_ms (we don't need it now)

        self._show_tweet_centered(text)
        for (name, col), val in zip(LABELS, label_vals):
            self.tiles[col].setChecked(bool(val))
        self._loading = False

        # Start timing for this tweet
        self._start_timer(tweet_id)

    def on_tile_toggled(self, _checked: bool):
        if self._loading or not self.ds_id:
            return
        row = get_tweet_row(self.con, self.ds_id, self.cursor)
        if not row:
            return
        tweet_id = row[0]
        label_values = {col: self.tiles[col].isChecked() for _, col in LABELS}
        save_labels_for(self.con, tweet_id, label_values, mark_annotated=True)
        self.refresh_progress()

    def on_next(self):
        if not self.ds_id: return
        # persist labels (via toggled handler side effects already), timing is handled in load_current_tweet
        if self.cursor >= self.total - 1:
            done, total = count_annotated(self.con, self.ds_id)
            if done == total:
                # stop timing the last tweet before asking to export
                self._stop_timer()
                resp = QMessageBox.question(
                    self, "Zakończono adnotacje",
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
        # Import zawsze klikalny — jeśli aktywna sesja, pokaż komunikat:
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
            QMessageBox.information(self, "Brak sesji", "Najpierw zaimportuj plik CSV."); return
        # Ensure we capture timing up to the export moment
        self._stop_timer()

        cur = self.con.cursor()
        cur.execute("SELECT name FROM datasets WHERE id=?", (self.ds_id,))
        name = cur.fetchone()[0] or f"dataset_{self.ds_id}"
        default_name = os.path.splitext(name)[0] + "_annotated.csv"

        out_path, _ = QFileDialog.getSaveFileName(self, "Zapisz CSV z oznaczeniami", default_name, "CSV (*.csv)")
        if not out_path:
            # restart timer on current tweet so tracking continues after cancel
            row = get_tweet_row(self.con, self.ds_id, self.cursor)
            if row: self._start_timer(row[0])
            return
        try:
            export_dataset_to_csv(self.con, self.ds_id, out_path)
        except Exception as e:
            QMessageBox.critical(self, "Błąd eksportu", str(e))
            # restart timer since we didn't reset session
            row = get_tweet_row(self.con, self.ds_id, self.cursor)
            if row: self._start_timer(row[0])
            return

        QMessageBox.information(self, "Eksport zakończony", f"Zapisano plik:\n{os.path.basename(out_path)}")

        # Reset po eksporcie -> import odblokowany
        set_active_dataset(None)
        self.ds_id = None; self.cursor = 0; self.total = 0
        self.status_lbl.setText("Brak sesji")
        self._current_tweet_id = None
        self._last_start_mono = None
        self._show_tweet_centered("Zaimportuj CSV z kolumną 'tweets'…")
        for t in self.tiles.values(): t.setChecked(False)
        self.update_ui_enabled(False)
        self.refresh_progress()

    # ---------- Window state ----------
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
        # persist any running timer before exit
        self._stop_timer()
        self.save_window_state()
        event.accept()


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
