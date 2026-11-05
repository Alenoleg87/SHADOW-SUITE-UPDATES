
"""
SHADOW CHECKER PRO
Firefox Proxy Diagnostic + Verified Proxy Pool
"""

import sys
import os
import threading
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

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame,
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFileDialog, QLineEdit, QSpinBox, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPlainTextEdit, QMessageBox, QInputDialog,
)

from playwright.sync_api import sync_playwright
import openpyxl

from integrations.proxy_runtime import ProxyRuntime
from integrations.proxy_pool import ProxyPool
from integrations.proxy_only_gui import ProxyOnlyWindow


TARGET_URL = "https://mail.google.com/"
# A secondary, browser-side IP check, never a substitute for proxy verification.
BROWSER_IP_URL = "https://api64.ipify.org?format=json"
SESSION_HOLD_SECONDS = 90


def browser_observed_exit_ip(context):
    """Read the public IP through a real Firefox tab in the SAME browser context.

    The APIRequestContext is intentionally NOT used: this check must go via
    the running browser network route, not an unrelated HTTP client.
    Failed/blocked lookups return an explicit reason rather than a guessed IP.
    """
    probe = context.new_page()
    try:
        response = probe.goto(
            BROWSER_IP_URL,
            wait_until="domcontentloaded",
            timeout=12000,
        )
        if response is None or not response.ok:
            return None, "IP endpoint returned no successful response"
        payload = json.loads(response.body().decode("utf-8"))
        value = payload.get("ip") if isinstance(payload, dict) else None
        if not isinstance(value, str):
            return None, "IP endpoint returned invalid JSON"
        observed = str(ipaddress.ip_address(value.strip()))
        return observed, None
    except Exception as exc:
        return None, f"Browser IP observation failed: {type(exc).__name__}"
    finally:
        try:
            probe.close()
        except Exception:
            pass


def set_firefox_window_visibility(title_marker, visible):
    """Windows-only control of OUR tagged Firefox window; never a global Firefox toggle."""
    if sys.platform != "win32":
        return False, "Native browser Hide/Show is supported on Windows only"
    if not title_marker:
        return False, "Browser window identifier is missing"
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_t = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows.argtypes = (callback_t, wintypes.LPARAM)
        user32.EnumWindows.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.ShowWindow.restype = wintypes.BOOL

        matches = []

        @callback_t
        def window_callback(hwnd, _lparam):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                title = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, title, length + 1)
                if title_marker in title.value:
                    matches.append(hwnd)
            return True

        if not user32.EnumWindows(window_callback, 0):
            return False, "Windows could not enumerate browser windows"
        if not matches:
            return False, "Tagged browser window not found yet"
        # SW_SHOW=5; SW_HIDE=0. ShowWindow's return value describes prior state.
        for hwnd in matches:
            user32.ShowWindow(hwnd, 5 if visible else 0)
        return True, f"Updated {len(matches)} tagged browser window(s)"
    except Exception as exc:
        return False, f"Window control unavailable: {type(exc).__name__}"



STYLE = """
/* SHADOW CHECKER PRO — compact Publisher-inspired grey/blue/green theme */
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
/* Keep existing object names and signals; only their visual palette changes. */
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
    background: #4B5860;
    color: #E7EFF2;
    border: 1px solid #72818B;
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
        self.log_signal.emit(
            "[RUNTIME] Starting HTTPS verification..."
        )

        self.runtime.scan(self.lines)

        self.log_signal.emit(
            "[RUNTIME] Verification finished."
        )


class FirefoxWorker(QThread):
    status_signal = Signal(int, str, str)
    result_signal = Signal(str, str, str, str)
    log_signal = Signal(str)

    def __init__(
        self,
        browser_id,
        proxy,
        protocol,
        expected_ip,
        lease=None,
        direct=False,
    ):
        super().__init__()

        self.browser_id = browser_id
        self.proxy = proxy
        self.protocol = protocol
        self.expected_ip = expected_ip
        self.lease = lease
        self.direct = direct

        # Unique marker allows Win32 visibility controls to target THIS session.
        self.window_title_marker = f"SHADOW-PRO-{os.getpid()}-{browser_id}-{uuid.uuid4().hex[:8]}"
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def run(self):
        """Navigate visibly, report connection status, and hold for 90 seconds.

        Does not enter identifiers/passwords or attempt Google authentication.
        """
        browser = None
        label = f"Browser #{self.browser_id}"
        proxy_label = "DIRECT" if self.direct else self.proxy.label
        try:
            with sync_playwright() as playwright:
                self.status_signal.emit(self.browser_id, "CONNECTING", proxy_label)
                options = {"headless": False}
                if not self.direct:
                    if self.proxy is None or not self.protocol or self.lease is None:
                        raise RuntimeError("Proxy requires verified lease")
                    options["proxy"] = self.proxy.playwright_config(self.protocol)

                browser = playwright.firefox.launch(**options)
                context = browser.new_context(ignore_https_errors=False)
                page = context.new_page()
                try:
                    page.goto("about:blank", timeout=5000)
                except Exception:
                    pass
                try:
                    page.evaluate("marker => {document.title = marker}", self.window_title_marker)
                except Exception:
                    pass

                # Start hold time at the beginning of navigation, and keep the
                # window alive after navigation errors too.
                self.status_signal.emit(self.browser_id, "OPENING GMAIL", proxy_label)
                status = "NOT_OPENED"
                reason = ""
                try:
                    response = page.goto(
                        TARGET_URL,
                        wait_until="domcontentloaded",
                        timeout=20000,
                    )
                    if response is None:
                        status = "NO_RESPONSE"
                    elif response.ok:
                        status = "OPENED"
                    else:
                        status = f"HTTP_{response.status}"
                except Exception as exc:
                    status = "NAVIGATION_ERROR"
                    reason = type(exc).__name__

                # Marker tagging supports Hide/Show on Windows.
                try:
                    page.evaluate("marker => {document.title = marker}", self.window_title_marker)
                except Exception:
                    pass
                self.status_signal.emit(self.browser_id, status, proxy_label)
                self.result_signal.emit(label, "Gmail", status, reason or "Navigation finished")
                self.log_signal.emit(f"[{label}] Gmail: {status} | {reason or 'No exception'}")
                deadline = time.monotonic() + SESSION_HOLD_SECONDS

                while not self.stop_event.is_set() and time.monotonic() < deadline:
                    if not browser.is_connected() or page.is_closed():
                        break
                    self.msleep(250)
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
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass


class CheckerWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle(
            "SHADOW CHECKER PRO — Firefox Proxy Pool"
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

        self.browser_status = []
        self.browser_show_buttons = []
        self.last_export_path = None
        self._export_session_token = None
        self._export_path = None
        self._browser_buttons = {}
        self._browser_hidden = {}

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
        self.log("Proxy Runtime ready. Gmail navigation only; no account login.")

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
                edit.setPlaceholderText("Reference only — no account login is performed")
                edit.setToolTip("Source File is reserved for a separate authorized integration; no account login is performed.")
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

            # Diagnostic Logs is already available in the top toolbar.
            # Avoid a duplicate button above the Logs pane.
            clear = QPushButton("♧  Clear")
            header.addWidget(clear)
            column.addLayout(header)

            if is_results:
                self.table = QTableWidget(0, 4)

                self.table.setHorizontalHeaderLabels([
                    "Session",
                    "Website",
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
        self._browser_hidden = {}

        for index in range(count):
            inner = QVBoxLayout()
            inner.setContentsMargins(6, 5, 6, 5)
            inner.setSpacing(3)

            inner.addWidget(
                QLabel(
                    f"◉  Browser #{index + 1}",
                    objectName="section",
                )
            )

            toggles = QHBoxLayout()
            toggles.setSpacing(4)

            status = QLabel(
                "Status: WAITING"
            )

            hide_btn = QPushButton("Hide")
            show_btn = QPushButton("Show")

            hide_btn.setObjectName("show")
            show_btn.setObjectName("show")

            hide_btn.setCheckable(True)
            show_btn.setCheckable(True)

            show_btn.setChecked(True)

            # The checked state is changed only if a native window operation
            # succeeds; no fake visual-only Hide/Show toggle.
            browser_id = index + 1
            hide_btn.clicked.connect(
                lambda _checked=False, bid=browser_id: self.toggle_browser_window(bid, False)
            )
            show_btn.clicked.connect(
                lambda _checked=False, bid=browser_id: self.toggle_browser_window(bid, True)
            )
            self._browser_buttons[browser_id] = (hide_btn, show_btn)

            toggles.addWidget(hide_btn)
            toggles.addWidget(show_btn)
            inner.addLayout(toggles)

            location = QLabel(
                "⌖  Proxy: Waiting"
            )

            location.setWordWrap(True)
            status.setWordWrap(True)
            inner.addWidget(location)
            inner.addWidget(status)

            card = self.panel(inner)
            card.setMinimumWidth(132)
            card.setMaximumWidth(260)

            self.browser_row.addWidget(card, index // 5, index % 5)

            self.browser_status.append(
                (location, status)
            )

            self.browser_show_buttons.append(
                show_btn
            )

    def toggle_browser_window(self, browser_id, visible):
        worker = next(
            (item for item in self.workers if item.browser_id == browser_id),
            None,
        )
        ok, reason = (
            set_firefox_window_visibility(worker.window_title_marker, visible)
            if worker is not None
            else (False, "Browser session is not running")
        )
        buttons = self._browser_buttons.get(browser_id)
        if buttons:
            hide_btn, show_btn = buttons
            old_hidden = self._browser_hidden.get(browser_id, False)
            if ok:
                self._browser_hidden[browser_id] = not visible
            new_hidden = self._browser_hidden.get(browser_id, old_hidden)
            hide_btn.setChecked(new_hidden)
            show_btn.setChecked(not new_hidden)
        self.log(f"[WINDOW #{browser_id}] {'SHOW' if visible else 'HIDE'}: {reason}")

    def browse_source(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose source file",
            "",
            "Text files (*.txt *.csv);;All files (*)",
        )

        if path:
            self.source_path.setText(path)
            self.log(
                f"Source selected for reference only (not processed): {Path(path).name}"
            )

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

        self.loaded_label.setText(
            f"Loaded: {len(lines)}"
        )

        self.log(
            f"Loaded {len(lines)} proxy entries."
        )

        return lines

    def start(self):
        if (
            self.runtime_thread
            and self.runtime_thread.isRunning()
        ):
            return

        if any(
            worker.isRunning()
            for worker in self.workers
        ):
            return

        proxy_path_text = self.proxy_path.text().strip()
        self.direct_mode = not bool(proxy_path_text)
        if self.direct_mode:
            answer = QMessageBox.question(
                self,
                "Continue without proxy?",
                "Are you sure you want to continue without proxy?\n\n"
                "Firefox will use this computer's normal network connection. "
                "Your public IP may be visible to the destination website.",
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
        self._completed_browser_ids = set()
        if self.proxy_monitor is not None:
            self.proxy_monitor.reset(len(lines))

        self.update_counters()

        self.start_btn.setEnabled(False)

        for index in range(
            len(self.browser_status)
        ):
            self.update_browser_status(
                index + 1,
                "WAITING",
                "No proxy assigned",
            )

        if self.direct_mode:
            self.runtime_scan_done = True
            self.progress_label.setText("Runtime: SKIPPED (DIRECT)")
            self.type_label.setText("Protocol: DIRECT")
            self.log("[DIRECT] User confirmed normal network connection.")
            self.start_browser_sessions()
            return

        self.type_label.setText("Protocol: AUTO")
        self.runtime_thread = RuntimeThread(lines, self.proxy_pool)

        self.runtime_thread.result_signal.connect(
            self.runtime_result
        )

        self.runtime_thread.progress_signal.connect(
            self.runtime_progress
        )

        self.runtime_thread.log_signal.connect(
            self.log
        )

        self.runtime_thread.finished.connect(
            self.runtime_finished
        )

        self.runtime_thread.start()

        self.log(
            "[CHECKER] Runtime started. "
            "Browsers remain in WAITING."
        )

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
            self.log(
                f"[GOOD] {proxy.label} | {result['protocol']} | "
                f"Exit IP: {result['exit_ip']}"
            )
        else:
            if status in ("BAD", "AUTH_FAILED"):
                self.bad_count += 1

            label = (
                proxy.label
                if proxy
                else f"Line {result.get('line', '?')}"
            )

            self.log(
                f"[{status}] {label} | "
                f"{result.get('reason', 'Unknown')}"
            )

        self.update_counters()

    def runtime_progress(self, completed, total):
        self.runtime_last_progress = (completed, total)
        self.diagnostic("proxy_runtime", "progress", completed=completed, total=total)
        if self.proxy_monitor is not None:
            self.proxy_monitor.set_progress(completed, total)
        self.progress_label.setText(
            f"Runtime: {completed}/{total}"
        )

    def runtime_finished(self):
        self.runtime_scan_done = True
        self.diagnostic("proxy_runtime", "scan_finished", good=self.good_count,
                        bad=self.bad_count, checked=self.checked_count)
        if self.proxy_monitor is not None:
            self.proxy_monitor.mark_finished()
        self.log(
            "[RUNTIME] Scan finished. "
            f"GOOD: {self.good_count} | "
            f"BAD: {self.bad_count}"
        )

        self.progress_label.setText(
            "Runtime: COMPLETE"
        )

        self.start_browser_sessions()
        if not self.workers:
            self.start_btn.setEnabled(True)
            self.threads.setEnabled(True)

    def start_browser_sessions(self):
        # One bounded diagnostic session per browser slot per scan.
        # A slot is not restarted automatically after it finishes.
        if self.stopping:
            return
        capacity = self.threads.value()
        used_ids = {w.browser_id for w in self.workers}
        used_ids.update(getattr(self, "_completed_browser_ids", set()))
        for browser_id in range(1, capacity + 1):
            if browser_id in used_ids:
                continue
            if self.direct_mode:
                lease = None
                worker = FirefoxWorker(browser_id, None, "DIRECT",
                                       "Not verified", direct=True)
            else:
                lease = self.proxy_pool.acquire(f"browser-{browser_id}", timeout=0)
                if lease is None:
                    continue
                worker = FirefoxWorker(browser_id, lease.proxy, lease.protocol,
                                       lease.exit_ip, lease=lease)
            worker.status_signal.connect(self.update_browser_status)
            worker.result_signal.connect(self.handle_result)
            worker.log_signal.connect(self.log)
            worker.finished.connect(lambda w=worker: self.worker_finished(w))
            self.workers.append(worker)
            used_ids.add(browser_id)
            if lease is None:
                self.diagnostic("firefox", "session_assigned", browser=browser_id,
                                network_mode="DIRECT", proxy="none",
                                protocol="DIRECT", expected_exit_ip="Not verified")
            else:
                self.diagnostic("firefox", "session_assigned", browser=browser_id,
                                network_mode="VERIFIED_PROXY", proxy=lease.proxy.label,
                                protocol=lease.protocol, expected_exit_ip=lease.exit_ip)
            worker.start()
        self.update_counters()

    def update_browser_status(
        self,
        browser_id,
        status,
        proxy_info,
    ):
        index = browser_id - 1

        if 0 <= index < len(self.browser_status):
            location, status_label = (
                self.browser_status[index]
            )

            location.setText(
                f"⌖ Proxy: {proxy_info[:28]}"
            )

            status_label.setText(
                f"Status: {status}"
            )

    def handle_result(
        self,
        session,
        website,
        status,
        detail,
    ):
        record = (
            session,
            website,
            status,
            detail,
        )

        self.results.append(record)
        self.diagnostic("firefox", "navigation_result", session=session,
                        website=website, status=status, detail=detail)

        row = self.table.rowCount()
        self.table.insertRow(row)

        for column, value in enumerate(record):
            self.table.setItem(
                row,
                column,
                QTableWidgetItem(str(value)),
            )

        self.refresh_stats()

        self.last_export_path = (
            self.export_to_file(self.results)
        )

    def update_counters(self):
        self.working_label.setText(
            f"Valid: {self.good_count}"
        )

        self.bad_label.setText(
            f"Invalid: {self.bad_count}"
        )

        self.pool_label.setText(
            ("Proxy Pool: BYPASSED (DIRECT)" if self.direct_mode
             else f"Proxy Pool: {self.proxy_pool.stats()['available']} READY")
        )

        self.refresh_stats()

    def refresh_stats(self):
        total = len(self.results)

        ok = sum(
            row[2] == "OPENED"
            for row in self.results
        )

        bad = sum(
            row[2].startswith("HTTP")
            or row[2] == "NO RESPONSE"
            for row in self.results
        )

        errors = sum(
            row[2] in ("ERROR", "NAVIGATION_ERROR")
            for row in self.results
        )

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
            self.stats[key].setText(
                f"{key}: {value}"
            )

    def worker_finished(self, worker):
        if not hasattr(self, "_completed_browser_ids"):
            self._completed_browser_ids = set()
        self._completed_browser_ids.add(worker.browser_id)
        if worker.lease is not None:
            self.proxy_pool.release(worker.lease)
        if worker in self.workers:
            self.workers.remove(worker)

        # After a lease is released, one previously waiting browser slot may
        # run. Each slot can run at most once per scan; never an endless loop.
        if not self.stopping:
            self.start_browser_sessions()

        if not self.workers and self.runtime_scan_done:
            self.start_btn.setEnabled(True)
            self.threads.setEnabled(True)
            self.log("[CHECKER] Firefox sessions finished.")
        self.update_counters()

    def export_to_file(self, data):
        try:
            if getattr(sys, "frozen", False):
                base = Path(
                    sys.executable
                ).resolve().parent
            else:
                base = Path(
                    __file__
                ).resolve().parent.parent

            directory = (
                base / "output" / "Shadow_Checker"
            )

            directory.mkdir(
                parents=True,
                exist_ok=True,
            )

            excel = (
                "Excel"
                in self.mode.currentText()
            )

            extension = (
                ".xlsx" if excel else ".txt"
            )

            # One stable file per run, not one colliding name per result/second.
            if self._export_path is None or self._export_path.suffix != extension:
                if not self._export_session_token:
                    self._export_session_token = (
                        datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                        + "_" + uuid.uuid4().hex[:8]
                    )
                self._export_path = directory / (
                    f"Results_{self._export_session_token}{extension}"
                )
            path = self._export_path

            headers = [
                "Session",
                "Website",
                "Status",
                "Details",
            ]

            # Write to a neighbor file before atomic replacement so an
            # interrupted export never leaves a truncated published result.
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
            self.log(
                f"[EXPORT ERROR] {exc}"
            )
            return None

    def stop(self):
        self.stopping = True
        if (
            self.runtime_thread
            and self.runtime_thread.isRunning()
        ):
            self.runtime_thread.stop()

        for worker in self.workers:
            worker.stop()

        self.log("[STOP] Stop requested.")
        self.diagnostic("checker", "stop_requested")

    def restart(self):
        self.stop()

        if (
            self.runtime_thread
            and self.runtime_thread.isRunning()
        ):
            self.log(
                "[SYSTEM] Wait for Runtime to stop."
            )
            return

        if any(
            worker.isRunning()
            for worker in self.workers
        ):
            self.log(
                "[SYSTEM] Wait for Firefox sessions."
            )
            return

        self.clear_results()

        self.log(
            "[SYSTEM] Ready for a new scan."
        )

    def clear_results(self):
        self.table.setRowCount(0)
        self.results = []

        self.refresh_stats()

        self.log("[UI] Results cleared.")

    def open_file(self):
        if (
            not self.last_export_path
            or not Path(
                self.last_export_path
            ).is_file()
        ):
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

        if (
            self.runtime_thread
            and self.runtime_thread.isRunning()
        ):
            self.runtime_thread.wait(10000)

        for worker in list(self.workers):
            if worker.isRunning():
                worker.wait(5000)

        still_running = (
            self.runtime_thread
            and self.runtime_thread.isRunning()
        ) or any(
            worker.isRunning()
            for worker in self.workers
        )

        if still_running:
            event.ignore()
            self.log(
                "[SYSTEM] Waiting for threads to finish."
            )
            return

        self.diagnostic("system", "normal_exit", events=self._diag_count)
        self._diagnostic_dir.cleanup()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = CheckerWindow()
    window.show()

    sys.exit(app.exec())
