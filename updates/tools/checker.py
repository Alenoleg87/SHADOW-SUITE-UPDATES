
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
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QLineEdit, QSpinBox, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPlainTextEdit, QMessageBox, QInputDialog,
)

from playwright.sync_api import sync_playwright
import openpyxl

from integrations.proxy_runtime import ProxyRuntime
from integrations.proxy_pool import ProxyPool
from integrations.proxy_only_gui import ProxyOnlyWindow


TARGET_URL = "https://www.whatismyip.com/"


STYLE = """
QMainWindow,QWidget {
    background:#FAF9F7;
    color:#252B32;
    font:12px 'Segoe UI';
}
QFrame#panel {
    background:#FFFFFF;
    border:1px solid #DDDDE0;
    border-radius:11px;
}
QLabel {background:transparent;}
QLabel#section {
    font-weight:750;
    font-size:13px;
}
QPushButton {
    background:#FFFEFC;
    border:1px solid #E4D9D0;
    border-radius:8px;
    padding:7px 12px;
    color:#333942;
}
QPushButton:hover {
    border-color:#FF8C47;
    background:#FFF3EA;
}
QPushButton#orange {
    background:#FF831F;
    color:white;
    border:1px solid #FF831F;
    font-weight:800;
    font-size:14px;
}
QPushButton#stop {
    color:#B42318;
    background:#FFF0EF;
    border:1px solid #EFA8A4;
    font-weight:700;
}
QPushButton#show {
    color:#333942;
    background:#FFFEFC;
    border:1px solid #E4D9D0;
    font-weight:650;
}
QPushButton#show:checked {
    color:#187D42;
    background:#EBF8EF;
    border:1px solid #8FCFA5;
    font-weight:700;
}
QPushButton#tofile {
    color:#187D42;
    background:#EAF8EE;
    border:1px solid #8FCFA5;
    font-weight:700;
}
QPushButton#explore {
    color:#896000;
    background:#FFF8DE;
    border:1px solid #EAD18A;
    font-weight:700;
}
QLineEdit,QComboBox,QSpinBox {
    background:#FFFFFF;
    border:1px solid #DED9D4;
    border-radius:7px;
    padding:7px;
    color:#30343A;
}
QTableWidget,QPlainTextEdit {
    background:#FFFEFD;
    border:1px solid #E7DFD9;
    border-radius:7px;
    gridline-color:#EEEAE6;
}
QHeaderView::section {
    background:#F8F5F2;
    border:0;
    border-bottom:1px solid #E7DFD9;
    padding:7px;
    font-weight:650;
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

        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def run(self):
        browser = None
        import time
        deadline = time.monotonic() + 90

        label = f"Browser #{self.browser_id}"
        proxy_label = "DIRECT (normal connection)" if self.direct else self.proxy.label

        try:
            with sync_playwright() as playwright:
                self.status_signal.emit(
                    self.browser_id,
                    "CONNECTING",
                    proxy_label,
                )

                launch_options = {"headless": False}
                if not self.direct:
                    if self.proxy is None or not self.protocol or self.lease is None:
                        raise RuntimeError("Proxy mode requires a verified lease")
                    launch_options["proxy"] = self.proxy.playwright_config(self.protocol)

                browser = playwright.firefox.launch(**launch_options)

                context = browser.new_context(
                    ignore_https_errors=False,
                )

                page = context.new_page()

                self.status_signal.emit(
                    self.browser_id,
                    "OPENING WEBSITE",
                    proxy_label,
                )

                response = page.goto(
                    TARGET_URL,
                    wait_until="domcontentloaded",
                    timeout=20000,
                )

                if response is None:
                    status = "NO RESPONSE"
                elif response.ok:
                    status = "OPENED"
                else:
                    status = f"HTTP {response.status}"

                self.status_signal.emit(
                    self.browser_id,
                    status,
                    proxy_label,
                )

                self.result_signal.emit(
                    label,
                    self.expected_ip,
                    status,
                    proxy_label,
                )

                self.log_signal.emit(
                    f"[{label}] {status} | "
                    f"Expected exit IP: {self.expected_ip}"
                )

                while not self.stop_event.is_set() and time.monotonic() < deadline:
                    if not browser.is_connected():
                        break

                    if page.is_closed():
                        break

                    self.msleep(350)

        except Exception as exc:
            message = str(exc)

            for secret in (
                getattr(self.proxy, "username", ""),
                getattr(self.proxy, "password", ""),
            ):
                if secret:
                    message = message.replace(
                        secret,
                        "***",
                    )

            self.status_signal.emit(
                self.browser_id,
                "ERROR",
                proxy_label,
            )

            self.result_signal.emit(
                label,
                self.expected_ip,
                "ERROR",
                proxy_label,
            )

            self.log_signal.emit(
                f"[{label}] "
                f"{type(exc).__name__}: "
                f"{message[:160]}"
            )

        finally:
            if browser:
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

        self.resize(1080, 720)
        self.setMinimumSize(940, 650)
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
        self.log("Proxy Runtime ready.")

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
        v.setContentsMargins(13, 12, 13, 12)
        v.setSpacing(8)

        toolbar = QHBoxLayout()

        for name, function in [
            ("■  Stop", self.stop),
            ("⟳  Restart", self.restart),
            ("▤  To File", self.open_file),
            ("◎  Proxy Runtime", self.open_proxy_monitor),
            ("▤  Diagnostic Logs", self.show_diagnostics),
        ]:
            button = QPushButton(name)
            button.setMinimumWidth(125)

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

            label = QLabel(title)
            label.setFixedWidth(150)
            row.addWidget(label)

            edit = QLineEdit()
            edit.setPlaceholderText(
                "Select a local text file..."
            )

            setattr(self, attribute, edit)
            row.addWidget(edit, 1)

            button = QPushButton("▱  Explore")
            button.setObjectName("explore")
            button.clicked.connect(function)
            row.addWidget(button)

            v.addLayout(row)

        settings = QHBoxLayout()

        settings.addWidget(
            QLabel("Proxy Protocol")
        )

        self.proxy_type = QComboBox()
        self.proxy_type.addItems([
            "AUTO DETECT",
        ])

        settings.addWidget(self.proxy_type)
        settings.addSpacing(16)

        settings.addWidget(QLabel("Threads"))

        self.threads = QSpinBox()
        self.threads.setRange(1, 10)
        self.threads.setValue(3)

        self.threads.valueChanged.connect(
            self.browser_cards
        )

        settings.addWidget(self.threads)
        settings.addSpacing(16)

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
        self.start_btn.setMinimumWidth(160)
        self.start_btn.clicked.connect(self.start)

        settings.addWidget(self.start_btn)
        v.addLayout(settings)

        counter = QHBoxLayout()

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
        browser_box.setContentsMargins(9, 8, 9, 8)
        browser_box.setSpacing(5)

        browser_box.addWidget(
            QLabel(
                "◎   Live Browsers",
                objectName="section",
            )
        )

        self.browser_row = QHBoxLayout()
        browser_box.addLayout(self.browser_row)

        v.addWidget(self.panel(browser_box))
        self.browser_cards(self.threads.value())

        stats_row = QHBoxLayout()
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

        for title, is_results in [
            ("▤   Results", True),
            ("▤   Logs", False),
        ]:
            column = QVBoxLayout()
            column.setContentsMargins(8, 7, 8, 8)

            header = QHBoxLayout()
            header.addWidget(
                QLabel(
                    title,
                    objectName="section",
                )
            )
            header.addStretch()

            if not is_results:
                diag_button = QPushButton("▤ Diagnostic Logs")
                diag_button.clicked.connect(self.show_diagnostics)
                header.addWidget(diag_button)
            clear = QPushButton("♧  Clear")
            header.addWidget(clear)
            column.addLayout(header)

            if is_results:
                self.table = QTableWidget(0, 4)

                self.table.setHorizontalHeaderLabels([
                    "Session",
                    "Exit IP",
                    "Status",
                    "Proxy",
                ])

                self.table.verticalHeader().setVisible(
                    True
                )

                self.table.verticalHeader().setDefaultSectionSize(
                    25
                )

                self.table.horizontalHeader().setSectionResizeMode(
                    QHeaderView.ResizeMode.Stretch
                )

                self.table.setEditTriggers(
                    QTableWidget.EditTrigger.NoEditTriggers
                )

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

        for index in range(count):
            inner = QVBoxLayout()
            inner.setContentsMargins(8, 8, 8, 8)
            inner.setSpacing(5)

            inner.addWidget(
                QLabel(
                    f"◉  Browser #{index + 1}",
                    objectName="section",
                )
            )

            toggles = QHBoxLayout()

            status = QLabel(
                "Status: WAITING"
            )

            hide_btn = QPushButton("Hide")
            show_btn = QPushButton("Show")

            hide_btn.setObjectName("show")
            show_btn.setObjectName("show")

            hide_btn.setCheckable(True)
            show_btn.setCheckable(True)

            hide_btn.setChecked(True)

            def make_toggle(h_btn, s_btn):
                h_btn.clicked.connect(
                    lambda checked: (
                        s_btn.setChecked(False)
                        if checked
                        else h_btn.setChecked(True)
                    )
                )

                s_btn.clicked.connect(
                    lambda checked: (
                        h_btn.setChecked(False)
                        if checked
                        else s_btn.setChecked(True)
                    )
                )

            make_toggle(hide_btn, show_btn)

            toggles.addWidget(hide_btn)
            toggles.addWidget(show_btn)
            inner.addLayout(toggles)

            location = QLabel(
                "⌖  Proxy: Waiting"
            )

            inner.addWidget(location)
            inner.addWidget(status)

            card = self.panel(inner)
            card.setMinimumWidth(180)

            self.browser_row.addWidget(card, 1)

            self.browser_status.append(
                (location, status)
            )

            self.browser_show_buttons.append(
                show_btn
            )

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
                f"Source selected: {Path(path).name}"
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
            self.diagnostic("firefox", "session_assigned", browser=browser_id,
                            proxy=lease.proxy.label, protocol=lease.protocol,
                            expected_exit_ip=lease.exit_ip)
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
        exit_ip,
        status,
        proxy_label,
    ):
        record = (
            session,
            exit_ip,
            status,
            proxy_label,
        )

        self.results.append(record)
        self.diagnostic("firefox", "navigation_result", session=session,
                        exit_ip=exit_ip, status=status, proxy=proxy_label)

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
            row[2] == "ERROR"
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

        if not self.workers and self.runtime_scan_done:
            self.start_btn.setEnabled(True)
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

            path = directory / (
                f"Results_"
                f"{datetime.now():%Y%m%d_%H%M%S}"
                f"{extension}"
            )

            headers = [
                "Session",
                "Exit IP",
                "Status",
                "Proxy",
            ]

            if excel:
                workbook = openpyxl.Workbook()
                sheet = workbook.active
                sheet.title = "Results"
                sheet.append(headers)

                for row in data:
                    sheet.append(row)

                workbook.save(path)

            else:
                with open(
                    path,
                    "w",
                    encoding="utf-8",
                ) as file:
                    file.write(
                        "\t".join(headers) + "\n"
                    )

                    for row in data:
                        file.write(
                            "\t".join(
                                str(value)
                                for value in row
                            )
                            + "\n"
                        )

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
