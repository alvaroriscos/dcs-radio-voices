"""Ventana principal (PySide6)."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

from PySide6.QtCore import Qt, QObject, QThread, Signal, QTimer, QSize
from PySide6.QtGui import QIcon, QColor, QFont, QPixmap, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QFileDialog, QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QDoubleSpinBox,
    QCheckBox, QSlider, QProgressBar, QPlainTextEdit, QFrame, QMessageBox, QInputDialog, QGridLayout,
    QAbstractItemView, QSizePolicy, QGroupBox,
)

from .config import (APP_NAME, APP_VERSION, Settings, SpeakerSettings, assign_default_voices, role_of,
                     ROLE_LABELS, PLAYER_VOICE, settings_dir)
from .effects import PROFILE_NAMES
from .engines import TTSManager, voice_catalog, voice_by_id, models_dir
from .parser import parse_file, ParsedScript, ScriptLine
from .pipeline import generate_all, preview_line, resolve_profile, normalize, norm_options

ACCENT = "#3fb68b"
STYLE = f"""
* {{ font-family: 'Segoe UI', 'Inter', 'Noto Sans', sans-serif; font-size: 10pt; color: #e6e9ef; }}
QMainWindow, QWidget#root {{ background: #14181f; }}
QLabel#title {{ font-size: 18pt; font-weight: 600; color: #ffffff; }}
QLabel#subtitle {{ color: #8b95a7; }}
QLabel#hint {{ color: #8b95a7; font-size: 9pt; }}
QFrame#card {{ background: #1c222c; border: 1px solid #262e3b; border-radius: 10px; }}
QLabel#cardtitle {{ font-weight: 600; color: #c9d1de; }}
QLineEdit, QComboBox, QDoubleSpinBox, QPlainTextEdit {{
    background: #12161c; border: 1px solid #2c3544; border-radius: 6px; padding: 5px 8px;
    selection-background-color: {ACCENT};
}}
QComboBox QAbstractItemView {{ background: #1c222c; selection-background-color: #2b6b55; }}
QPushButton {{ background: #273041; border: 1px solid #323d50; border-radius: 6px; padding: 6px 14px; }}
QPushButton:hover {{ background: #303b50; }}
QPushButton:disabled {{ color: #5c6677; background: #1d232d; }}
QPushButton#primary {{ background: {ACCENT}; color: #0d1a14; font-weight: 700; border: none; padding: 9px 26px;
    font-size: 11pt; }}
QPushButton#primary:hover {{ background: #52c99d; }}
QPushButton#primary:disabled {{ background: #2a4a3e; color: #6d8a7f; }}
QPushButton#danger {{ background: #4a2a2e; border-color: #6a3a40; }}
QTabWidget::pane {{ border: 1px solid #262e3b; border-radius: 8px; background: #1c222c; top: -1px; }}
QTabBar::tab {{ background: transparent; padding: 8px 16px; color: #8b95a7; border: none; }}
QTabBar::tab:selected {{ color: #ffffff; border-bottom: 2px solid {ACCENT}; }}
QTableWidget {{ background: #161b22; alternate-background-color: #1a2029; gridline-color: #232b37;
    border: none; selection-background-color: #24493d; }}
QHeaderView::section {{ background: #1c222c; color: #8b95a7; border: none; border-bottom: 1px solid #2c3544;
    padding: 6px; font-weight: 600; }}
QProgressBar {{ background: #12161c; border: 1px solid #2c3544; border-radius: 6px; height: 18px;
    text-align: center; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 5px; }}
QSlider::groove:horizontal {{ height: 4px; background: #2c3544; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {ACCENT}; width: 14px; margin: -6px 0; border-radius: 7px; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid #3a465c; border-radius: 4px; background: #12161c; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 14px; background: #273041; border: none; }}
QGroupBox {{ border: 1px solid #262e3b; border-radius: 8px; margin-top: 14px; padding-top: 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #c9d1de; font-weight: 600; }}
QToolTip {{ background: #273041; color: #e6e9ef; border: 1px solid #3a465c; }}
"""


def make_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QBrush(QColor("#1c222c")))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(2, 2, 60, 60, 14, 14)
    pen = QPen(QColor(ACCENT), 4, Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)
    for r in (10, 18, 26):
        p.drawArc(32 - r, 36 - r, 2 * r, 2 * r, 35 * 16, 110 * 16)
    p.setBrush(QBrush(QColor(ACCENT)))
    p.drawEllipse(28, 32, 8, 8)
    p.end()
    return QIcon(pm)


def play_wav(path: str):
    if sys.platform == "win32":
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        return True
    for cmd in (["paplay", path], ["aplay", "-q", path], ["afplay", path]):
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except FileNotFoundError:
            continue
    return False


def stop_audio():
    if sys.platform == "win32":
        import winsound
        winsound.PlaySound(None, 0)


# ----------------------------------------------------------------------------
class Worker(QObject):
    progress = Signal(int, int, str)
    log = Signal(str, str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.cancelled = False

    def run(self):
        try:
            res = self.fn(self)
            self.done.emit(res)
        except Exception as e:
            self.failed.emit(f"{e}\n{traceback.format_exc()}")


def card(title: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.setSpacing(8)
    if title:
        t = QLabel(title)
        t.setObjectName("cardtitle")
        lay.addWidget(t)
    return f, lay


PROFILE_KEYS = ["AUTO", "AIR", "GROUND", "TOWER", "STRESS", "CLEAN"]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = Settings.load()
        self.tts = TTSManager()
        self.script: ParsedScript | None = None
        self.overrides: dict[int, str] = {}
        self.thread: QThread | None = None
        self.worker: Worker | None = None
        self.catalog = voice_catalog()
        self.avail = {v.id for v in self.catalog}
        self._loading = False
        self._pending_done = None
        self.extra_speakers: list[str] = []
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.setWindowIcon(make_icon())
        self.resize(1180, 800)
        self._build()
        self._load_settings_into_ui()
        if not self.catalog:
            self.log("error", f"No se encontraron modelos de voz en {models_dir()}. Reinstala la aplicación.")
        else:
            self.log("info", f"{len(self.catalog)} voces disponibles (offline). Ajustes en {settings_dir()}")
        if self.settings.last_script and Path(self.settings.last_script).exists():
            self.load_script(self.settings.last_script)
        QTimer.singleShot(300, self._warmup)

    # ------------------------------------------------------------------ UI
    def _build(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(18, 14, 18, 14)
        v.setSpacing(12)

        head = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(make_icon().pixmap(42, 42))
        head.addWidget(ic)
        tv = QVBoxLayout()
        t = QLabel(APP_NAME)
        t.setObjectName("title")
        st = QLabel("Convierte el guion .txt de tu misión en audio de radio realista · 100 % offline")
        st.setObjectName("subtitle")
        tv.addWidget(t)
        tv.addWidget(st)
        head.addLayout(tv)
        head.addStretch()
        v.addLayout(head)

        files = QHBoxLayout()
        files.setSpacing(12)
        c1, l1 = card("1 · Guion (.txt)")
        r1 = QHBoxLayout()
        self.script_edit = QLineEdit()
        self.script_edit.setReadOnly(True)
        self.script_edit.setPlaceholderText("Elige el archivo de guion…")
        b1 = QPushButton("Elegir guion…")
        b1.clicked.connect(self.choose_script)
        self.reload_btn = QPushButton("Recargar")
        self.reload_btn.setToolTip("Volver a leer el guion (si lo has editado)")
        self.reload_btn.clicked.connect(lambda: self.script and self.load_script(self.script.path))
        r1.addWidget(self.script_edit)
        r1.addWidget(self.reload_btn)
        r1.addWidget(b1)
        l1.addLayout(r1)
        self.script_info = QLabel("Sin guion cargado")
        self.script_info.setObjectName("hint")
        l1.addWidget(self.script_info)
        files.addWidget(c1, 3)

        c2, l2 = card("2 · Carpeta de salida")
        r2 = QHBoxLayout()
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("Elige dónde guardar los .ogg…")
        self.out_edit.textChanged.connect(self._save_paths)
        b2 = QPushButton("Elegir carpeta…")
        b2.clicked.connect(self.choose_out)
        r2.addWidget(self.out_edit)
        r2.addWidget(b2)
        l2.addLayout(r2)
        self.out_info = QLabel("Se crearán: «… - COMPLETO.ogg», «… - manifiesto.csv» y la carpeta «lineas»")
        self.out_info.setObjectName("hint")
        l2.addWidget(self.out_info)
        files.addWidget(c2, 2)
        v.addLayout(files)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_lines(), "Líneas")
        self.tabs.addTab(self._tab_voices(), "Voces")
        self.tabs.addTab(self._tab_effects(), "Efectos y salida")
        self.tabs.addTab(self._tab_lexicon(), "Pronunciación")
        self.tabs.addTab(self._tab_log(), "Registro")
        v.addWidget(self.tabs, 1)

        bottom = QHBoxLayout()
        pv = QVBoxLayout()
        self.status = QLabel("Listo")
        self.status.setObjectName("hint")
        self.pbar = QProgressBar()
        self.pbar.setValue(0)
        pv.addWidget(self.status)
        pv.addWidget(self.pbar)
        bottom.addLayout(pv, 1)
        self.cancel_btn = QPushButton("Cancelar")
        self.cancel_btn.setObjectName("danger")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel)
        self.open_btn = QPushButton("Abrir carpeta")
        self.open_btn.clicked.connect(self.open_out)
        self.gen_btn = QPushButton("Generar todo")
        self.gen_btn.setObjectName("primary")
        self.gen_btn.clicked.connect(self.generate)
        bottom.addWidget(self.open_btn)
        bottom.addWidget(self.cancel_btn)
        bottom.addWidget(self.gen_btn)
        v.addLayout(bottom)

    def _tab_lines(self):
        w = QWidget()
        v = QVBoxLayout(w)
        self.lines_tbl = QTableWidget(0, 6)
        self.lines_tbl.setHorizontalHeaderLabels(["Nº", "Hablante", "Tono", "Efecto", "Texto", "Hilo"])
        self.lines_tbl.setAlternatingRowColors(True)
        self.lines_tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.lines_tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        self.lines_tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.lines_tbl.verticalHeader().setVisible(False)
        hh = self.lines_tbl.horizontalHeader()
        for i, m in enumerate([QHeaderView.ResizeToContents, QHeaderView.ResizeToContents,
                               QHeaderView.Interactive, QHeaderView.ResizeToContents, QHeaderView.Stretch,
                               QHeaderView.Interactive]):
            hh.setSectionResizeMode(i, m)
        self.lines_tbl.setColumnWidth(2, 150)
        self.lines_tbl.setColumnWidth(5, 160)
        self.lines_tbl.itemSelectionChanged.connect(self._line_selected)
        self.lines_tbl.cellDoubleClicked.connect(lambda r, c: self.preview())
        v.addWidget(self.lines_tbl, 1)
        h = QHBoxLayout()
        self.spoken_lbl = QLabel("Selecciona una línea para ver cómo se pronunciará.")
        self.spoken_lbl.setWordWrap(True)
        self.spoken_lbl.setObjectName("hint")
        self.prev_btn = QPushButton("▶  Previsualizar línea")
        self.prev_btn.clicked.connect(self.preview)
        self.stop_btn = QPushButton("■")
        self.stop_btn.setFixedWidth(36)
        self.stop_btn.clicked.connect(stop_audio)
        h.addWidget(self.spoken_lbl, 1)
        h.addWidget(self.stop_btn)
        h.addWidget(self.prev_btn)
        v.addLayout(h)
        return w

    def _tab_voices(self):
        w = QWidget()
        v = QVBoxLayout(w)
        hint = QLabel("Cada hablante tiene su voz. PLAYER usa siempre la misma voz fija. Los cambios se guardan "
                      "solos. Los hablantes nuevos reciben una voz por defecto.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        v.addWidget(hint)
        self.voice_tbl = QTableWidget(0, 8)
        self.voice_tbl.setHorizontalHeaderLabels(["Hablante", "Tipo", "Voz", "Velocidad", "Tono (semit.)",
                                                  "Volumen", "Efecto por defecto", ""])
        self.voice_tbl.verticalHeader().setVisible(False)
        self.voice_tbl.setAlternatingRowColors(True)
        self.voice_tbl.setSelectionMode(QAbstractItemView.NoSelection)
        hh = self.voice_tbl.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        v.addWidget(self.voice_tbl, 1)
        h = QHBoxLayout()
        add = QPushButton("+ Añadir hablante")
        add.clicked.connect(self.add_speaker)
        reset = QPushButton("Restablecer voces por defecto")
        reset.clicked.connect(self.reset_voices)
        h.addWidget(add)
        h.addWidget(reset)
        h.addStretch()
        v.addLayout(h)
        return w

    def _slider(self, lo, hi, val, suffix="%"):
        s = QSlider(Qt.Horizontal)
        s.setRange(lo, hi)
        s.setValue(val)
        lab = QLabel(f"{val}{suffix}")
        lab.setMinimumWidth(48)
        s.valueChanged.connect(lambda x: lab.setText(f"{x}{suffix}"))
        return s, lab

    def _tab_effects(self):
        w = QWidget()
        g = QGridLayout(w)
        g.setHorizontalSpacing(18)

        fxbox = QGroupBox("Efectos de radio")
        fl = QGridLayout(fxbox)
        self.cb_nofx = QCheckBox("Modo sin efectos (voz limpia en todas las líneas)")
        self.cb_player = QCheckBox("PLAYER siempre por radio de cabina")
        self.cb_click = QCheckBox("Clic de micrófono y cola de squelch")
        self.cb_breath = QCheckBox("Respiración en líneas con estrés")
        for i, cb in enumerate([self.cb_nofx, self.cb_player, self.cb_click, self.cb_breath]):
            fl.addWidget(cb, i, 0, 1, 3)
            cb.toggled.connect(self._fx_changed)
        self.sl_int, li = self._slider(0, 200, 100)
        self.sl_var, lv = self._slider(0, 100, 35)
        fl.addWidget(QLabel("Intensidad (ruido, estática)"), 4, 0)
        fl.addWidget(self.sl_int, 4, 1)
        fl.addWidget(li, 4, 2)
        fl.addWidget(QLabel("Variación entre líneas"), 5, 0)
        fl.addWidget(self.sl_var, 5, 1)
        fl.addWidget(lv, 5, 2)
        self.sl_int.valueChanged.connect(self._fx_changed)
        self.sl_var.valueChanged.connect(self._fx_changed)
        info = QLabel("La app elige el efecto por línea: la etiqueta del guion ([AIR], [GROUND], [TOWER], "
                      "[STRESS], [CLEAN]) y, si no hay, el tipo de hablante y el tono (calm → radio limpia; "
                      "stressed/urgente → más estática, respiración y algo más rápido). Puedes forzarlo por "
                      "hablante (pestaña Voces) o por línea (columna Efecto).")
        info.setWordWrap(True)
        info.setObjectName("hint")
        fl.addWidget(info, 6, 0, 1, 3)
        g.addWidget(fxbox, 0, 0, 2, 1)

        outbox = QGroupBox("Archivos de salida")
        ol = QGridLayout(outbox)
        self.cb_comb = QCheckBox("Un .ogg único con todas las líneas")
        self.cb_ind = QCheckBox("Un .ogg por línea (carpeta «lineas»)")
        self.cb_man = QCheckBox("Manifiesto CSV (tiempos de inicio y fin)")
        for i, cb in enumerate([self.cb_comb, self.cb_ind, self.cb_man]):
            ol.addWidget(cb, i, 0, 1, 3)
            cb.toggled.connect(self._fx_changed)
        ol.addWidget(QLabel("Silencio entre líneas"), 3, 0)
        self.sp_gap = QDoubleSpinBox()
        self.sp_gap.setRange(0, 30)
        self.sp_gap.setDecimals(2)
        self.sp_gap.setSingleStep(0.5)
        self.sp_gap.setSuffix(" s")
        self.sp_gap.valueChanged.connect(self._fx_changed)
        ol.addWidget(self.sp_gap, 3, 1)
        self.sl_q, lq = self._slider(10, 100, 60)
        ol.addWidget(QLabel("Calidad OGG"), 4, 0)
        ol.addWidget(self.sl_q, 4, 1)
        ol.addWidget(lq, 4, 2)
        self.sl_q.valueChanged.connect(self._fx_changed)
        fmt = QLabel("OGG Vorbis · mono · 44 100 Hz · misma calidad en el archivo único y en los individuales.\n"
                     "Nombre: HABLANTE NNN PALABRACLAVE Ns.ogg (N = duración real redondeada hacia arriba).")
        fmt.setObjectName("hint")
        fmt.setWordWrap(True)
        ol.addWidget(fmt, 5, 0, 1, 3)
        g.addWidget(outbox, 0, 1)

        pbox = QGroupBox("Fraseología")
        pl = QGridLayout(pbox)
        self.cb_niner = QCheckBox("Decir «niner» para el 9")
        self.cb_niner.toggled.connect(self._fx_changed)
        pl.addWidget(self.cb_niner, 0, 0, 1, 2)
        pl.addWidget(QLabel("Separador de frecuencias"), 1, 0)
        self.cmb_dec = QComboBox()
        self.cmb_dec.addItems(["decimal", "point"])
        self.cmb_dec.currentTextChanged.connect(self._fx_changed)
        pl.addWidget(self.cmb_dec, 1, 1)
        g.addWidget(pbox, 1, 1)
        g.setRowStretch(2, 1)
        return w

    def _tab_lexicon(self):
        w = QWidget()
        v = QVBoxLayout(w)
        hint = QLabel("Diccionario de pronunciación: cómo se dice cada palabra o sigla. Escribe la forma "
                      "fonética en inglés (p. ej. «Mouawad» → «Moo-ah-wad»). Las siglas en MAYÚSCULAS solo "
                      "se aplican si coinciden exactamente.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        v.addWidget(hint)
        self.lex_tbl = QTableWidget(0, 2)
        self.lex_tbl.setHorizontalHeaderLabels(["Palabra en el guion", "Se pronuncia"])
        self.lex_tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.lex_tbl.verticalHeader().setVisible(False)
        self.lex_tbl.setAlternatingRowColors(True)
        self.lex_tbl.itemChanged.connect(self._lex_changed)
        v.addWidget(self.lex_tbl, 1)
        h = QHBoxLayout()
        a = QPushButton("+ Añadir")
        a.clicked.connect(self._lex_add)
        d = QPushButton("– Quitar seleccionada")
        d.clicked.connect(self._lex_del)
        self.lex_test = QLineEdit()
        self.lex_test.setPlaceholderText("Prueba un texto: Cougar11, climb Angels 20, contact 251.000…")
        self.lex_out = QLabel("")
        self.lex_out.setObjectName("hint")
        self.lex_out.setWordWrap(True)
        self.lex_test.textChanged.connect(
            lambda t: self.lex_out.setText("→ " + normalize(t, norm_options(self.settings)) if t else ""))
        h.addWidget(a)
        h.addWidget(d)
        h.addWidget(self.lex_test, 1)
        v.addLayout(h)
        v.addWidget(self.lex_out)
        return w

    def _tab_log(self):
        w = QWidget()
        v = QVBoxLayout(w)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 9))
        v.addWidget(self.log_view)
        h = QHBoxLayout()
        c = QPushButton("Copiar registro")
        c.clicked.connect(lambda: QApplication.clipboard().setText(self.log_view.toPlainText()))
        x = QPushButton("Limpiar")
        x.clicked.connect(self.log_view.clear)
        h.addStretch()
        h.addWidget(x)
        h.addWidget(c)
        v.addLayout(h)
        return w

    # ----------------------------------------------------------- settings
    def _load_settings_into_ui(self):
        self._loading = True
        s = self.settings
        self.cb_nofx.setChecked(s.no_effects)
        self.cb_player.setChecked(s.force_player_radio)
        self.cb_click.setChecked(s.mic_clicks)
        self.cb_breath.setChecked(s.breathing)
        self.sl_int.setValue(int(round(s.fx_intensity * 100)))
        self.sl_var.setValue(int(round(s.variation * 100)))
        self.cb_comb.setChecked(s.out_combined)
        self.cb_ind.setChecked(s.out_individual)
        self.cb_man.setChecked(s.out_manifest)
        self.sp_gap.setValue(s.gap_seconds)
        self.sl_q.setValue(int(round(s.ogg_quality * 100)))
        self.cb_niner.setChecked(s.niner)
        self.cmb_dec.setCurrentText(s.decimal_word)
        self.out_edit.setText(s.last_output)
        self._fill_lexicon()
        self._loading = False

    def _fx_changed(self, *_):
        if self._loading:
            return
        s = self.settings
        s.no_effects = self.cb_nofx.isChecked()
        s.force_player_radio = self.cb_player.isChecked()
        s.mic_clicks = self.cb_click.isChecked()
        s.breathing = self.cb_breath.isChecked()
        s.fx_intensity = self.sl_int.value() / 100
        s.variation = self.sl_var.value() / 100
        s.out_combined = self.cb_comb.isChecked()
        s.out_individual = self.cb_ind.isChecked()
        s.out_manifest = self.cb_man.isChecked()
        s.gap_seconds = round(self.sp_gap.value(), 3)
        s.ogg_quality = self.sl_q.value() / 100
        s.niner = self.cb_niner.isChecked()
        s.decimal_word = self.cmb_dec.currentText()
        self._save()
        self._refresh_line_effects()

    def _save(self):
        try:
            self.settings.save()
        except Exception as e:
            self.log("error", f"No se pudieron guardar los ajustes: {e}")

    def _save_paths(self):
        if self._loading:
            return
        self.settings.last_output = self.out_edit.text()
        self._save()

    # ------------------------------------------------------------ lexicon
    def _fill_lexicon(self):
        self.lex_tbl.blockSignals(True)
        self.lex_tbl.setRowCount(0)
        for k, val in sorted(self.settings.lexicon.items(), key=lambda kv: kv[0].lower()):
            r = self.lex_tbl.rowCount()
            self.lex_tbl.insertRow(r)
            self.lex_tbl.setItem(r, 0, QTableWidgetItem(k))
            self.lex_tbl.setItem(r, 1, QTableWidgetItem(val))
        self.lex_tbl.blockSignals(False)

    def _lex_changed(self, *_):
        lex = {}
        for r in range(self.lex_tbl.rowCount()):
            k = self.lex_tbl.item(r, 0)
            val = self.lex_tbl.item(r, 1)
            if k and k.text().strip():
                lex[k.text().strip()] = val.text().strip() if val else ""
        self.settings.lexicon = lex
        self._save()
        self._line_selected()

    def _lex_add(self):
        r = self.lex_tbl.rowCount()
        self.lex_tbl.insertRow(r)
        self.lex_tbl.setItem(r, 0, QTableWidgetItem(""))
        self.lex_tbl.setItem(r, 1, QTableWidgetItem(""))
        self.lex_tbl.editItem(self.lex_tbl.item(r, 0))

    def _lex_del(self):
        r = self.lex_tbl.currentRow()
        if r >= 0:
            self.lex_tbl.removeRow(r)
            self._lex_changed()

    # -------------------------------------------------------------- script
    def choose_script(self):
        start = str(Path(self.settings.last_script).parent) if self.settings.last_script else ""
        f, _ = QFileDialog.getOpenFileName(self, "Elegir guion", start, "Guion de texto (*.txt);;Todos (*.*)")
        if f:
            self.load_script(f)

    def choose_out(self):
        d = QFileDialog.getExistingDirectory(self, "Carpeta de salida", self.out_edit.text() or "")
        if d:
            self.out_edit.setText(d)

    def load_script(self, path: str):
        try:
            sc = parse_file(path)
        except Exception as e:
            self.log("error", f"No se pudo leer el guion: {e}")
            QMessageBox.critical(self, APP_NAME, f"No se pudo leer el guion:\n{e}")
            return
        self.script = sc
        self.overrides = {}
        self.script_edit.setText(path)
        self.settings.last_script = path
        if not self.out_edit.text():
            self.out_edit.setText(str(Path(path).parent / (Path(path).stem + "_audio")))
        new = assign_default_voices(self.settings, sc.speakers, self.avail)
        self._save()
        self.script_info.setText(f"{len(sc.lines)} líneas · {len(sc.speakers)} hablantes · {len(sc.threads)} hilos"
                                 + (f" · ⚠ {len(sc.warnings)} avisos (ver Registro)" if sc.warnings else ""))
        self.log("info", f"Guion cargado: {Path(path).name} ({len(sc.lines)} líneas)")
        for w in sc.warnings:
            self.log("warn", w)
        for s in new:
            self.log("info", f"Hablante '{s}': voz por defecto {self._voice_label(self.settings.speakers[s].voice)}")
        self._fill_lines()
        self._fill_voices()

    def _fill_lines(self):
        t = self.lines_tbl
        t.setRowCount(0)
        if not self.script:
            return
        t.setRowCount(len(self.script.lines))
        for r, l in enumerate(self.script.lines):
            num = l.number + (f" ({l.take})" if l.take and not l.number.endswith(l.take) else "")
            t.setItem(r, 0, QTableWidgetItem(num))
            t.setItem(r, 1, QTableWidgetItem(l.speaker))
            t.setItem(r, 2, QTableWidgetItem(l.tone_text))
            cmb = QComboBox()
            for k in PROFILE_KEYS:
                cmb.addItem(PROFILE_NAMES[k], k)
            cmb.setCurrentIndex(PROFILE_KEYS.index(self.overrides.get(l.index, "AUTO")))
            cmb.currentIndexChanged.connect(lambda i, idx=l.index, c=cmb: self._override(idx, c.currentData()))
            t.setCellWidget(r, 3, cmb)
            it = QTableWidgetItem(l.text)
            it.setToolTip(l.text)
            t.setItem(r, 4, it)
            t.setItem(r, 5, QTableWidgetItem(l.thread_title))
        self._refresh_line_effects()

    def _refresh_line_effects(self):
        if not self.script:
            return
        for r, l in enumerate(self.script.lines):
            cmb = self.lines_tbl.cellWidget(r, 3)
            if cmb is None:
                continue
            auto = resolve_profile(l, self.settings, "")
            cmb.setItemText(0, f"Auto · {PROFILE_NAMES.get(auto, auto)}")

    def _override(self, idx, key):
        if key == "AUTO":
            self.overrides.pop(idx, None)
        else:
            self.overrides[idx] = key

    def _current_line(self) -> ScriptLine | None:
        if not self.script:
            return None
        r = self.lines_tbl.currentRow()
        if r < 0 or r >= len(self.script.lines):
            return None
        return self.script.lines[r]

    def _line_selected(self):
        l = self._current_line()
        if l is None:
            return
        sp = normalize(l.text, norm_options(self.settings))
        self.spoken_lbl.setText(f"Se locuta: «{sp}»")

    # -------------------------------------------------------------- voices
    def _voice_label(self, vid):
        v = voice_by_id(vid)
        return v.label if v else vid

    def _fill_voices(self):
        t = self.voice_tbl
        t.setRowCount(0)
        names = list(self.script.speakers) if self.script else []
        names += [n for n in self.extra_speakers if n not in names]
        if "PLAYER" not in names:
            names.insert(0, "PLAYER")
        t.setRowCount(len(names))
        for r, name in enumerate(names):
            sp = self.settings.speakers.setdefault(name, SpeakerSettings(voice=PLAYER_VOICE if name == "PLAYER" else ""))
            t.setItem(r, 0, QTableWidgetItem(name))
            t.setItem(r, 1, QTableWidgetItem(ROLE_LABELS.get(role_of(name), "")))
            for c in (0, 1):
                t.item(r, c).setFlags(Qt.ItemIsEnabled)
            cmb = QComboBox()
            cmb.setMinimumWidth(280)
            for v in self.catalog:
                cmb.addItem(v.label, v.id)
                cmb.setItemData(cmb.count() - 1, f"Licencia: {v.license}" + (f" · calidad {v.quality}" if v.quality else ""),
                                Qt.ToolTipRole)
            i = cmb.findData(sp.voice)
            cmb.setCurrentIndex(max(0, i))
            cmb.currentIndexChanged.connect(lambda _, n=name, c=cmb: self._set_sp(n, "voice", c.currentData()))
            t.setCellWidget(r, 2, cmb)
            for col, field, lo, hi, step, val in ((3, "speed", 0.6, 1.5, 0.05, sp.speed),
                                                  (4, "pitch", -6, 6, 0.5, sp.pitch),
                                                  (5, "volume", 0.2, 1.5, 0.05, sp.volume)):
                s = QDoubleSpinBox()
                s.setRange(lo, hi)
                s.setSingleStep(step)
                s.setDecimals(2)
                s.setValue(val)
                s.valueChanged.connect(lambda x, n=name, f=field: self._set_sp(n, f, float(x)))
                t.setCellWidget(r, col, s)
            pc = QComboBox()
            for k in PROFILE_KEYS:
                pc.addItem(PROFILE_NAMES[k], k)
            pc.setCurrentIndex(PROFILE_KEYS.index(sp.profile if sp.profile in PROFILE_KEYS else "AUTO"))
            pc.currentIndexChanged.connect(lambda _, n=name, c=pc: self._set_sp(n, "profile", c.currentData()))
            t.setCellWidget(r, 6, pc)
            b = QPushButton("▶ Probar")
            b.clicked.connect(lambda _, n=name: self.preview_speaker(n))
            t.setCellWidget(r, 7, b)
            if name == "PLAYER":
                t.item(r, 0).setToolTip("Voz fija del jugador")

    def _set_sp(self, name, field, value):
        sp = self.settings.speakers.setdefault(name, SpeakerSettings())
        setattr(sp, field, value)
        self._save()
        if field == "profile":
            self._refresh_line_effects()

    def add_speaker(self):
        name, ok = QInputDialog.getText(self, "Añadir hablante", "Nombre del hablante (como en el guion):")
        if ok and name.strip():
            name = " ".join(name.upper().split())
            assign_default_voices(self.settings, [name], self.avail)
            self.extra_speakers.append(name)
            self._save()
            self._fill_voices()

    def reset_voices(self):
        if QMessageBox.question(self, APP_NAME, "¿Restablecer las voces de todos los hablantes a los valores por "
                                "defecto? (PLAYER conserva su voz fija)") != QMessageBox.Yes:
            return
        self.settings.speakers = {"PLAYER": SpeakerSettings(voice=PLAYER_VOICE)}
        if self.script:
            assign_default_voices(self.settings, self.script.speakers, self.avail)
        self._save()
        self._fill_voices()
        self._refresh_line_effects()

    # ---------------------------------------------------------- background
    def _run(self, fn, on_done, busy_text):
        if self.thread is not None:
            return
        self.thread = QThread()
        self.worker = Worker(fn)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.log.connect(self.log)
        # Los callbacks se guardan y se llaman desde un método de la ventana: así Qt los ejecuta en el
        # hilo de la interfaz (una función suelta conectada a la señal se ejecutaría en el hilo de trabajo).
        self._pending_done = on_done
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self._set_busy(True, busy_text)
        self.thread.start()

    def _on_done(self, res):
        cb = self._pending_done
        self._pending_done = None
        self._cleanup()
        if cb:
            cb(res)

    def _cleanup(self, *_):
        if self.thread:
            self.thread.quit()
            self.thread.wait()
        self.thread = None
        self.worker = None
        self._set_busy(False)

    def _set_busy(self, busy, text=""):
        self.gen_btn.setEnabled(not busy)
        self.prev_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        for r in range(self.voice_tbl.rowCount()):
            w = self.voice_tbl.cellWidget(r, 7)
            if w:
                w.setEnabled(not busy)
        if text:
            self.status.setText(text)

    def _on_progress(self, i, n, msg):
        self.pbar.setMaximum(max(1, n))
        self.pbar.setValue(i)
        self.status.setText(msg)

    def _on_failed(self, msg):
        self._pending_done = None
        self._cleanup()
        first = msg.splitlines()[0] if msg else "Error"
        self.log("error", msg)
        self.status.setText("Error: " + first)
        QMessageBox.critical(self, APP_NAME, f"Se produjo un error:\n{first}\n\nDetalles en la pestaña Registro.")

    def _warmup(self):
        if not self.catalog or self.thread is not None:
            return

        def job(w):
            t0 = time.time()
            self.tts.synthesize("Radio check.", PLAYER_VOICE, 1.0)
            return time.time() - t0
        self._run(job, lambda t: (self.status.setText("Motor de voz listo"),
                                  self.log("info", f"Motor de voz cargado en {t:.1f} s")), "Cargando motor de voz…")

    def cancel(self):
        if self.worker:
            self.worker.cancelled = True
            self.status.setText("Cancelando…")

    # -------------------------------------------------------------- actions
    def preview(self):
        l = self._current_line()
        if l is None:
            if self.script and self.script.lines:
                self.lines_tbl.selectRow(0)
                l = self._current_line()
            else:
                QMessageBox.information(self, APP_NAME, "Carga un guion y selecciona una línea.")
                return
        self._preview(l, self.overrides.get(l.index, ""))

    def preview_speaker(self, name):
        line = None
        if self.script:
            line = next((l for l in self.script.lines if l.speaker == name), None)
        if line is None:
            line = ScriptLine(0, 0, name, "000", "", [], "", None,
                              "Radio check, how do you read? Angels two zero, contact one four three decimal two.")
        self._preview(line, "")

    def _preview(self, line: ScriptLine, override: str):
        stop_audio()
        path = Path(tempfile.gettempdir()) / f"dcsradio_preview_{os.getpid()}.wav"

        def job(w):
            w.progress.emit(0, 1, f"Generando vista previa: {line.speaker} {line.number}…")
            r = preview_line(self.tts, line, self.settings, path, override)
            return r

        def done(r):
            self.pbar.setValue(self.pbar.maximum())
            self.status.setText(f"Vista previa: {line.speaker} {line.number} · {len(r.audio) / 44100:.1f} s · "
                                f"{PROFILE_NAMES.get(r.profile, r.profile)}")
            self.spoken_lbl.setText(f"Se locuta: «{r.spoken}»")
            if not play_wav(str(path)):
                self.log("warn", f"No hay reproductor de audio disponible. Vista previa guardada en {path}")
        self._run(job, done, "Generando vista previa…")

    def generate(self):
        if not self.script or not self.script.lines:
            QMessageBox.warning(self, APP_NAME, "Primero elige un guion con líneas válidas.")
            return
        out = self.out_edit.text().strip()
        if not out:
            QMessageBox.warning(self, APP_NAME, "Elige una carpeta de salida.")
            return
        if not (self.settings.out_combined or self.settings.out_individual or self.settings.out_manifest):
            QMessageBox.warning(self, APP_NAME, "Activa al menos un tipo de archivo de salida.")
            return
        outp = Path(out)
        if (outp / "lineas").exists() and any((outp / "lineas").glob("*.ogg")):
            if QMessageBox.question(self, APP_NAME, "La carpeta de salida ya contiene audios de una generación "
                                    "anterior. ¿Borrar los .ogg antiguos de «lineas» y generar de nuevo?") != QMessageBox.Yes:
                return
            for f in (outp / "lineas").glob("*.ogg"):
                try:
                    f.unlink()
                except Exception as e:
                    self.log("warn", f"No se pudo borrar {f.name}: {e}")
        script = self.script
        settings = self.settings
        overrides = dict(self.overrides)
        t0 = time.time()
        self.tabs.setCurrentIndex(4)

        def job(w):
            return generate_all(script, settings, out, tts=self.tts,
                                progress=lambda i, n, m: w.progress.emit(i, n, m),
                                log=lambda lvl, m: w.log.emit(lvl, m),
                                cancel=lambda: w.cancelled, overrides=overrides)

        def done(res):
            if res.get("cancelled"):
                self.status.setText("Cancelado")
                return
            dt = time.time() - t0
            msg = f"Terminado: {res['lines']} líneas en {dt:.0f} s" + (f" · {res['errors']} errores" if res["errors"] else "")
            self.status.setText(msg)
            self.log("ok", msg + f" → {res['out_dir']}")
            self._save()
            QMessageBox.information(self, APP_NAME, msg + f"\n\nCarpeta: {res['out_dir']}")
        self.log("info", f"Generando {len(script.lines)} líneas en {out} …")
        self._run(job, done, "Generando…")

    def open_out(self):
        p = self.out_edit.text().strip()
        if not p or not Path(p).exists():
            return
        if sys.platform == "win32":
            os.startfile(p)  # noqa
        else:
            subprocess.Popen(["xdg-open", p])

    # ------------------------------------------------------------------ log
    def log(self, level: str, msg: str):
        colors = {"error": "#ff6b6b", "warn": "#f0c05a", "ok": ACCENT, "info": "#9aa5b8"}
        tag = {"error": "ERROR", "warn": "AVISO", "ok": "OK", "info": "INFO"}.get(level, level.upper())
        ts = time.strftime("%H:%M:%S")
        safe = msg.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        self.log_view.appendHtml(f'<span style="color:#5c6677">{ts}</span> '
                                 f'<b style="color:{colors.get(level, "#ccc")}">{tag}</b> '
                                 f'<span style="color:#d5dbe5">{safe}</span>')
        if level == "error":
            self.tabs.setTabText(4, "Registro ⚠")

    def closeEvent(self, e):
        if self.worker:
            self.worker.cancelled = True
        if self.thread:
            self.thread.quit()
            self.thread.wait(3000)
        self._save()
        stop_audio()
        super().closeEvent(e)


def main():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DCSRadioVoices")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    w = MainWindow()
    w.show()
    return app.exec()


def selftest(out_dir: str) -> int:
    """Autoprueba sin intervención: abre la ventana, carga el ejemplo, previsualiza, genera 6 líneas y captura."""
    from .engines import resource_dir
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    logf = open(out / "selftest.log", "w", encoding="utf-8")

    def say(m):
        logf.write(m + "\n")
        logf.flush()
    errors: list[str] = []
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    QMessageBox.warning = staticmethod(lambda *a, **k: errors.append(str(a[2:])) or QMessageBox.Ok)
    QMessageBox.critical = staticmethod(lambda *a, **k: errors.append(str(a[2:])) or QMessageBox.Ok)
    global play_wav
    play_wav = lambda p: True  # noqa: E731
    try:
        app = QApplication(sys.argv[:1])
        app.setStyle("Fusion")
        app.setStyleSheet(STYLE)
        w = MainWindow()
        w.resize(1280, 820)
        w.show()

        def wait_idle(timeout=900):
            t0 = time.time()
            while time.time() - t0 < timeout:
                app.processEvents()
                if w.thread is None:
                    return True
                time.sleep(0.02)
            return False
        t0 = time.time()
        while time.time() - t0 < 1.0:
            app.processEvents()
            time.sleep(0.02)
        wait_idle()
        say(f"voces: {len(w.catalog)}")
        sample = resource_dir() / "samples" / "Levante_M02_EJEMPLO_guion_voces.txt"
        w.load_script(str(sample))
        say(f"guion: {w.script_info.text()}")
        w.script.lines = w.script.lines[:6]
        w._fill_lines()
        w.out_edit.setText(str(out / "salida"))
        for i, name in enumerate(["lineas", "voces", "efectos", "pronunciacion"]):
            w.tabs.setCurrentIndex(i)
            app.processEvents()
            w.grab().save(str(out / f"captura_{i}_{name}.png"))
        w.tabs.setCurrentIndex(0)
        w.lines_tbl.selectRow(1)
        w.preview()
        wait_idle()
        say("vista previa: " + w.status.text())
        w.generate()
        wait_idle(1800)
        app.processEvents()
        w.grab().save(str(out / "captura_5_registro.png"))
        say("estado: " + w.status.text())
        say(w.log_view.toPlainText())
        n = len(list((out / "salida" / "lineas").glob("*.ogg")))
        say(f"ogg generados: {n}")
        if n != 6:
            errors.append(f"se esperaban 6 ogg y hay {n}")
        if "ERROR" in w.log_view.toPlainText():
            errors.append("hay errores en el registro")
        w.close()
    except Exception:
        errors.append(traceback.format_exc())
    for e in errors:
        say("FALLO: " + e)
    say("RESULTADO: " + ("OK" if not errors else "FALLO"))
    logf.close()
    return 0 if not errors else 1
