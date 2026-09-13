"""Interactive, local-only 3D presentation of a trajectory Analysis Result."""

from __future__ import annotations

from copy import deepcopy
import math
from typing import Callable

from PySide6.QtGui import QVector3D
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class PyqtgraphTrajectoryCanvas:
    """Small adapter that keeps pyqtgraph/OpenGL details out of the page."""

    def __init__(self) -> None:
        import numpy as np
        import pyqtgraph.opengl as gl

        self._np = np
        self._gl = gl
        self.widget = gl.GLViewWidget()
        self.widget.setAccessibleName("互動式 3D 出拳軌跡")
        self.widget.setMinimumHeight(300)
        self.widget.setBackgroundColor((248, 249, 250, 255))
        self._trajectory_items: list[object] = []

        grid = gl.GLGridItem()
        grid.setSize(2.0, 2.0)
        grid.setSpacing(0.1, 0.1)
        self.widget.addItem(grid)
        self._add_axes()

    def _add_axes(self) -> None:
        gl, np = self._gl, self._np
        for endpoint, color in (
            ((0.35, 0.0, 0.0), (0.85, 0.18, 0.22, 1.0)),
            ((0.0, 0.35, 0.0), (0.15, 0.65, 0.30, 1.0)),
            ((0.0, 0.0, 0.35), (0.20, 0.35, 0.85, 1.0)),
        ):
            item = gl.GLLinePlotItem(
                pos=np.array(((0.0, 0.0, 0.0), endpoint), dtype=float),
                color=color,
                width=2,
                antialias=True,
            )
            self.widget.addItem(item)

    def show_trajectory(self, trajectory: dict) -> None:
        for item in self._trajectory_items:
            self.widget.removeItem(item)
        self._trajectory_items.clear()
        positions = self._np.array(
            [(point["x_m"], point["y_m"], point["z_m"]) for point in trajectory["points"]],
            dtype=float,
        )
        color = (0.86, 0.18, 0.25, 1.0) if trajectory["hand"] == "left" else (0.15, 0.40, 0.85, 1.0)
        line = self._gl.GLLinePlotItem(pos=positions, color=color, width=4, antialias=True)
        endpoints = self._gl.GLScatterPlotItem(
            pos=positions[[0, -1]],
            color=self._np.array(((0.10, 0.65, 0.30, 1.0), (0.90, 0.25, 0.18, 1.0))),
            size=self._np.array((9.0, 11.0)),
            pxMode=True,
        )
        self.widget.addItem(line)
        self.widget.addItem(endpoints)
        self._trajectory_items.extend((line, endpoints))

    def set_camera(self, preset: str, distance: float) -> None:
        # pyqtgraph uses azimuth -90 degrees for a camera located behind the
        # user on -Y, looking toward the +Y punch direction.  Z stays upward.
        cameras = {
            "user": (8.0, -90.0),
            "side": (8.0, 0.0),
            "top": (90.0, -90.0),
        }
        elevation, azimuth = cameras[preset]
        self.widget.setCameraPosition(
            pos=QVector3D(0.0, 0.0, 0.0),
            distance=distance,
            elevation=elevation,
            azimuth=azimuth,
        )


class TrajectoryResultView(QWidget):
    """Selectors, summary, camera presets, and an OpenGL-safe fallback."""

    def __init__(
        self,
        result: dict,
        *,
        canvas_factory: Callable[[], object] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.result = deepcopy(result)
        self._trajectories = tuple(self.result.get("trajectories", ()))
        self._canvas = None
        self._camera_preset = "user"
        self._camera_distance = 1.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        total = int(self.result.get("total_punch_count", 0))
        counts = QLabel(
            f"總拳數：{total}｜左手：{int(self.result.get('left_punch_count', 0))}｜"
            f"右手：{int(self.result.get('right_punch_count', 0))}"
        )
        counts.setObjectName("sectionTitle")
        counts.setWordWrap(True)
        layout.addWidget(counts)

        if not self._trajectories:
            empty = QLabel("本次測量沒有偵測到可顯示的出拳軌跡。")
            empty.setWordWrap(True)
            empty.setAccessibleName("沒有偵測到出拳軌跡")
            layout.addWidget(empty)
            self.summary = empty
            return

        selectors = QHBoxLayout()
        hand_label = QLabel("手別")
        self.hand_selector = QComboBox()
        self.hand_selector.setAccessibleName("選擇要查看的手別")
        hands = [hand for hand in ("left", "right") if any(item["hand"] == hand for item in self._trajectories)]
        for hand in hands:
            self.hand_selector.addItem("左手" if hand == "left" else "右手", hand)
        punch_label = QLabel("拳次")
        self.punch_selector = QComboBox()
        self.punch_selector.setAccessibleName("選擇要查看的拳次")
        hand_label.setBuddy(self.hand_selector)
        punch_label.setBuddy(self.punch_selector)
        selectors.addWidget(hand_label)
        selectors.addWidget(self.hand_selector)
        selectors.addWidget(punch_label)
        selectors.addWidget(self.punch_selector)
        selectors.addStretch(1)
        layout.addLayout(selectors)

        camera = QHBoxLayout()
        camera.addWidget(QLabel("視角"))
        self.camera_buttons: dict[str, QPushButton] = {}
        for preset, label in (
            ("user", "使用者視角"),
            ("side", "側面"),
            ("top", "上方"),
            ("reset", "重設縮放"),
        ):
            button = QPushButton(label)
            button.setProperty("role", "secondary")
            button.setAccessibleName(f"3D 軌跡{label}")
            button.clicked.connect(lambda _checked=False, value=preset: self.apply_camera_preset(value))
            camera.addWidget(button)
            self.camera_buttons[preset] = button
        camera.addStretch(1)
        layout.addLayout(camera)

        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        self.summary.setAccessibleName("所選出拳軌跡摘要")
        layout.addWidget(self.summary)

        self.legend = QLabel(
            "方向：X 向右（紅色軸）｜Y 向前（綠色軸）｜Z 向上（藍色軸）｜"
            "綠點為起點｜紅點為終點。這是每一拳從原點開始的估算相對軌跡，"
            "不是絕對位置量測。"
        )
        self.legend.setWordWrap(True)
        self.legend.setAccessibleName("3D 軌跡方向與起終點圖例")
        layout.addWidget(self.legend)

        try:
            self._canvas = (canvas_factory or PyqtgraphTrajectoryCanvas)()
            layout.addWidget(self._canvas.widget, 1)
        except Exception:
            fallback = QLabel(
                "此電腦目前無法建立互動式 3D 圖；分析結果仍已保留，"
                "你可以查看下方的軌跡摘要或重新測量。"
            )
            fallback.setObjectName("warningMessage")
            fallback.setWordWrap(True)
            fallback.setAccessibleName("3D 軌跡文字替代畫面")
            layout.addWidget(fallback)
            self.fallback_label = fallback

        self.hand_selector.currentIndexChanged.connect(self._hand_changed)
        self.punch_selector.currentIndexChanged.connect(self._selection_changed)
        earliest = min(self._trajectories, key=lambda item: (item["start_elapsed_us"], item["hand"]))
        self.hand_selector.setCurrentIndex(self.hand_selector.findData(earliest["hand"]))
        self._populate_punches(selected_index=int(earliest["punch_index"]))
        QWidget.setTabOrder(self.hand_selector, self.punch_selector)
        previous: QWidget = self.punch_selector
        for button in self.camera_buttons.values():
            QWidget.setTabOrder(previous, button)
            previous = button

    @property
    def camera_state(self) -> tuple[str, float]:
        return self._camera_preset, self._camera_distance

    def selected_trajectory(self) -> dict:
        hand = self.hand_selector.currentData()
        punch_index = self.punch_selector.currentData()
        return next(
            item for item in self._trajectories
            if item["hand"] == hand and item["punch_index"] == punch_index
        )

    def _hand_changed(self) -> None:
        self._populate_punches()

    def _populate_punches(self, *, selected_index: int | None = None) -> None:
        hand = self.hand_selector.currentData()
        self.punch_selector.blockSignals(True)
        self.punch_selector.clear()
        for item in self._trajectories:
            if item["hand"] == hand:
                self.punch_selector.addItem(f"第 {item['punch_index']} 拳", item["punch_index"])
        if selected_index is not None:
            found = self.punch_selector.findData(selected_index)
            if found >= 0:
                self.punch_selector.setCurrentIndex(found)
        self.punch_selector.blockSignals(False)
        self._selection_changed()

    def _selection_changed(self) -> None:
        if self.punch_selector.currentIndex() < 0:
            return
        trajectory = self.selected_trajectory()
        hand = "左手" if trajectory["hand"] == "left" else "右手"
        self.summary.setText(
            f"{hand}｜第 {trajectory['punch_index']} 拳｜"
            f"持續 {float(trajectory['duration_seconds']):.3f} 秒｜"
            f"路徑長度 {float(trajectory['path_length_m']):.3f} m｜"
            f"最大位移 {float(trajectory['maximum_displacement_m']):.3f} m"
        )
        self._camera_distance = self._distance_for(trajectory)
        if self._canvas is not None:
            self._canvas.show_trajectory(trajectory)
            self._canvas.set_camera(self._camera_preset, self._camera_distance)

    @staticmethod
    def _distance_for(trajectory: dict) -> float:
        points = trajectory["points"]
        spans = [
            max(float(point[axis]) for point in points) - min(float(point[axis]) for point in points)
            for axis in ("x_m", "y_m", "z_m")
        ]
        return max(0.5, math.sqrt(sum(span * span for span in spans)) * 2.5)

    def apply_camera_preset(self, preset: str) -> None:
        if preset == "reset":
            preset = self._camera_preset
        else:
            self._camera_preset = preset
        trajectory = self.selected_trajectory()
        self._camera_distance = self._distance_for(trajectory)
        if self._canvas is not None:
            self._canvas.set_camera(preset, self._camera_distance)
