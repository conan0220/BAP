from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from PySide6.QtWidgets import QFileDialog, QMessageBox

from bap_common.benchmark_bundle import BenchmarkStopReason
from bap_desktop.services.benchmark_recorder import BenchmarkRecorderState
from bap_desktop.services.imu_discovery import DiscoveryResult, ImuSource
from bap_desktop.services.imu_scan import ConnectionType
from bap_desktop.ui.benchmark import BenchmarkRecorderPage


class Service:
    def discover(self, **_kwargs):
        return DiscoveryResult(sources=(), port_reasons=())
    def clear(self):
        pass


class Coordinator:
    def __init__(self, _root, *, desktop_version):
        self.desktop_version = desktop_version; self.state = BenchmarkRecorderState.SCANNING
        self.has_unsaved_recording = False; self.capture_result = SimpleNamespace(directory=Path("staging")); self.assignments = {}
        self.discarded = False; self.exported = None; self.stop_reason = None
    def begin_scan(self): self.state = BenchmarkRecorderState.SCANNING
    def complete_scan(self, result): self.sources = result.sources; self.state = BenchmarkRecorderState.READY
    def set_assignments(self, assignments): self.assignments = assignments
    def start(self, duration): self.requested = duration; self.state = BenchmarkRecorderState.RECORDING
    def elapsed_seconds(self): return 1.2
    def remaining_seconds(self): return 58.8
    def tick(self): return False
    def stop_early(self): self.state = BenchmarkRecorderState.LABELING; self.has_unsaved_recording = True; self.stop_reason = BenchmarkStopReason.ENDED_BY_USER
    def set_ground_truth(self, left, right, *, notes=""):
        if not left or not right:
            from bap_desktop.services.benchmark_recorder import BenchmarkRecorderError
            raise BenchmarkRecorderError("missing")
        self.state = BenchmarkRecorderState.READY_TO_EXPORT
        return SimpleNamespace(total_punch_count=int(left) + int(right))
    def metadata(self): return SimpleNamespace(session_id=uuid4())
    def mark_exported(self, path): self.exported = Path(path); self.state = BenchmarkRecorderState.EXPORTED; self.has_unsaved_recording = False
    def discard(self): self.discarded = True; self.has_unsaved_recording = False; self.state = BenchmarkRecorderState.DISCARDED


def make_page(qtbot, tmp_path: Path):
    page = BenchmarkRecorderPage(service=Service(), recording_root=tmp_path, desktop_version="0.1.9", coordinator_factory=Coordinator)
    qtbot.addWidget(page)
    sources = (ImuSource("COM1", ConnectionType.WIRED), ImuSource("COM2", ConnectionType.WIRED))
    page._show_sources(DiscoveryResult(sources=sources, port_reasons=()))
    return page


@pytest.mark.scenario("benchmark-data-recorder", "user 進入 Benchmark 資料錄製")
def test_page_explains_local_only_manual_ground_truth_and_keyboard_fields(qtbot, tmp_path: Path) -> None:
    page = make_page(qtbot, tmp_path)
    visible = " ".join(label.text() for label in page.findChildren(type(page.status)))
    assert "不會上傳 Backend" in visible
    assert "人工確認" in visible
    assert page.left_selector.accessibleName() == "左手腕 IMU"
    assert page.right_selector.accessibleName() == "右手腕 IMU"
    assert page.duration.minimum() == 5 and page.duration.maximum() == 3600 and page.duration.value() == 60


def test_page_requires_two_distinct_sources_and_completes_label_flow(qtbot, tmp_path: Path) -> None:
    page = make_page(qtbot, tmp_path)
    page.left_selector.setCurrentIndex(1); page.right_selector.setCurrentIndex(1)
    assert not page.primary_button.isEnabled()
    page.right_selector.setCurrentIndex(2)
    assert page.primary_button.isEnabled()
    page._primary_action()
    assert page.coordinator.state is BenchmarkRecorderState.RECORDING
    assert page.primary_button.text() == "提前結束"
    assert "剩餘" in page.status.text()
    page._primary_action()
    assert page.label_card.isVisible() is False  # parent page is not shown in this source-level Qt test
    page.left_count.setText("3"); page.right_count.setText("4")
    assert page.total_count.text() == "7"
    assert page.primary_button.isEnabled()
    assert "Ground Truth" in page.label_card.findChild(type(page.status)).text()


def test_page_explains_that_interrupted_source_data_was_kept(qtbot, tmp_path: Path) -> None:
    page = make_page(qtbot, tmp_path)
    page.coordinator.stop_reason = BenchmarkStopReason.SOURCE_INTERRUPTED

    page._show_labeling()

    assert "IMU 中斷" in page.status.text()
    assert "保留中斷前的資料" in page.status.text()
    assert page.primary_button.text() == "匯出 Benchmark"


@pytest.mark.scenario("benchmark-data-recorder", "user 取消儲存對話框")
def test_cancelled_save_keeps_unsaved_recording(qtbot, tmp_path: Path, monkeypatch) -> None:
    page = make_page(qtbot, tmp_path); page.left_selector.setCurrentIndex(1); page.right_selector.setCurrentIndex(2)
    page._start_recording(); page._finish_early(); page.left_count.setText("1"); page.right_count.setText("2")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: ("", ""))
    assert not page._export()
    assert page.coordinator.has_unsaved_recording
    assert "仍保留" in page.status.text()


@pytest.mark.scenario("benchmark-data-recorder", "user 離開但尚未匯出")
def test_close_prompt_can_cancel_or_discard_unsaved_recording(qtbot, tmp_path: Path, monkeypatch) -> None:
    page = make_page(qtbot, tmp_path); page.coordinator.has_unsaved_recording = True; page.coordinator.state = BenchmarkRecorderState.LABELING
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Cancel)
    assert not page.can_close()
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: int(QMessageBox.StandardButton.Discard))
    assert page.can_close()
    assert page.coordinator.discarded


@pytest.mark.scenario("benchmark-data-recorder", "user 離開前選擇匯出尚未保存的錄製")
def test_close_prompt_accepts_save_button_value(qtbot, tmp_path: Path, monkeypatch) -> None:
    page = make_page(qtbot, tmp_path)
    page.coordinator.has_unsaved_recording = True
    page.coordinator.state = BenchmarkRecorderState.LABELING
    export_calls = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: int(QMessageBox.StandardButton.Save),
    )
    monkeypatch.setattr(page, "_export", lambda: export_calls.append(True) or True)

    assert page.can_close()
    assert export_calls == [True]

@pytest.mark.scenario("benchmark-data-recorder", "user 查看側邊導覽")
@pytest.mark.scenario("benchmark-data-recorder", "user 開啟 Benchmark Recorder")
def test_app_shell_has_separate_developer_tool_navigation(qtbot) -> None:
    from PySide6.QtWidgets import QWidget
    from bap_desktop.ui.app_shell import AppShell

    shell = AppShell(QWidget())
    qtbot.addWidget(shell)
    requested = []
    shell.benchmark_requested.connect(lambda: requested.append(True))
    assert "benchmark-recorder" in shell.nav_buttons
    assert "Benchmark 資料錄製" not in [key.removeprefix("punch:") for key in shell.nav_buttons if key.startswith("punch:")]
    shell.nav_buttons["benchmark-recorder"].click()
    assert requested == [True]


def test_recorder_layout_keeps_controls_when_window_is_narrow(qtbot, tmp_path: Path) -> None:
    page = make_page(qtbot, tmp_path)
    page.resize(480, 700)
    page.show()
    qtbot.wait(10)
    assert page.left_selector.isVisible()
    assert page.right_selector.isVisible()
    assert page.duration.isVisible()
    assert page.primary_button.isVisible()

@pytest.mark.scenario("benchmark-data-recorder", "user 完成匯出")
def test_ui_successfully_exports_selected_bundle(qtbot, tmp_path: Path, monkeypatch) -> None:
    import bap_desktop.ui.benchmark.page as page_module

    page = make_page(qtbot, tmp_path)
    page.left_selector.setCurrentIndex(1); page.right_selector.setCurrentIndex(2)
    page._start_recording(); page._finish_early()
    page.left_count.setText("5"); page.right_count.setText("6")
    destination = tmp_path / "selected.zip"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(destination), "ZIP (*.zip)"))
    monkeypatch.setattr(page_module, "export_benchmark_bundle", lambda metadata, staging, path: Path(path))
    assert page._export()
    assert page.coordinator.state is BenchmarkRecorderState.EXPORTED
    assert str(destination) in page.status.text()


def test_settings_create_benchmark_staging_directory(tmp_path: Path) -> None:
    from bap_desktop.settings import DesktopSettings

    settings = DesktopSettings(data_dir=tmp_path)
    settings.prepare_local_directories()
    assert settings.benchmark_recordings_dir == tmp_path / "temp" / "benchmark-recordings"
    assert settings.benchmark_recordings_dir.is_dir()
