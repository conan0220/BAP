from __future__ import annotations

from copy import deepcopy

import pytest
from PySide6.QtWidgets import QWidget

from bap_desktop.ui.punch_items.trajectory_view import TrajectoryResultView


def trajectory(hand: str, punch_index: int, start: int, scale: float = 1.0) -> dict:
    return {
        "hand": hand,
        "punch_index": punch_index,
        "start_elapsed_us": start,
        "end_elapsed_us": start + 200_000,
        "duration_seconds": 0.2,
        "path_length_m": 0.4 * scale,
        "maximum_displacement_m": 0.3 * scale,
        "points": [
            {"elapsed_us": start, "x_m": 0.0, "y_m": 0.0, "z_m": 0.0},
            {"elapsed_us": start + 100_000, "x_m": 0.1 * scale, "y_m": 0.2 * scale, "z_m": 0.05},
            {"elapsed_us": start + 200_000, "x_m": 0.0, "y_m": 0.3 * scale, "z_m": 0.0},
        ],
    }


def result() -> dict:
    trajectories = [
        trajectory("right", 1, 2_500_000),
        trajectory("left", 1, 2_200_000),
        trajectory("left", 2, 3_000_000, 2.0),
    ]
    return {
        "algorithm_version": "trajectory_rule_v1",
        "coordinate_system": "session_local_x_right_y_forward_z_up",
        "distance_unit": "m",
        "left_punch_count": 2,
        "right_punch_count": 1,
        "total_punch_count": 3,
        "trajectories": trajectories,
    }


class FakeCanvas:
    def __init__(self):
        self.widget = QWidget()
        self.shown = []
        self.cameras = []

    def show_trajectory(self, value):
        self.shown.append(value)

    def set_camera(self, preset, distance):
        self.cameras.append((preset, distance))


@pytest.mark.scenario("punch-trajectory-analysis", "首次顯示有效軌跡 Result")
@pytest.mark.scenario("punch-trajectory-analysis", "user 切換手別或拳次")
def test_view_selects_earliest_punch_and_switches_locally(qtbot) -> None:
    source = result()
    original = deepcopy(source)
    canvas = FakeCanvas()
    view = TrajectoryResultView(source, canvas_factory=lambda: canvas)
    qtbot.addWidget(view)
    view.resize(900, 650)
    view.show()

    assert view.hand_selector.currentData() == "left"
    assert view.punch_selector.currentData() == 1
    assert "左手" in view.summary.text()
    assert canvas.cameras[-1][0] == "user"
    assert "X 向右" in view.legend.text()
    assert "綠點為起點" in view.legend.text()
    assert "估算相對軌跡" in view.legend.text()

    view.punch_selector.setCurrentIndex(1)
    assert "第 2 拳" in view.summary.text()
    assert canvas.shown[-1]["punch_index"] == 2
    assert source == original


@pytest.mark.scenario("punch-trajectory-analysis", "user 操作 3D 圖")
@pytest.mark.scenario("desktop-ui-design", "user 只使用鍵盤操作視角")
def test_camera_presets_are_keyboard_focusable_and_do_not_change_result(qtbot) -> None:
    source = result()
    original = deepcopy(source)
    canvas = FakeCanvas()
    view = TrajectoryResultView(source, canvas_factory=lambda: canvas)
    qtbot.addWidget(view)
    for preset in ("side", "top", "user", "reset"):
        button = view.camera_buttons[preset]
        assert button.focusPolicy().value != 0
        button.click()
    assert [item[0] for item in canvas.cameras[-4:]] == ["side", "top", "user", "user"]
    assert source == original


@pytest.mark.scenario("desktop-ui-design", "電腦無法建立 3D 繪圖環境")
def test_opengl_failure_uses_text_fallback_without_losing_summary(qtbot) -> None:
    def fail():
        raise RuntimeError("forced OpenGL failure")

    view = TrajectoryResultView(result(), canvas_factory=fail)
    qtbot.addWidget(view)
    view.show()
    assert "無法建立互動式 3D 圖" in view.fallback_label.text()
    assert "路徑長度" in view.summary.text()


@pytest.mark.scenario("punch-trajectory-analysis", "正式資料沒有偵測到出拳")
def test_empty_result_explains_that_no_punch_was_detected(qtbot) -> None:
    payload = result()
    payload.update(left_punch_count=0, right_punch_count=0, total_punch_count=0, trajectories=[])
    view = TrajectoryResultView(payload, canvas_factory=FakeCanvas)
    qtbot.addWidget(view)
    assert "沒有偵測到" in view.summary.text()
