"""One-at-a-time boxing item page with mandatory fresh IMU discovery."""

from __future__ import annotations

from threading import Event

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QButtonGroup,
    QLabel,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from bap_desktop.services.imu_discovery import (
    DiscoveryResult,
    ImuDiscoveryService,
    ImuSource,
)
from bap_desktop.resources import text


class _DiscoverySignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class _DiscoveryWorker(QRunnable):
    def __init__(self, service: ImuDiscoveryService, cancel_event: Event) -> None:
        super().__init__()
        self.service = service
        self.cancel_event = cancel_event
        self.signals = _DiscoverySignals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.finished.emit(self.service.discover(cancel_event=self.cancel_event))
        except Exception:
            self.signals.failed.emit("確認 IMU 時發生錯誤，請再次確認。")


class PunchItemPage(QWidget):
    def __init__(
        self,
        item_name: str,
        service: ImuDiscoveryService | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.item_name = item_name
        self.service = service or ImuDiscoveryService()
        self.selected_source: ImuSource | None = None
        self._cancel_event: Event | None = None
        self._started = False
        self._shutdown = False
        self._source_buttons: dict[QRadioButton, ImuSource] = {}

        self.layout = QVBoxLayout(self)
        self.title = QLabel(item_name)
        self.status = QLabel(text.DISCOVERY_READY)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.sources_container = QWidget()
        self.sources_layout = QVBoxLayout(self.sources_container)
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        self.continue_button = QPushButton("繼續")
        self.continue_button.setEnabled(False)
        self.retry_button = QPushButton(text.DISCOVERY_RETRY)
        self.retry_button.setVisible(False)
        for widget in (
            self.title,
            self.status,
            self.progress,
            self.sources_container,
            self.continue_button,
            self.retry_button,
        ):
            self.layout.addWidget(widget)

        self.button_group.buttonToggled.connect(self._source_toggled)
        self.continue_button.clicked.connect(self._show_pending)
        self.retry_button.clicked.connect(self.start_discovery)
        self._start_timer = QTimer(self)
        self._start_timer.setSingleShot(True)
        self._start_timer.timeout.connect(self.start_discovery)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._started:
            self._started = True
            self._start_timer.start(0)

    @Slot()
    def start_discovery(self) -> None:
        if self._shutdown:
            return
        if self._cancel_event is not None:
            self._cancel_event.set()
        self._cancel_event = Event()
        self.selected_source = None
        self._clear_source_buttons()
        self.status.setText(text.DISCOVERY_RUNNING)
        self.progress.setVisible(True)
        self.continue_button.setEnabled(False)
        self.retry_button.setVisible(False)
        worker = _DiscoveryWorker(self.service, self._cancel_event)
        worker.signals.finished.connect(self._show_sources)
        worker.signals.failed.connect(self._show_error)
        QThreadPool.globalInstance().start(worker)

    def _clear_source_buttons(self) -> None:
        for button in tuple(self._source_buttons):
            self.button_group.removeButton(button)
        while self.sources_layout.count():
            item = self.sources_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._source_buttons.clear()

    @Slot(object)
    def _show_sources(self, result: DiscoveryResult) -> None:
        self.progress.setVisible(False)
        if not result.sources:
            self.status.setText(text.DISCOVERY_NOT_FOUND)
            for port, reason in result.port_reasons:
                self.sources_layout.addWidget(QLabel(f"{port}：{reason}"))
            self.retry_button.setVisible(True)
            return
        self.status.setText(text.DISCOVERY_SELECT)
        for source in result.sources:
            button = QRadioButton(source.label)
            self.button_group.addButton(button)
            self.sources_layout.addWidget(button)
            self._source_buttons[button] = source

    @Slot(str)
    def _show_error(self, message: str) -> None:
        self.progress.setVisible(False)
        self.status.setText(message)
        self.retry_button.setVisible(True)

    @Slot(object, bool)
    def _source_toggled(self, button: QRadioButton, checked: bool) -> None:
        if checked:
            self.selected_source = self._source_buttons.get(button)
            self.continue_button.setEnabled(self.selected_source is not None)

    @Slot()
    def _show_pending(self) -> None:
        if self.selected_source is None:
            return
        self._clear_source_buttons()
        self.status.setText(f"{self.item_name}：{text.PENDING}")
        self.continue_button.setEnabled(False)
        self.service.clear()

    def shutdown(self) -> None:
        self._shutdown = True
        self._start_timer.stop()
        if self._cancel_event is not None:
            self._cancel_event.set()
        self.service.clear()
