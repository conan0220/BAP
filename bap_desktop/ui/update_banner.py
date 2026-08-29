"""Small, non-modal update status and action banner."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from bap_desktop.resources import text
from bap_desktop.services.update import UpdateResult, UpdateStatus


class UpdateBanner(QWidget):
    download_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._download_url: str | None = None
        self.message = QLabel("")
        self.download_button = QPushButton(text.UPDATE_DOWNLOAD)
        self.later_button = QPushButton(text.UPDATE_LATER)
        layout = QHBoxLayout(self)
        layout.addWidget(self.message)
        layout.addStretch(1)
        layout.addWidget(self.download_button)
        layout.addWidget(self.later_button)
        self.download_button.clicked.connect(self._download)
        self.later_button.clicked.connect(self.hide)
        self.hide()

    def show_result(self, result: UpdateResult) -> None:
        self._download_url = result.download_url
        available = result.status is UpdateStatus.AVAILABLE and bool(result.download_url)
        self.download_button.setVisible(available)
        self.later_button.setVisible(result.status is UpdateStatus.AVAILABLE)
        if result.status is UpdateStatus.AVAILABLE:
            self.message.setText(
                f"發現新版。目前版本：{result.current_version}；最新版本：{result.latest_version}。"
            )
        elif result.status is UpdateStatus.LATEST:
            self.message.setText(text.UPDATE_LATEST)
        elif result.status is UpdateStatus.OFFLINE:
            self.message.setText(text.UPDATE_OFFLINE)
        else:
            self.message.setText(text.UPDATE_INVALID)
        self.show()

    def _download(self) -> None:
        if self._download_url:
            self.download_requested.emit(self._download_url)

