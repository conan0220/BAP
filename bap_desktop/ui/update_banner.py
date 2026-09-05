"""Small, non-modal update status and action banner."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from bap_desktop.resources import text
from bap_desktop.services.update import UpdateResult, UpdateStatus


class UpdateBanner(QWidget):
    install_requested = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._result: UpdateResult | None = None
        self.message = QLabel("")
        self.download_button = QPushButton(text.UPDATE_DOWNLOAD)
        self.later_button = QPushButton(text.UPDATE_LATER)
        layout = QHBoxLayout(self)
        layout.addWidget(self.message)
        layout.addStretch(1)
        layout.addWidget(self.download_button)
        layout.addWidget(self.later_button)
        self.download_button.clicked.connect(self._install)
        self.later_button.clicked.connect(self.hide)
        self.download_button.hide()
        self.later_button.hide()
        self.hide()

    def show_result(self, result: UpdateResult) -> None:
        self._result = result
        available = (
            result.status is UpdateStatus.AVAILABLE
            and bool(result.download_url)
            and bool(result.sha256)
        )
        self.download_button.setEnabled(available)
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

    def show_download_progress(self, percent: int | None = None) -> None:
        self.download_button.setEnabled(False)
        self.later_button.setVisible(False)
        suffix = f" {percent}%" if percent is not None else ""
        self.message.setText(text.UPDATE_DOWNLOADING + suffix)
        self.show()

    def show_installing(self) -> None:
        self.download_button.setVisible(False)
        self.later_button.setVisible(False)
        self.message.setText(text.UPDATE_INSTALLING)
        self.show()

    def show_install_failed(self) -> None:
        self.download_button.setEnabled(self._result is not None)
        self.download_button.setVisible(self._result is not None)
        self.later_button.setVisible(True)
        self.message.setText(text.UPDATE_FAILED)
        self.show()

    def _install(self) -> None:
        if self._result is not None:
            self.install_requested.emit(self._result)
