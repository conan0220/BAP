"""One-at-a-time boxing item page with fresh, role-based IMU assignment."""

from __future__ import annotations

from threading import Event

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bap_desktop.resources import text
from bap_desktop.services.imu_discovery import DiscoveryResult, ImuDiscoveryService, ImuSource
from bap_desktop.services.analysis_flow import AnalysisFlowService
from bap_desktop.services.analysis_recording import LiveAnalysisRecording, RecordingError, SessionDraft
from bap_desktop.ui.components import Card, PageHeader
from bap_desktop.ui.punch_items.definitions import ImuPlacement, get_punch_item_definition


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


class _FlowSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class _FlowWorker(QRunnable):
    def __init__(self, operation) -> None:
        super().__init__()
        self.operation = operation
        self.signals = _FlowSignals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.finished.emit(self.operation())
        except Exception as error:
            self.signals.failed.emit(str(error) or "目前無法完成操作")


class PunchItemPage(QWidget):
    def __init__(
        self,
        item_name: str,
        service: ImuDiscoveryService | None = None,
        analysis_flow: AnalysisFlowService | None = None,
        recording_root=None,
        desktop_version: str = "0.0.0",
        recording_factory=LiveAnalysisRecording,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.item_name = item_name
        self.definition = get_punch_item_definition(item_name)
        self.service = service or ImuDiscoveryService()
        self.analysis_flow = analysis_flow
        self.recording_root = recording_root
        self.desktop_version = desktop_version
        self.recording_factory = recording_factory
        self._recording: LiveAnalysisRecording | None = None
        self._draft: SessionDraft | None = None
        self._measurement_state = "assigning"
        self._elapsed_seconds = 0
        self._remote_session_id: str | None = None
        self._remote_analysis_id: str | None = None
        self.assignments: dict[str, ImuSource] = {}
        self._cancel_event: Event | None = None
        self._started = False
        self._shutdown = False
        self._source_selectors: dict[QComboBox, ImuPlacement] = {}
        self._assignment_rows: list[tuple[QGridLayout, QLabel, QComboBox]] = []
        self._latest_sources: tuple[ImuSource, ...] = ()

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(28, 26, 28, 28)
        self.layout.setSpacing(16)
        header = PageHeader(item_name, "系統會先自動確認所有 Port，再依照這個項目的需求分配 IMU。")
        self.analysis_chip = QLabel("分析功能待開發")
        self.analysis_chip.setObjectName("pendingChip")
        header.add_action(self.analysis_chip)
        self.layout.addWidget(header)

        self.card = Card()
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(20, 18, 20, 20)
        card_layout.setSpacing(12)
        self.status = QLabel(text.DISCOVERY_READY)
        self.status.setObjectName("sectionTitle")
        self.status.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setAccessibleName("IMU 探索進度")
        self.message = QLabel("")
        self.message.setObjectName("warningMessage")
        self.message.setWordWrap(True)
        self.message.setVisible(False)
        self.sources_container = QWidget()
        self.sources_layout = QVBoxLayout(self.sources_container)
        self.sources_layout.setContentsMargins(0, 0, 0, 0)
        self.sources_layout.setSpacing(10)
        self.continue_button = QPushButton("繼續")
        self.continue_button.setProperty("role", "primary")
        self.continue_button.setEnabled(False)
        self.continue_button.setAccessibleName("繼續到目前項目的待開發頁面")
        self.retry_button = QPushButton(text.DISCOVERY_RETRY)
        self.retry_button.setProperty("role", "secondary")
        self.retry_button.setVisible(False)
        actions = QHBoxLayout()
        actions.addWidget(self.retry_button)
        actions.addStretch(1)
        actions.addWidget(self.continue_button)
        for widget in (self.status, self.progress, self.message, self.sources_container):
            card_layout.addWidget(widget)
        card_layout.addLayout(actions)
        self.layout.addWidget(self.card)
        self.layout.addStretch(1)

        self.continue_button.clicked.connect(self._primary_action)
        self.retry_button.clicked.connect(self.start_discovery)
        self._start_timer = QTimer(self)
        self._start_timer.setSingleShot(True)
        self._start_timer.timeout.connect(self.start_discovery)
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._update_elapsed)

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
        self.assignments.clear()
        self._measurement_state = "assigning"
        self.continue_button.setText("繼續")
        self._latest_sources = ()
        self._clear_source_selectors()
        self.message.clear()
        self.message.setVisible(False)
        self.status.setText(text.DISCOVERY_RUNNING)
        self.progress.setVisible(True)
        self.continue_button.setEnabled(False)
        self.retry_button.setVisible(False)
        worker = _DiscoveryWorker(self.service, self._cancel_event)
        worker.signals.finished.connect(self._show_sources)
        worker.signals.failed.connect(self._show_error)
        QThreadPool.globalInstance().start(worker)

    def _clear_source_selectors(self) -> None:
        while self.sources_layout.count():
            item = self.sources_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._source_selectors.clear()
        self._assignment_rows.clear()

    @Slot(object)
    def _show_sources(self, result: DiscoveryResult) -> None:
        self.progress.setVisible(False)
        self._latest_sources = result.sources
        if not result.sources:
            self.status.setText(text.DISCOVERY_NOT_FOUND)
            for port, reason in result.port_reasons:
                reason_label = QLabel(f"{port}：{reason}")
                reason_label.setWordWrap(True)
                self.sources_layout.addWidget(reason_label)
            self.retry_button.setVisible(True)
            return

        if not self.definition.configuration_decided:
            self.status.setText(text.DISCOVERY_CONFIGURATION_PENDING)
            self.message.setText(self.definition.description)
            self.message.setVisible(True)
            self.retry_button.setVisible(True)
            return

        self.status.setText(text.DISCOVERY_SELECT)
        for placement in self.definition.placements:
            self._add_assignment_row(placement, result.sources)
        selectors = list(self._source_selectors)
        for current, following in zip(selectors, selectors[1:]):
            QWidget.setTabOrder(current, following)
        if selectors:
            QWidget.setTabOrder(selectors[-1], self.continue_button)
        if len(result.sources) < len(self.definition.placements):
            self.message.setText(text.DISCOVERY_INSUFFICIENT)
            self.message.setVisible(True)
        self._validate_assignments()

    def _add_assignment_row(
        self,
        placement: ImuPlacement,
        sources: tuple[ImuSource, ...],
    ) -> None:
        row = QFrame()
        row.setProperty("card", True)
        row_layout = QGridLayout(row)
        row_layout.setContentsMargins(12, 10, 12, 10)
        label = QLabel(f"{placement.name}\n配戴者：{placement.wearer}")
        label.setWordWrap(True)
        selector = QComboBox()
        selector.setAccessibleName(f"{placement.name}使用的 IMU")
        selector.addItem(text.IMU_PLACEHOLDER, None)
        for source in sources:
            selector.addItem(source.label, source)
        label.setBuddy(selector)
        selector.currentIndexChanged.connect(self._validate_assignments)
        row_layout.addWidget(label, 0, 0)
        row_layout.addWidget(selector, 0, 1)
        row_layout.setColumnStretch(0, 2)
        row_layout.setColumnStretch(1, 3)
        self.sources_layout.addWidget(row)
        self._source_selectors[selector] = placement
        self._assignment_rows.append((row_layout, label, selector))
        self._reflow_assignment_rows(self.width())

    def resizeEvent(self, event) -> None:
        self._reflow_assignment_rows(event.size().width())
        super().resizeEvent(event)

    def _reflow_assignment_rows(self, width: int) -> None:
        compact = width < 700
        for row_layout, label, selector in self._assignment_rows:
            if compact:
                row_layout.addWidget(label, 0, 0)
                row_layout.addWidget(selector, 1, 0)
                row_layout.setColumnStretch(0, 1)
                row_layout.setColumnStretch(1, 0)
            else:
                row_layout.addWidget(label, 0, 0)
                row_layout.addWidget(selector, 0, 1)
                row_layout.setColumnStretch(0, 2)
                row_layout.setColumnStretch(1, 3)

    @Slot()
    @Slot(int)
    def _validate_assignments(self, _index: int | None = None) -> None:
        self.assignments.clear()
        selected: list[ImuSource] = []
        for selector, placement in self._source_selectors.items():
            source = selector.currentData()
            if isinstance(source, ImuSource):
                self.assignments[placement.id] = source
                selected.append(source)

        complete = len(self.assignments) == len(self.definition.placements) > 0
        unique = len(set(selected)) == len(selected)
        if not unique:
            self.message.setText(text.DISCOVERY_DUPLICATE)
            self.message.setVisible(True)
        elif len(self._latest_sources) < len(self.definition.placements):
            self.message.setText(text.DISCOVERY_INSUFFICIENT)
            self.message.setVisible(True)
        else:
            self.message.clear()
            self.message.setVisible(False)
        self.continue_button.setEnabled(complete and unique)

    @Slot(str)
    def _show_error(self, message: str) -> None:
        self.progress.setVisible(False)
        self.status.setText(message)
        self.retry_button.setVisible(True)

    @Slot()
    def _primary_action(self) -> None:
        if self._measurement_state == "assigning":
            self._prepare_session()
        elif self._measurement_state == "ready":
            self._start_measurement()
        elif self._measurement_state == "recording":
            self._finish_measurement()
        elif self._measurement_state == "upload_failed":
            self._upload_and_wait()
        elif self._measurement_state == "poll_failed":
            self._poll_status()

    def _prepare_session(self) -> None:
        required = len(self.definition.placements)
        selected = tuple(self.assignments.values())
        if len(selected) != required or len(set(selected)) != required:
            return
        if self.analysis_flow is None:
            self._show_unavailable()
            return
        self.status.setText("正在確認 Backend 分析能力…")
        self.continue_button.setEnabled(False)
        worker = _FlowWorker(
            lambda: self.analysis_flow.capability(self.definition.analysis_type, 1)
        )
        worker.signals.finished.connect(self._capability_ready)
        worker.signals.failed.connect(self._show_error)
        QThreadPool.globalInstance().start(worker)

    @Slot(object)
    def _capability_ready(self, capability) -> None:
        if capability is None or not capability.executable:
            self._show_unavailable()
            return
        self._clear_source_selectors()
        self.message.setVisible(False)
        self.status.setText("IMU 已準備完成，按下「開始測量」後才會建立正式 CSV。")
        self.analysis_chip.setText("準備測量")
        self._measurement_state = "ready"
        self.continue_button.setText("開始測量")
        self.continue_button.setEnabled(True)
        self.retry_button.setVisible(False)
        self.service.clear()

    def _show_unavailable(self) -> None:
        self._clear_source_selectors()
        self.message.setVisible(False)
        self.status.setText(f"{self.item_name}：{text.PENDING}")
        self.analysis_chip.setText("分析功能待開發")
        self.continue_button.setEnabled(False)
        self.retry_button.setVisible(False)
        self.service.clear()

    def _start_measurement(self) -> None:
        if self.recording_root is None:
            self._show_error("本機 Session 暫存位置尚未設定")
            return
        try:
            self._recording = self.recording_factory(
                self.recording_root,
                assignments=self.assignments,
                analysis_type=self.definition.analysis_type,
                spec_version=1,
                desktop_version=self.desktop_version,
            )
            self._recording.start()
        except Exception:
            self._show_error("無法開始錄製 IMU 資料")
            return
        self._measurement_state = "recording"
        self._elapsed_seconds = 0
        self.status.setText("測量中｜00:00")
        self.continue_button.setText("結束測量")
        self.continue_button.setEnabled(True)
        self._elapsed_timer.start()

    def _update_elapsed(self) -> None:
        self._elapsed_seconds += 1
        minutes, seconds = divmod(self._elapsed_seconds, 60)
        self.status.setText(f"測量中｜{minutes:02d}:{seconds:02d}")

    def _finish_measurement(self) -> None:
        self._elapsed_timer.stop()
        self.continue_button.setEnabled(False)
        self.status.setText("正在完成 CSV…")
        recording = self._recording
        if recording is None:
            self._show_error("找不到目前的錄製工作")
            return
        worker = _FlowWorker(recording.stop)
        worker.signals.finished.connect(self._recording_finished)
        worker.signals.failed.connect(self._recording_failed)
        QThreadPool.globalInstance().start(worker)

    @Slot(object)
    def _recording_finished(self, draft: SessionDraft) -> None:
        self._draft = draft
        self._upload_and_wait()

    @Slot(str)
    def _recording_failed(self, _message: str) -> None:
        self._measurement_state = "failed"
        self.status.setText("IMU 錄製失敗，本次資料無法使用，請返回後重新測量。")
        self.continue_button.setEnabled(False)

    def _upload_and_wait(self) -> None:
        if self.analysis_flow is None or self._draft is None or self._draft.metadata is None:
            return
        self._measurement_state = "uploading"
        self.status.setText("正在上傳 Session…")
        self.continue_button.setEnabled(False)

        worker = _FlowWorker(lambda: self.analysis_flow.upload(self._draft))
        worker.signals.finished.connect(self._upload_succeeded)
        worker.signals.failed.connect(self._upload_failed)
        QThreadPool.globalInstance().start(worker)

    @Slot(object)
    def _upload_succeeded(self, response: dict) -> None:
        self.analysis_flow.remove_uploaded_package(self._draft)
        self._remote_session_id = response["session_id"]
        self._remote_analysis_id = response["analysis_ids"][0]
        self._measurement_state = "analyzing"
        self.status.setText("Backend 分析中…")
        self._poll_status()

    @Slot(str)
    def _upload_failed(self, message: str) -> None:
        if message.startswith("本機 CSV 已損壞"):
            self._measurement_state = "failed"
            self.status.setText(message)
            self.message.setText("本次測量資料無法使用，請返回後重新測量。")
            self.message.setVisible(True)
            self.continue_button.setEnabled(False)
            return
        self._measurement_state = "upload_failed"
        self.status.setText(f"上傳失敗：{message}")
        self.message.setText("本機 CSV 已保留，可以直接重試上傳，不需要重新測量。")
        self.message.setVisible(True)
        self.continue_button.setText("重試上傳")
        self.continue_button.setEnabled(True)

    @Slot(object)
    def _analysis_status_ready(self, payload: dict) -> None:
        state = payload.get("status")
        if state in {"pending", "processing"}:
            self._measurement_state = "analyzing"
            self.status.setText("Backend 分析中…")
            QTimer.singleShot(1000, self._poll_again)
            return
        if state == "failed":
            self._measurement_state = "failed"
            self.status.setText(payload.get("safe_error_message") or "Backend 分析失敗")
            return
        try:
            validated = self.analysis_flow.validate_completed(payload)
        except Exception:
            self._measurement_state = "failed"
            self.status.setText("Backend 回傳的 Result 格式不正確")
            return
        self._measurement_state = "completed"
        self.status.setText(f"分析完成｜Session {validated.session_id or self._draft.session_id}")
        self._clear_source_selectors()
        for key, value in validated.result.items():
            label = QLabel(f"{key}：{value}")
            label.setWordWrap(True)
            self.sources_layout.addWidget(label)

    def _poll_again(self) -> None:
        if self._shutdown:
            return
        self._poll_status()

    def _poll_status(self) -> None:
        if self._remote_session_id is None or self._remote_analysis_id is None:
            return
        self._measurement_state = "analyzing"
        self.status.setText("Backend 分析中…")
        self.continue_button.setEnabled(False)
        worker = _FlowWorker(
            lambda: self.analysis_flow.poll(self._remote_session_id, self._remote_analysis_id)
        )
        worker.signals.finished.connect(self._analysis_status_ready)
        worker.signals.failed.connect(self._poll_failed)
        QThreadPool.globalInstance().start(worker)

    @Slot(str)
    def _poll_failed(self, message: str) -> None:
        self._measurement_state = "poll_failed"
        self.status.setText(f"查詢分析狀態失敗：{message}")
        self.continue_button.setText("重試查詢")
        self.continue_button.setEnabled(True)

    def shutdown(self) -> None:
        self._shutdown = True
        self._start_timer.stop()
        self._elapsed_timer.stop()
        if self._cancel_event is not None:
            self._cancel_event.set()
        self.service.clear()
        if self._recording is not None and self._measurement_state == "recording":
            self._recording.abort()
