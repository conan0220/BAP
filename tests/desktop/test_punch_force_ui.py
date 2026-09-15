from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QLabel

from bap_desktop.services.imu_discovery import DiscoveryResult, ImuSource
from bap_desktop.services.imu_scan import ConnectionType
from bap_desktop.ui.punch_items.page import PunchItemPage
from bap_desktop.ui.punch_items.force_view import ForceResultView


class Discovery:
    def __init__(self, sources):
        self.result = DiscoveryResult(tuple(sources), ())
    def discover(self, *, cancel_event=None):
        return self.result
    def clear(self):
        pass


SOURCES = (
    ImuSource("COM6", ConnectionType.WIRELESS_RECEIVER, group_id=0, node_id=0),
    ImuSource("COM6", ConnectionType.WIRELESS_RECEIVER, group_id=0, node_id=1),
)


def page_with_assignments(qtbot):
    page = PunchItemPage("出拳力量", Discovery(SOURCES))
    qtbot.addWidget(page)
    page._show_sources(DiscoveryResult(SOURCES, ()))
    first, second = page._source_selectors
    first.setCurrentIndex(1)
    second.setCurrentIndex(2)
    return page


def result(*, warning=False):
    warnings = ["實際取樣率低於建議值。"] if warning else []
    return {
        "algorithm_version": "bag_rigid_body_v1", "peak_elapsed_us": 3_000_000,
        "peak_force_n": 98.0665, "peak_force_kgf": 10.0,
        "peak_com_acceleration_g": 0.277778,
        "impact_height_from_bottom_m": 0.82, "impact_offset_from_center_m": 0.2,
        "sample_rate_hz": 400.0, "quality_status": "warning" if warning else "valid",
        "warnings": warnings,
        "curve_points": [
            {"elapsed_us": 2_200_000, "top_horizontal_acceleration_mps2": 0.0,
             "bottom_horizontal_acceleration_mps2": 0.0, "angular_acceleration_x_radps2": 0.0,
             "angular_acceleration_y_radps2": 0.0, "force_kgf": 0.0},
            {"elapsed_us": 3_000_000, "top_horizontal_acceleration_mps2": 3.0,
             "bottom_horizontal_acceleration_mps2": 2.0, "angular_acceleration_x_radps2": 0.0,
             "angular_acceleration_y_radps2": 1.0, "force_kgf": 10.0},
        ],
    }


@pytest.mark.scenario("desktop-app-shell", "查看拳擊測量項目")
@pytest.mark.scenario("desktop-app-shell", "進入單一拳擊項目")
@pytest.mark.scenario("desktop-app-shell", "出拳力量 version 1 可執行")
@pytest.mark.scenario("desktop-app-shell", "出拳力量 Executor 可用")
@pytest.mark.scenario("punch-force-analysis", "user 使用預設沙袋參數")
@pytest.mark.scenario("punch-force-analysis", "user 開始校正")
def test_force_capability_shows_parameters_before_calibration(qtbot) -> None:
    page = page_with_assignments(qtbot)
    page._capability_ready(SimpleNamespace(executable=True))
    assert not page.force_settings.isHidden()
    assert page.force_parameter_inputs["bag_mass_kg"].text() == "36"
    assert page.force_parameter_inputs["bag_length_m"].text() == "1.24"
    assert page.continue_button.text() == "開始校正"
    assert page.duration_row.isHidden()
    assert "沙袋完全靜止" in page.status.text()


@pytest.mark.scenario("punch-force-analysis", "user 輸入不合理的沙袋參數")
def test_force_invalid_physical_parameter_cannot_start(qtbot, tmp_path) -> None:
    class MustNotStart:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("invalid parameters must not start recording")
    page = page_with_assignments(qtbot)
    page.recording_root = tmp_path
    page.recording_factory = MustNotStart
    page._capability_ready(SimpleNamespace(executable=True))
    page.force_parameter_inputs["sensor_distance_m"].setText("2")
    page._start_measurement()
    assert page._measurement_state == "ready"
    assert "不得大於" in page.status.text()


@pytest.mark.scenario("punch-force-analysis", "校正完成後準備打擊")
def test_force_parameters_are_forwarded_to_two_stage_recording(qtbot, tmp_path) -> None:
    class Recording:
        def __init__(self, *_args, **kwargs):
            self.kwargs = kwargs
            self.is_calibrating = True
        def start(self):
            pass
        def abort(self):
            pass
        def calibration_remaining_seconds(self):
            return 2.0
        def calibration_due(self):
            return False
        def due_stop_reason(self):
            return None
    page = page_with_assignments(qtbot)
    page.recording_root = tmp_path
    page.recording_factory = Recording
    page._capability_ready(SimpleNamespace(executable=True))
    page._start_measurement()
    assert page._measurement_state == "calibrating"
    assert page._recording.kwargs["analysis_parameters"]["bag_mass_kg"] == 36.0
    assert page.duration_row.isHidden()


@pytest.mark.scenario("punch-force-analysis", "user 查看正常 Result")
@pytest.mark.scenario("punch-force-analysis", "user 查看具有警告的 Result")
def test_force_result_shows_units_quality_warnings_and_embedded_fallback(qtbot) -> None:
    def unavailable(_result):
        raise RuntimeError("no canvas")
    view = ForceResultView(result(warning=True), canvas_factory=unavailable)
    qtbot.addWidget(view)
    visible = " ".join(label.text() for label in view.findChildren(QLabel))
    assert "10.00 kgf" in visible and "98.07 N" in visible
    assert "距沙袋底部 0.820 m" in visible
    assert "不是 Force Plate" in visible
    assert "實際取樣率低於建議值" in visible
    assert hasattr(view, "fallback_label")


@pytest.mark.scenario("desktop-app-shell", "完成待開發項目的 IMU 來源選擇")
def test_non_executable_force_capability_never_starts_recording(qtbot) -> None:
    page = page_with_assignments(qtbot)
    page._capability_ready(SimpleNamespace(executable=False))
    assert "目前沒有提供" in page.status.text()
    assert not page.continue_button.isEnabled()


@pytest.mark.scenario("punch-force-analysis", "校正期間來源中斷")
def test_force_calibration_interruption_returns_to_rescan(qtbot) -> None:
    class Recording:
        aborted = False
        def due_stop_reason(self):
            from bap_common.analysis_session import SessionStopReason
            return SessionStopReason.SOURCE_INTERRUPTED
        def abort(self):
            self.aborted = True
    page = page_with_assignments(qtbot)
    page._recording = Recording()
    page._measurement_state = "calibrating"
    page._update_elapsed()
    assert page._recording.aborted
    assert page.continue_button.text() == "重新檢測 IMU"
