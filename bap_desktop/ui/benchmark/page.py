"""Authenticated developer tool for recording labeled local benchmark bundles."""

from __future__ import annotations

from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QProgressBar, QPushButton, QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)

from bap_common.benchmark_bundle import BenchmarkStopReason
from bap_desktop.services.benchmark_recorder import (
    BenchmarkRecorderCoordinator, BenchmarkRecorderError, BenchmarkRecorderState,
    benchmark_bundle_filename, export_benchmark_bundle,
)
from bap_desktop.services.imu_discovery import DiscoveryResult, ImuDiscoveryService, ImuSource
from bap_desktop.ui.components import Card, PageHeader


class _DiscoverySignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class _DiscoveryWorker(QRunnable):
    def __init__(self, service: ImuDiscoveryService, cancel_event: Event) -> None:
        super().__init__(); self.service = service; self.cancel_event = cancel_event; self.signals = _DiscoverySignals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.finished.emit(self.service.discover(cancel_event=self.cancel_event))
        except Exception:
            self.signals.failed.emit("掃描 IMU 時發生錯誤，請稍後重試。")


class BenchmarkRecorderPage(QWidget):
    def __init__(
        self,
        *,
        service: ImuDiscoveryService | None = None,
        recording_root: Path | None = None,
        desktop_version: str = "0.0.0",
        coordinator_factory=BenchmarkRecorderCoordinator,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.service = service or ImuDiscoveryService()
        self.recording_root = Path(recording_root) if recording_root is not None else None
        self.coordinator = (
            coordinator_factory(self.recording_root, desktop_version=desktop_version)
            if self.recording_root is not None else None
        )
        self._started = False
        self._cancel_event: Event | None = None
        self._selectors: dict[str, QComboBox] = {}

        layout = QVBoxLayout(self); layout.setContentsMargins(28, 26, 28, 28); layout.setSpacing(16)
        layout.addWidget(PageHeader(
            "Benchmark 資料錄製",
            "錄製 Shadow boxing 的左右手腕 IMU，並加入人工確認的實際出拳次數。資料只匯出到本機，不會上傳 Backend。",
        ))

        self.setup_card = Card(); setup = QFormLayout(self.setup_card); setup.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows); setup.setContentsMargins(20, 18, 20, 20); setup.setSpacing(12)
        self.status = QLabel("正在準備掃描 IMU…"); self.status.setObjectName("sectionTitle"); self.status.setWordWrap(True)
        self.progress = QProgressBar(); self.progress.setRange(0, 0); self.progress.setAccessibleName("Benchmark IMU 掃描進度")
        self.analysis_selector = QComboBox(); self.analysis_selector.setAccessibleName("Benchmark 錄製項目")
        self.analysis_selector.addItem("出拳次數", "punch_count")
        self.left_selector = QComboBox(); self.left_selector.setAccessibleName("左手腕 IMU")
        self.right_selector = QComboBox(); self.right_selector.setAccessibleName("右手腕 IMU")
        self._selectors = {"left_wrist": self.left_selector, "right_wrist": self.right_selector}
        self._clear_sources()
        self.duration = QSpinBox(); self.duration.setRange(5, 3600); self.duration.setValue(60); self.duration.setSuffix(" 秒"); self.duration.setAccessibleName("預定錄製時間")
        setup.addRow(self.status); setup.addRow(self.progress); setup.addRow("Benchmark 項目", self.analysis_selector); setup.addRow("活動類型", QLabel("Shadow boxing")); setup.addRow("左手腕", self.left_selector); setup.addRow("右手腕", self.right_selector); setup.addRow("錄製時間", self.duration)
        layout.addWidget(self.setup_card)

        self.label_card = Card(); form = QFormLayout(self.label_card); form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows); form.setContentsMargins(20, 18, 20, 20); form.setSpacing(12)
        explanation = QLabel("Ground Truth 是人工確認的標記，不是系統分析結果。請在錄製後填入實際出拳次數。"); explanation.setWordWrap(True)
        self.left_count = QLineEdit(); self.left_count.setAccessibleName("左手實際出拳次數"); self.left_count.setValidator(QIntValidator(0, 999999, self))
        self.right_count = QLineEdit(); self.right_count.setAccessibleName("右手實際出拳次數"); self.right_count.setValidator(QIntValidator(0, 999999, self))
        self.total_count = QLabel("—"); self.total_count.setAccessibleName("實際總拳數")
        self.notes = QTextEdit(); self.notes.setAccessibleName("人工審查備註"); self.notes.setMaximumHeight(90); self.notes.setPlaceholderText("選填；例如姿勢、場地或需要注意的資料片段")
        form.addRow(explanation); form.addRow("左手拳數", self.left_count); form.addRow("右手拳數", self.right_count); form.addRow("總拳數", self.total_count); form.addRow("備註", self.notes)
        self.label_card.setVisible(False); layout.addWidget(self.label_card)

        actions = QHBoxLayout()
        self.retry_button = QPushButton("重新掃描"); self.retry_button.setProperty("role", "secondary"); self.retry_button.setVisible(False)
        self.primary_button = QPushButton("開始錄製"); self.primary_button.setProperty("role", "primary"); self.primary_button.setEnabled(False)
        self.primary_button.setAccessibleName("開始錄製 Benchmark")
        actions.addWidget(self.retry_button); actions.addStretch(1); actions.addWidget(self.primary_button); layout.addLayout(actions); layout.addStretch(1)

        self.left_selector.currentIndexChanged.connect(self._validate_assignments)
        self.right_selector.currentIndexChanged.connect(self._validate_assignments)
        self.left_count.textChanged.connect(self._validate_ground_truth)
        self.right_count.textChanged.connect(self._validate_ground_truth)
        self.notes.textChanged.connect(self._validate_ground_truth)
        self.retry_button.clicked.connect(self.start_discovery)
        self.primary_button.clicked.connect(self._primary_action)
        self._start_timer = QTimer(self); self._start_timer.setSingleShot(True); self._start_timer.timeout.connect(self.start_discovery)
        self._record_timer = QTimer(self); self._record_timer.setInterval(100); self._record_timer.timeout.connect(self._recording_tick)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._started:
            self._started = True; self._start_timer.start(0)

    @Slot()
    def start_discovery(self) -> None:
        if self.coordinator is None:
            self.status.setText("Benchmark 本機暫存位置尚未設定"); return
        try:
            self.coordinator.begin_scan()
        except BenchmarkRecorderError as error:
            self.status.setText(str(error)); return
        if self._cancel_event is not None: self._cancel_event.set()
        self._cancel_event = Event(); self._clear_sources(); self.status.setText("正在掃描所有 Port（固定 921600 baud rate）…")
        self.progress.setVisible(True); self.retry_button.setVisible(False); self.primary_button.setEnabled(False)
        worker = _DiscoveryWorker(self.service, self._cancel_event); worker.signals.finished.connect(self._show_sources); worker.signals.failed.connect(self._show_error); QThreadPool.globalInstance().start(worker)

    def _clear_sources(self) -> None:
        for selector in self._selectors.values(): selector.clear(); selector.addItem("請選擇 IMU", None)

    @Slot(object)
    def _show_sources(self, result: DiscoveryResult) -> None:
        self.progress.setVisible(False)
        if self.coordinator is None: return
        self.coordinator.complete_scan(result)
        if not result.sources:
            reasons = "；".join(f"{port}：{reason}" for port, reason in result.port_reasons)
            self.status.setText("找不到可用 IMU。" + (f" {reasons}" if reasons else "")); self.retry_button.setVisible(True); return
        for selector in self._selectors.values():
            for source in result.sources: selector.addItem(source.label, source)
        self.status.setText("請為左右手腕選擇不同的 IMU，再設定錄製時間。")
        self.retry_button.setVisible(True); self._validate_assignments()

    @Slot()
    @Slot(int)
    def _validate_assignments(self, _index: int | None = None) -> None:
        selected = [selector.currentData() for selector in self._selectors.values()]
        valid = all(isinstance(item, ImuSource) for item in selected) and len(set(selected)) == 2
        self.primary_button.setEnabled(valid)
        if all(isinstance(item, ImuSource) for item in selected) and len(set(selected)) != 2:
            self.status.setText("左右手腕不得使用同一顆 IMU。")

    @Slot(str)
    def _show_error(self, message: str) -> None:
        self.progress.setVisible(False); self.status.setText(message); self.retry_button.setVisible(True)

    @Slot()
    def _primary_action(self) -> None:
        if self.coordinator is None: return
        if self.coordinator.state is BenchmarkRecorderState.READY: self._start_recording()
        elif self.coordinator.state is BenchmarkRecorderState.RECORDING: self._finish_early()
        elif self.coordinator.state in {BenchmarkRecorderState.LABELING, BenchmarkRecorderState.READY_TO_EXPORT}: self._export()

    def _start_recording(self) -> None:
        assignments = {role: selector.currentData() for role, selector in self._selectors.items()}
        try:
            self.coordinator.set_assignments(assignments); self.coordinator.start(self.duration.value())
        except BenchmarkRecorderError as error:
            self.status.setText(str(error)); return
        self.analysis_selector.setEnabled(False); self.duration.setEnabled(False); self.left_selector.setEnabled(False); self.right_selector.setEnabled(False); self.retry_button.setVisible(False)
        self.primary_button.setText("提前結束"); self.primary_button.setEnabled(True); self._record_timer.start(); self._refresh_recording_status()

    def _refresh_recording_status(self) -> None:
        if self.coordinator is None: return
        elapsed = self.coordinator.elapsed_seconds(); remaining = self.coordinator.remaining_seconds()
        self.status.setText(f"錄製中｜已錄製 {elapsed:.1f} 秒｜剩餘 {remaining:.1f} 秒")

    @Slot()
    def _recording_tick(self) -> None:
        if self.coordinator is None: return
        try:
            finished = self.coordinator.tick()
        except BenchmarkRecorderError as error:
            self._record_timer.stop(); self.status.setText(str(error)); self.primary_button.setEnabled(False); return
        if finished: self._show_labeling()
        else: self._refresh_recording_status()

    def _finish_early(self) -> None:
        if self.coordinator is None: return
        try: self.coordinator.stop_early()
        except BenchmarkRecorderError as error:
            self.status.setText(str(error)); self.primary_button.setEnabled(False); return
        self._show_labeling()

    def _show_labeling(self) -> None:
        self._record_timer.stop(); self.label_card.setVisible(True)
        if self.coordinator is not None and self.coordinator.stop_reason is BenchmarkStopReason.SOURCE_INTERRUPTED:
            self.status.setText("偵測到 IMU 中斷，已停止錄製並保留中斷前的資料。請確認 Ground Truth 後匯出。")
        else:
            self.status.setText("錄製完成。請人工確認並填入左右手實際出拳次數。")
        self.primary_button.setText("匯出 Benchmark"); self.primary_button.setEnabled(False); self.left_count.setFocus()

    @Slot()
    @Slot(str)
    def _validate_ground_truth(self, _value: str | None = None) -> None:
        if self.coordinator is None or self.coordinator.state not in {BenchmarkRecorderState.LABELING, BenchmarkRecorderState.READY_TO_EXPORT}: return
        try:
            truth = self.coordinator.set_ground_truth(self.left_count.text(), self.right_count.text(), notes=self.notes.toPlainText())
        except BenchmarkRecorderError:
            self.total_count.setText("—"); self.primary_button.setEnabled(False); return
        self.total_count.setText(str(truth.total_punch_count)); self.primary_button.setEnabled(True)

    def _export(self) -> bool:
        if self.coordinator is None: return False
        try: metadata = self.coordinator.metadata()
        except BenchmarkRecorderError as error:
            self.status.setText(str(error)); return False
        path, _ = QFileDialog.getSaveFileName(self, "匯出 Benchmark", benchmark_bundle_filename(metadata), "ZIP (*.zip)")
        if not path:
            self.status.setText("已取消匯出；本次錄製仍保留，可再次匯出。"); return False
        try:
            exported = export_benchmark_bundle(metadata, self.coordinator.capture_result.directory, Path(path))
            self.coordinator.mark_exported(exported)
        except BenchmarkRecorderError as error:
            self.status.setText(str(error)); return False
        self.status.setText(f"Benchmark 已匯出：{exported}"); self.primary_button.setEnabled(False); return True

    def can_close(self) -> bool:
        if self.coordinator is None or not self.coordinator.has_unsaved_recording: return True
        choice = QMessageBox.warning(
            self, "尚未匯出 Benchmark", "這次錄製尚未匯出。要先匯出，還是確認捨棄？",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if choice == QMessageBox.StandardButton.Save: return self._export()
        if choice == QMessageBox.StandardButton.Discard:
            self.coordinator.discard(); return True
        return False

    def shutdown(self) -> None:
        self._start_timer.stop(); self._record_timer.stop()
        if self._cancel_event is not None: self._cancel_event.set()
        if self.coordinator is not None and self.coordinator.state is BenchmarkRecorderState.RECORDING:
            self.coordinator.discard()
        self.service.clear()
