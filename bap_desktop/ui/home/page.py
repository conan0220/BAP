"""Authenticated home page with one entry per available feature."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from bap_desktop.resources import text


class HomePage(QWidget):
    open_diagnostics = Signal()
    open_punch_item = Signal(str)
    logout_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.diagnostics_button = QPushButton(text.IMU_DIAGNOSTICS)
        self.logout_button = QPushButton(text.LOGOUT)
        self.punch_buttons: dict[str, QPushButton] = {}

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(text.HOME_TITLE))
        layout.addWidget(QLabel(text.HOME_DESCRIPTION))
        layout.addWidget(self.diagnostics_button)
        for item_name in text.PUNCH_ITEMS:
            button = QPushButton(f"{item_name}｜{text.PENDING}")
            button.clicked.connect(lambda _checked=False, name=item_name: self.open_punch_item.emit(name))
            self.punch_buttons[item_name] = button
            layout.addWidget(button)
        layout.addStretch(1)
        layout.addWidget(self.logout_button)

        self.diagnostics_button.clicked.connect(self.open_diagnostics)
        self.logout_button.clicked.connect(self.logout_requested)

