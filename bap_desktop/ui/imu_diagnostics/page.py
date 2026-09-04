"""Responsive PySide6 page for the IMU connection report."""

from __future__ import annotations

from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bap_desktop.resources import text
from bap_desktop.services.imu_diagnostics import REPORT_COLUMNS, DiagnosticReport, ImuDiagnosticsService
from bap_desktop.ui.components import Card, PageHeader


class _WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)
    phase = Signal(str)


class _DiagnosticWorker(QRunnable):
    def __init__(self, service: ImuDiagnosticsService, cancel_event: Event) -> None:
        super().__init__()
        self.service = service
        self.cancel_event = cancel_event
        self.signals = _WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.finished.emit(
                self.service.run(cancel_event=self.cancel_event, phase_callback=self.signals.phase.emit)
            )
        except Exception:
            self.signals.failed.emit("測試時發生未預期的錯誤，請重新測試。")


class ImuDiagnosticsPage(QWidget):
    """Automatically run diagnostics when the page is first opened."""

    def __init__(self, service: ImuDiagnosticsService | None = None, parent=None) -> None:
        super().__init__(parent)
        self.service = service or ImuDiagnosticsService()
        self._thread_pool = QThreadPool.globalInstance()
        self._cancel_event: Event | None = None
        self._started = False
        self._shutdown = False
        self._elapsed_tenths = 0

        self.retest_button = QPushButton(text.RETEST)
        self.retest_button.setProperty("role", "primary")
        self.retest_button.setAccessibleName("重新執行所有 Port 的 IMU 測試")
        self.export_button = QPushButton(text.EXPORT_CSV)
        self.export_button.setProperty("role", "secondary")
        self.export_button.setEnabled(False)
        header = PageHeader(
            text.IMU_DIAGNOSTICS,
            "使用 921600 baud rate 測試目前電腦上的所有 Port。",
        )
        header.add_action(self.export_button)
        header.add_action(self.retest_button)

        self.port_count_value = QLabel("0")
        self.port_count_value.setObjectName("pageTitle")
        self.connected_count_value = QLabel("0")
        self.connected_count_value.setObjectName("pageTitle")
        self.summary = QGridLayout()
        self.port_count_card = self._summary_card("找到的 Port", self.port_count_value)
        self.connected_count_card = self._summary_card("已連線", self.connected_count_value)
        self.summary.addWidget(self.port_count_card, 0, 0)
        self.summary.addWidget(self.connected_count_card, 0, 1)
        self.summary.setColumnStretch(0, 1)
        self.summary.setColumnStretch(1, 1)

        self.status_label = QLabel(text.DIAGNOSTIC_READY)
        self.status_label.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setObjectName("diagnosticProgress")
        self.progress.setRange(0, max(1, round(self.service.duration_seconds * 10)))
        self.progress.setFormat("%p%")
        self.progress.setTextVisible(True)
        self.progress.setAccessibleName("IMU 測試進度")
        self.table = QTableWidget(0, len(REPORT_COLUMNS))
        self.table.setHorizontalHeaderLabels(REPORT_COLUMNS)
        self.table.setAccessibleName("每個 Port 的 IMU 連線狀態 Report")
        self.table.setMinimumHeight(180)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(len(REPORT_COLUMNS) - 1, QHeaderView.ResizeMode.Stretch)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 28)
        layout.setSpacing(16)
        layout.addWidget(header)
        layout.addLayout(self.summary)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress)
        layout.addWidget(self.table, 1)

        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._advance_progress)
        self.retest_button.clicked.connect(self.start_test)
        self.export_button.clicked.connect(self._choose_export_path)
        self._start_timer = QTimer(self)
        self._start_timer.setSingleShot(True)
        self._start_timer.timeout.connect(self.start_test)
        self._compact_summary = False

    def resizeEvent(self, event) -> None:
        compact = event.size().width() < 620
        if compact != self._compact_summary:
            self._compact_summary = compact
            if compact:
                self.summary.addWidget(self.port_count_card, 0, 0)
                self.summary.addWidget(self.connected_count_card, 1, 0)
                self.summary.setColumnStretch(0, 1)
                self.summary.setColumnStretch(1, 0)
            else:
                self.summary.addWidget(self.port_count_card, 0, 0)
                self.summary.addWidget(self.connected_count_card, 0, 1)
                self.summary.setColumnStretch(0, 1)
                self.summary.setColumnStretch(1, 1)
        super().resizeEvent(event)

    @staticmethod
    def _summary_card(title: str, value: QLabel) -> Card:
        card = Card()
        layout = QVBoxLayout(card)
        label = QLabel(title)
        label.setProperty("muted", True)
        layout.addWidget(label)
        layout.addWidget(value)
        return card

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._started:
            self._started = True
            self._start_timer.start(0)

    @Slot()
    def start_test(self) -> None:
        if self._shutdown:
            return
        if self._cancel_event is not None:
            self._cancel_event.set()
        self._cancel_event = Event()
        self.table.setRowCount(0)
        self.port_count_value.setText("0")
        self.connected_count_value.setText("0")
        self.export_button.setEnabled(False)
        self.retest_button.setEnabled(False)
        self.status_label.setText(text.DIAGNOSTIC_COLLECTING)
        self._elapsed_tenths = 0
        self.progress.setValue(0)
        self._timer.start()
        worker = _DiagnosticWorker(self.service, self._cancel_event)
        worker.signals.finished.connect(self._show_report)
        worker.signals.failed.connect(self._show_error)
        worker.signals.phase.connect(self._show_phase)
        self._thread_pool.start(worker)

    @Slot(str)
    def _show_phase(self, phase: str) -> None:
        self.status_label.setText(
            text.DIAGNOSTIC_ANALYZING if phase == "analyzing" else text.DIAGNOSTIC_COLLECTING
        )

    @Slot()
    def _advance_progress(self) -> None:
        self._elapsed_tenths = min(self.progress.maximum(), self._elapsed_tenths + 1)
        self.progress.setValue(self._elapsed_tenths)

    @Slot(object)
    def _show_report(self, report: DiagnosticReport) -> None:
        self._timer.stop()
        self.progress.setValue(self.progress.maximum())
        self.status_label.setText(text.DIAGNOSTIC_COMPLETE if report.rows else text.NO_PORT)
        self.port_count_value.setText(str(len(report.rows)))
        self.connected_count_value.setText(str(sum(row.status == "已連線" for row in report.rows)))
        self.table.setRowCount(len(report.rows))
        for row_index, row in enumerate(report.rows):
            for column_index, value in enumerate(row.as_display_values()):
                self.table.setItem(row_index, column_index, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()
        self.export_button.setEnabled(bool(report.csv_files))
        self.retest_button.setEnabled(True)

    @Slot(str)
    def _show_error(self, message: str) -> None:
        self._timer.stop()
        self.status_label.setText(message)
        self.retest_button.setEnabled(True)

    @Slot()
    def _choose_export_path(self) -> None:
        report = self.service.latest_report
        if report is None or not report.csv_files:
            return
        try:
            if len(report.csv_files) == 1:
                suggested_name = report.csv_files[0].path.name
                destination, _ = QFileDialog.getSaveFileName(
                    self,
                    "匯出 IMU 測試 CSV",
                    suggested_name,
                    "CSV (*.csv)",
                )
                if destination:
                    self.service.export_csv(Path(destination))
            else:
                destination = QFileDialog.getExistingDirectory(
                    self,
                    "選擇多個 IMU 測試 CSV 的匯出資料夾",
                )
                if destination:
                    self.service.export_csv_files(Path(destination))
        except OSError:
            QMessageBox.warning(self, "匯出失敗", "無法寫入選擇的位置，請選擇其他資料夾。")

    def shutdown(self) -> None:
        self._shutdown = True
        self._start_timer.stop()
        if self._cancel_event is not None:
            self._cancel_event.set()
        self._timer.stop()
        self.service.cleanup()
