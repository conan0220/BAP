from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget

from bap_desktop.ui.punch_items.trajectory_view import (
    MatplotlibTrajectoryCanvas,
    TrajectoryResultView,
    trajectory_limits,
)


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
        "algorithm_version": "trajectory_rule_v2",
        "coordinate_system": "session_local_x_right_y_forward_z_up",
        "distance_unit": "m",
        "left_punch_count": 2,
        "right_punch_count": 1,
        "total_punch_count": 3,
        "quality_status": "valid",
        "warnings": [],
        "trajectories": trajectories,
    }


class FakeCanvas:
    def __init__(self):
        self.widget = QWidget()
        self.shown = []
        self.cameras = []
        self.comparisons = []

    def configure_result(self, trajectories):
        self.reference = trajectories

    def show_trajectories(self, trajectories, *, side_by_side=False):
        self.comparisons.append((trajectories, side_by_side))

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


@pytest.mark.scenario("punch-trajectory-analysis", "校正期間姿態不穩定")
def test_view_shows_calibration_warning_without_hiding_trajectory(qtbot) -> None:
    payload = result()
    payload["quality_status"] = "warning"
    payload["warnings"] = ["校正期間偵測到明顯動作，本次軌跡可能有較大漂移。"]
    canvas = FakeCanvas()
    view = TrajectoryResultView(payload, canvas_factory=lambda: canvas)
    qtbot.addWidget(view)
    visible = " ".join(label.text() for label in view.findChildren(QLabel))
    assert "資料品質：需要注意" in visible
    assert "校正期間偵測到明顯動作" in visible
    assert canvas.shown


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
def test_matplotlib_failure_uses_text_fallback_without_losing_summary(qtbot) -> None:
    def fail():
        raise RuntimeError("forced Matplotlib failure")

    view = TrajectoryResultView(result(), canvas_factory=fail)
    qtbot.addWidget(view)
    view.show()
    assert "無法載入內嵌 Matplotlib 3D 圖" in view.fallback_label.text()
    assert "路徑長度" in view.summary.text()


@pytest.mark.scenario("punch-trajectory-analysis", "首次顯示有效軌跡 Result")
def test_real_matplotlib_canvas_embeds_3d_trajectory(qtbot) -> None:
    canvas = MatplotlibTrajectoryCanvas()
    qtbot.addWidget(canvas.widget)
    canvas.show_trajectory(trajectory("left", 1, 1_000_000))
    canvas.set_camera("user", 0.8)

    assert canvas.axes.name == "3d"
    assert canvas.axes.get_xlabel() == "X / right (m)"
    assert canvas.axes.get_ylabel() == "Y / forward (m)"
    assert canvas.axes.get_zlabel() == "Z / up (m)"
    assert len(canvas.axes.lines) == 1
    assert round(float(canvas.axes.azim)) == -90


@pytest.mark.scenario("punch-trajectory-analysis", "正式資料沒有偵測到出拳")
def test_empty_result_explains_that_no_punch_was_detected(qtbot) -> None:
    payload = result()
    payload.update(left_punch_count=0, right_punch_count=0, total_punch_count=0, trajectories=[])
    view = TrajectoryResultView(payload, canvas_factory=FakeCanvas)
    qtbot.addWidget(view)
    assert "沒有偵測到" in view.summary.text()


@pytest.mark.scenario("punch-trajectory-analysis", "Compare a selected subset across hands")
def test_checking_punches_compares_across_hands_and_preserves_selection(qtbot) -> None:
    source = result()
    original = deepcopy(source)
    canvas = FakeCanvas()
    view = TrajectoryResultView(source, canvas_factory=lambda: canvas)
    qtbot.addWidget(view)
    view.display_mode.setCurrentIndex(view.display_mode.findData("overlay"))
    view.punch_checks.topLevelItem(1).setCheckState(0, Qt.CheckState.Checked)
    assert [(t["hand"], t["punch_index"]) for t in canvas.comparisons[-1][0]] == [
        ("left", 1), ("right", 1),
    ]
    assert "已選 2 拳" in view.summary.text()
    assert not canvas.comparisons[-1][1]

    view.display_mode.setCurrentIndex(view.display_mode.findData("grid"))
    assert canvas.comparisons[-1][1]
    assert len(canvas.comparisons[-1][0]) == 2
    view.display_mode.setCurrentIndex(view.display_mode.findData("single"))
    view.punch_selector.setCurrentIndex(1)
    assert canvas.shown[-1]["punch_index"] == 2
    view.display_mode.setCurrentIndex(view.display_mode.findData("overlay"))
    assert len(view.selected_trajectories()) == 2
    assert source == original
    assert view.result == original
    assert len(set(distance for _, distance in canvas.cameras)) == 1


@pytest.mark.parametrize("mode", ["overlay", "grid"])
@pytest.mark.scenario("punch-trajectory-analysis", "Clear comparison selection")
def test_select_all_and_clear_leave_no_stale_trajectories(qtbot, mode) -> None:
    view = TrajectoryResultView(result())
    qtbot.addWidget(view)
    view.display_mode.setCurrentIndex(view.display_mode.findData(mode))
    view.select_all_button.click()
    canvas = view._canvas
    assert len(view.selected_trajectories()) == 3
    assert sum(len(axes.lines) for axes in canvas.figure.axes) == 3
    view.clear_selection_button.click()
    assert view.selected_trajectories() == []
    assert "尚未選取" in view.summary.text()
    assert sum(len(axes.lines) for axes in canvas.figure.axes) == 0
    view.camera_buttons["reset"].click()
    view.punch_checks.topLevelItem(2).setCheckState(0, Qt.CheckState.Checked)
    assert sum(len(axes.lines) for axes in canvas.figure.axes) == 1


def axes_limits(axes):
    return axes.get_xlim(), axes.get_ylim(), axes.get_zlim()


@pytest.mark.scenario("punch-trajectory-analysis", "Compare punches with different extents")
def test_all_modes_keep_common_bounds_colors_and_equal_axis_scale(qtbot) -> None:
    payload = result()
    # Opposite-direction punches expose the clipping problem in a range based
    # only on the largest individual punch's span.
    for point in payload["trajectories"][0]["points"]:
        point["y_m"] *= -4
    original = deepcopy(payload)
    view = TrajectoryResultView(payload)
    qtbot.addWidget(view)
    canvas = view._canvas
    expected = axes_limits(canvas.axes)
    spans = [high - low for low, high in expected]
    assert spans == pytest.approx([spans[0]] * 3)
    for trajectory_data in payload["trajectories"]:
        for point in trajectory_data["points"]:
            for axis, (low, high) in zip(("x_m", "y_m", "z_m"), expected):
                assert low <= point[axis] <= high
    view.punch_selector.setCurrentIndex(1)
    assert axes_limits(canvas.axes) == expected
    view.display_mode.setCurrentIndex(view.display_mode.findData("overlay"))
    view.select_all_button.click()
    colors = {line.get_label(): line.get_color() for line in canvas.axes.lines}
    view.punch_checks.topLevelItem(0).setCheckState(0, Qt.CheckState.Unchecked)
    assert axes_limits(canvas.axes) == expected
    for line in canvas.axes.lines:
        assert line.get_color() == colors[line.get_label()]
    view.display_mode.setCurrentIndex(view.display_mode.findData("grid"))
    assert len(canvas.figure.axes) == 2
    for axes in canvas.figure.axes:
        assert axes_limits(axes) == expected
        assert axes.lines[0].get_color() == colors[axes.lines[0].get_label()]
    assert payload == original


@pytest.mark.scenario("punch-trajectory-analysis", "Manipulate side-by-side plots")
def test_grid_camera_rotation_zoom_and_reset_are_shared(qtbot) -> None:
    view = TrajectoryResultView(result())
    qtbot.addWidget(view)
    view.display_mode.setCurrentIndex(view.display_mode.findData("grid"))
    view.select_all_button.click()
    canvas = view._canvas
    expected = axes_limits(canvas.axes)
    source = canvas.figure.axes[1]
    source.view_init(elev=30, azim=45, roll=10)
    source.set_xlim(-0.1, 0.1)
    source.set_ylim(-0.1, 0.1)
    source.set_zlim(-0.1, 0.1)
    canvas._synchronize_camera(SimpleNamespace(inaxes=source))
    for axes in canvas.figure.axes:
        assert (axes.elev, axes.azim, axes.roll) == (30, 45, 10)
        assert axes_limits(axes) == axes_limits(source)
    view.camera_buttons["top"].click()
    view.camera_buttons["reset"].click()
    for axes in canvas.figure.axes:
        assert axes_limits(axes) == expected
        assert (axes.elev, axes.azim, axes.roll) == (90, -90, 0)


@pytest.mark.scenario("punch-trajectory-analysis", "Compare without a renderer")
def test_comparison_fallback_keeps_per_punch_metrics(qtbot) -> None:
    def fail():
        raise RuntimeError("no renderer")

    view = TrajectoryResultView(result(), canvas_factory=fail)
    qtbot.addWidget(view)
    view.display_mode.setCurrentIndex(view.display_mode.findData("grid"))
    view.select_all_button.click()
    assert "已選 3 拳" in view.summary.text()
    row = view.punch_checks.topLevelItem(2)
    assert [row.text(i) for i in range(1, 4)] == ["0.200", "0.800", "0.600"]
    view.clear_selection_button.click()
    view.camera_buttons["reset"].click()
    assert "尚未選取" in view.summary.text()


def test_stationary_points_have_nonzero_common_range() -> None:
    item = trajectory("left", 1, 0)
    for point in item["points"]:
        point.update(x_m=0, y_m=0, z_m=0)
    assert trajectory_limits([item]) == ((-0.05, 0.05),) * 3
