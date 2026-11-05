
"""
SHADOW SUITE PRO — ADDER
Placeholder module.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QLabel,
)


class AdderWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("SHADOW ADDER")
        self.resize(700, 420)

        root = QWidget()
        root.setStyleSheet(
            "background:#FFF7F0;color:#333A40;"
        )

        self.setCentralWidget(root)

        layout = QVBoxLayout(root)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel("SHADOW ADDER")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font:800 25px 'Segoe UI';"
        )

        subtitle = QLabel("COMING SOON")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(
            "font:600 15px 'Segoe UI';"
            "color:#C77C5B;"
        )

        layout.addWidget(title)
        layout.addSpacing(12)
        layout.addWidget(subtitle)
