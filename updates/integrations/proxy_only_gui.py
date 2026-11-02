
"""Read-only live monitor for the existing CHECKER ProxyRuntime.
No independent verification, network requests, or proxy-file loading.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView,
)


class ProxyOnlyWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SHADOW SUITE — Proxy Runtime Monitor")
        self.resize(1080, 610)
        self.setMinimumSize(760, 420)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        self.setStyleSheet("""
            QMainWindow, QWidget {
                background: #FAF9F7;
                color: #252B32;
                font: 12px 'Segoe UI';
            }
            QLabel#title {
                font-size: 18px;
                font-weight: 750;
            }
            QTableWidget {
                background: white;
                border: 1px solid #DDDDE0;
                gridline-color: #EEEAE6;
            }
            QHeaderView::section {
                background: #F8F5F2;
                padding: 7px;
                font-weight: 650;
            }
            QPushButton {
                padding: 7px 15px;
                border: 1px solid #E4D9D0;
                border-radius: 7px;
                background: white;
            }
        """)

        self.total = 0
        self.completed = 0
        self.good = 0
        self.bad = 0

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        title = QLabel("Proxy Runtime — Live Diagnostics")
        title.setObjectName("title")
        layout.addWidget(title)

        layout.addWidget(QLabel(
            "Read-only results from CHECKER. "
            "No second scan is performed."
        ))

        self.stats = QLabel()
        layout.addWidget(self.stats)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "Line", "Proxy", "Status",
            "Protocol", "Exit IP", "Reason",
        ])

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        header.setStretchLastSection(True)

        for column, width in enumerate(
            (65, 195, 85, 100, 155)
        ):
            self.table.setColumnWidth(column, width)

        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        layout.addWidget(self.table)

        bottom = QHBoxLayout()
        self.state = QLabel("Waiting for CHECKER...")
        bottom.addWidget(self.state, 1)

        close = QPushButton("Close")
        close.clicked.connect(self.hide)
        bottom.addWidget(close)

        layout.addLayout(bottom)
        self.refresh_stats()

    def reset(self, total=0):
        self.table.setRowCount(0)
        self.total = total
        self.completed = 0
        self.good = 0
        self.bad = 0
        self.state.setText(
            "Verification started in CHECKER..."
        )
        self.refresh_stats()

    def set_progress(self, completed, total):
        self.completed = completed
        self.total = total
        self.refresh_stats()

    def add_result(self, result):
        proxy = result.get("proxy")
        status = str(result.get("status", "BAD"))

        if status == "GOOD":
            self.good += 1
        else:
            self.bad += 1

        # Never display proxy username or password.
        label = proxy.label if proxy else "[invalid format]"

        values = [
            result.get("line", ""),
            label,
            status,
            result.get("protocol", ""),
            result.get("exit_ip", ""),
            result.get("reason", ""),
        ]

        row = self.table.rowCount()
        self.table.insertRow(row)

        for column, value in enumerate(values):
            self.table.setItem(
                row,
                column,
                QTableWidgetItem(str(value))
            )

        self.refresh_stats()

    def mark_finished(self):
        self.state.setText(
            "Verification finished. "
            "Showing the last CHECKER scan."
        )

    def refresh_stats(self):
        self.stats.setText(
            f"Loaded: {self.total}    "
            f"Checked: {self.completed}    "
            f"GOOD: {self.good}    "
            f"BAD: {self.bad}    "
            f"Pending: {max(0, self.total - self.completed)}"
        )

    def closeEvent(self, event):
        event.ignore()
        self.hide()
