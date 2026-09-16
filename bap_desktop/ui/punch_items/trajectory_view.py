"""Interactive, local-only 3D presentation of a trajectory Analysis Result."""

from __future__ import annotations

from copy import deepcopy
import logging
import math
from typing import Callable

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class MatplotlibTrajectoryCanvas:
    """Embed a Matplotlib 3D figure without changing the Backend Result."""

    def __init__(self) -> None:
        # BAP uses DEBUG logs during local development. Matplotlib's font
        # discovery emits hundreds of internal lines at that level, so keep
        # the application log focused on actionable messages.
        logging.getLogger("matplotlib").setLevel(logging.WARNING)
        from matplotlib.backends.backend_qtagg import (
            FigureCanvasQTAgg,
            NavigationToolbar2QT,
        )
        from matplotlib.figure import Figure

        self.widget = QWidget()
        self.widget.setAccessibleName("內嵌 Matplotlib 3D 出拳軌跡")
        widget_layout = QVBoxLayout(self.widget)
        widget_layout.setContentsMargins(0, 0, 0, 0)
        widget_layout.setSpacing(4)

        self.figure = Figure(figsize=(7.0, 5.0), layout="constrained")
        self.figure.set_facecolor("#f8f9fa")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setAccessibleName("可旋轉、縮放與平移的 3D 出拳軌跡")
        self.canvas.setMinimumHeight(300)
        self.toolbar = NavigationToolbar2QT(self.canvas, self.widget)
        self.toolbar.setAccessibleName("3D 軌跡操作工具列")
        widget_layout.addWidget(self.toolbar)
        widget_layout.addWidget(self.canvas, 1)

        self.axes = self.figure.add_subplot(111, projection="3d")
        self._positions: tuple[tuple[float, float, float], ...] = ()

    def show_trajectory(self, trajectory: dict) -> None:
        self._positions = tuple(
            (float(point["x_m"]), float(point["y_m"]), float(point["z_m"]))
            for point in trajectory["points"]
        )
        x_values, y_values, z_values = zip(*self._positions, strict=True)
        color = "#d62e40" if trajectory["hand"] == "left" else "#2666cc"

        self.axes.clear()
        self.axes.plot(
            x_values,
            y_values,
            z_values,
            color=color,
            linewidth=2.4,
            marker="o",
            markersize=2.5,
            label="Trajectory",
        )
        self.axes.scatter(
            *self._positions[0], color="#1aa653", s=55, depthshade=False, label="Start"
        )
        self.axes.scatter(
            *self._positions[-1], color="#e63d2e", s=65, depthshade=False, label="End"
        )
        largest_span = max(
            max(values) - min(values)
            for values in zip(*self._positions, strict=True)
        )
        direction_length = max(0.05, largest_span * 0.35)
        for direction, color in (
            ((1.0, 0.0, 0.0), "#d62e40"),
            ((0.0, 1.0, 0.0), "#1aa653"),
            ((0.0, 0.0, 1.0), "#2666cc"),
        ):
            self.axes.quiver(
                0.0,
                0.0,
                0.0,
                *direction,
                length=direction_length,
                color=color,
                arrow_length_ratio=0.15,
            )
        self.axes.set_title("3D Punch Trajectory")
        self.axes.set_xlabel("X / right (m)")
        self.axes.set_ylabel("Y / forward (m)")
        self.axes.set_zlabel("Z / up (m)")
        self.axes.grid(True)
        self.axes.legend(loc="upper right")
        self.axes.set_box_aspect((1.0, 1.0, 1.0))
        self._fit_limits(1.0)
        self.canvas.draw_idle()

    def _fit_limits(self, distance: float) -> None:
        if not self._positions:
            return
        axes_values = tuple(zip(*self._positions, strict=True))
        centers = tuple((min(values) + max(values)) / 2.0 for values in axes_values)
        largest_span = max(max(values) - min(values) for values in axes_values)
        radius = max(0.05, largest_span * 0.60, float(distance) / 5.0)
        self.axes.set_xlim(centers[0] - radius, centers[0] + radius)
        self.axes.set_ylim(centers[1] - radius, centers[1] + radius)
        self.axes.set_zlim(centers[2] - radius, centers[2] + radius)

    def set_camera(self, preset: str, distance: float) -> None:
        # Azimuth -90 places the camera behind the user on -Y, looking toward
        # the +Y punch direction. Z remains upward.
        cameras = {
            "user": (8.0, -90.0),
            "side": (8.0, 0.0),
            "top": (90.0, -90.0),
        }
        elevation, azimuth = cameras[preset]
        self._fit_limits(distance)
        self.axes.view_init(elev=elevation, azim=azimuth, roll=0.0)
        self.canvas.draw_idle()


class TrajectoryResultView(QWidget):
    """Selectors, summary, camera presets, and a Matplotlib-safe fallback."""

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

        warnings = list(self.result.get("warnings", ()))
        quality = QLabel("資料品質：需要注意" if warnings else "資料品質：有效")
        quality.setObjectName("warningMessage" if warnings else "statusChip")
        quality.setWordWrap(True)
        layout.addWidget(quality)
        for warning in warnings:
            warning_label = QLabel(f"• {warning}")
            warning_label.setObjectName("warningMessage")
            warning_label.setWordWrap(True)
            layout.addWidget(warning_label)

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
            self._canvas = (canvas_factory or MatplotlibTrajectoryCanvas)()
            layout.addWidget(self._canvas.widget, 1)
        except Exception:
            fallback = QLabel(
                "此電腦目前無法載入內嵌 Matplotlib 3D 圖；分析結果仍已保留，"
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
