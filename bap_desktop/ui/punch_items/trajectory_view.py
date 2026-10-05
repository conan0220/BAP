"""Interactive, local-only 3D presentation of a trajectory Analysis Result."""

from __future__ import annotations

from copy import deepcopy
import logging
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


TRAJECTORY_COLORS = (
    "#2666cc", "#d62e40", "#16854a", "#ab6500", "#8646ae",
    "#00878a", "#bd347b", "#596773",
)


def trajectory_key(trajectory: dict) -> tuple[str, int]:
    return trajectory["hand"], trajectory["punch_index"]


def trajectory_limits(trajectories) -> tuple[tuple[float, float], ...]:
    # Include the origin and use the whole Result, so selecting a subset never
    # changes either the physical scale or the position of the coordinate frame.
    bounds = []
    for axis in ("x_m", "y_m", "z_m"):
        values = [0.0] + [float(p[axis]) for t in trajectories for p in t["points"]]
        bounds.append((min(values), max(values)))
    radius = max(0.05, max(high - low for low, high in bounds) * 0.60)
    return tuple(((low + high) / 2 - radius, (low + high) / 2 + radius) for low, high in bounds)


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
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setWidget(self.canvas)
        self.scroll.setMinimumHeight(320)
        widget_layout.addWidget(self.scroll, 1)

        self.axes = self.figure.add_subplot(111, projection="3d")
        self._limits = None
        self._styles = {}
        self.canvas.mpl_connect("button_release_event", self._synchronize_camera)

    def configure_result(self, trajectories) -> None:
        self._limits = trajectory_limits(trajectories)
        self._styles = {
            trajectory_key(item): (TRAJECTORY_COLORS[i % len(TRAJECTORY_COLORS)],
                                   ("-", "--", "-.", ":")[(i // len(TRAJECTORY_COLORS)) % 4])
            for i, item in enumerate(trajectories)
        }

    def show_trajectory(self, trajectory: dict) -> None:
        self.show_trajectories([trajectory])

    def show_trajectories(self, trajectories: list[dict], *, side_by_side: bool = False) -> None:
        if self._limits is None:
            self.configure_result(trajectories)
        self.figure.clear()
        columns = 2 if side_by_side and len(trajectories) > 1 else 1
        rows = (len(trajectories) + columns - 1) // columns if side_by_side else 1
        rows = max(1, rows)
        self.canvas.setMinimumHeight(380 * rows)
        groups = [[item] for item in trajectories] if side_by_side else [trajectories]
        for index, group in enumerate(groups or [[]]):
            axes = self.figure.add_subplot(rows, columns, index + 1, projection="3d")
            for trajectory in group:
                self._draw_trajectory(axes, trajectory)
            title = "3D Punch Trajectories"
            if side_by_side and group:
                title = self._label(group[0])
            self._finish_axes(axes, title)
        self.axes = self.figure.axes[0]
        self._fit_limits()
        self.toolbar.update()
        self.canvas.draw_idle()

    @staticmethod
    def _label(trajectory: dict) -> str:
        hand = "L" if trajectory["hand"] == "left" else "R"
        return f"{hand}{trajectory['punch_index']}"

    def _draw_trajectory(self, axes, trajectory: dict) -> None:
        positions = tuple(
            (float(point["x_m"]), float(point["y_m"]), float(point["z_m"]))
            for point in trajectory["points"]
        )
        x_values, y_values, z_values = zip(*positions, strict=True)
        color, linestyle = self._styles.get(trajectory_key(trajectory), (TRAJECTORY_COLORS[0], "-"))
        axes.plot(
            x_values,
            y_values,
            z_values,
            color=color,
            linestyle=linestyle,
            linewidth=2.4,
            marker="o",
            markersize=2.5,
            label=self._label(trajectory),
        )
        axes.scatter(
            *positions[0], color="#1aa653", s=45, depthshade=False,
            label="Start" if len(axes.lines) == 1 else "_nolegend_",
        )
        axes.scatter(
            *positions[-1], color=color, marker="^", s=55, depthshade=False,
        )

    def _finish_axes(self, axes, title: str) -> None:
        from matplotlib.ticker import MaxNLocator

        direction_length = (self._limits[0][1] - self._limits[0][0]) * 0.15
        for direction, color in (
            ((1.0, 0.0, 0.0), "#d62e40"),
            ((0.0, 1.0, 0.0), "#1aa653"),
            ((0.0, 0.0, 1.0), "#2666cc"),
        ):
            axes.quiver(
                0.0,
                0.0,
                0.0,
                *direction,
                length=direction_length,
                color=color,
                arrow_length_ratio=0.15,
            )
        axes.set_title(title, fontsize=11)
        axes.set_xlabel("X / right (m)", fontsize=9, labelpad=6)
        axes.set_ylabel("Y / forward (m)", fontsize=9, labelpad=6)
        axes.set_zlabel("Z / up (m)", fontsize=9, labelpad=6)
        for axis in (axes.xaxis, axes.yaxis, axes.zaxis):
            axis.set_major_locator(MaxNLocator(nbins=3))
        axes.tick_params(labelsize=8, pad=2)
        axes.grid(True)
        # The scrollable selection table is the full legend for large selections.
        if 0 < len(axes.lines) <= 8:
            axes.legend(loc="upper right", fontsize="small")
        axes.set_box_aspect((1.0, 1.0, 1.0))
        axes.set_proj_type("ortho")

    def _fit_limits(self) -> None:
        if self._limits is None:
            return
        for axes in self.figure.axes:
            axes.set_xlim(*self._limits[0])
            axes.set_ylim(*self._limits[1])
            axes.set_zlim(*self._limits[2])

    def _synchronize_camera(self, event) -> None:
        source = event.inaxes
        if source not in self.figure.axes or len(self.figure.axes) < 2:
            return
        for axes in self.figure.axes:
            if axes is not source:
                axes.view_init(elev=source.elev, azim=source.azim, roll=source.roll)
                axes.set_xlim(source.get_xlim())
                axes.set_ylim(source.get_ylim())
                axes.set_zlim(source.get_zlim())
        self.canvas.draw_idle()

    def set_camera(self, preset: str, distance: float) -> None:
        # Azimuth -90 places the camera behind the user on -Y, looking toward
        # the +Y punch direction. Z remains upward.
        cameras = {
            "user": (20.0, -90.0),
            "side": (20.0, 0.0),
            "top": (90.0, -90.0),
        }
        elevation, azimuth = cameras[preset]
        self._fit_limits()
        for axes in self.figure.axes:
            axes.view_init(elev=elevation, azim=azimuth, roll=0.0)
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
        self._trajectories = tuple(sorted(
            self.result.get("trajectories", ()),
            key=lambda item: (item["start_elapsed_us"], item["hand"], item["punch_index"]),
        ))
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

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("顯示"))
        self.display_mode = QComboBox()
        self.display_mode.setAccessibleName("軌跡顯示模式")
        for label, value in (("單拳", "single"), ("疊圖比較", "overlay"), ("並排比較", "grid")):
            self.display_mode.addItem(label, value)
        mode_row.addWidget(self.display_mode)
        limits = trajectory_limits(self._trajectories)
        self._camera_distance = (limits[0][1] - limits[0][0]) * 2.5
        scale = QLabel(f"共同範圍：每軸 {limits[0][1] - limits[0][0]:.3f} m")
        scale.setWordWrap(True)
        mode_row.addWidget(scale, 1)
        layout.addLayout(mode_row)

        self.single_selectors = QWidget()
        selectors = QHBoxLayout(self.single_selectors)
        selectors.setContentsMargins(0, 0, 0, 0)
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
        layout.addWidget(self.single_selectors)

        self.comparison_controls = QWidget()
        comparison = QVBoxLayout(self.comparison_controls)
        comparison.setContentsMargins(0, 0, 0, 0)
        self.punch_checks = QTreeWidget()
        self.punch_checks.setAccessibleName("勾選比較拳次")
        self.punch_checks.setHeaderLabels(["拳次", "持續 (s)", "路徑 (m)", "最大位移 (m)"])
        self.punch_checks.setRootIsDecorated(False)
        self.punch_checks.setUniformRowHeights(True)
        self.punch_checks.setMinimumHeight(110)
        self.punch_checks.setMaximumHeight(135)
        self.punch_checks.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.punch_checks.header().setStretchLastSection(True)
        for index, item in enumerate(self._trajectories):
            hand = "左手" if item["hand"] == "left" else "右手"
            row = QTreeWidgetItem([
                f"{hand} 第 {item['punch_index']} 拳 ({MatplotlibTrajectoryCanvas._label(item)})",
                f"{float(item['duration_seconds']):.3f}",
                f"{float(item['path_length_m']):.3f}",
                f"{float(item['maximum_displacement_m']):.3f}",
            ])
            row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            row.setCheckState(0, Qt.CheckState.Checked if index == 0 else Qt.CheckState.Unchecked)
            row.setData(0, Qt.ItemDataRole.UserRole, index)
            swatch = QPixmap(12, 12)
            swatch.fill(QColor(TRAJECTORY_COLORS[index % len(TRAJECTORY_COLORS)]))
            row.setIcon(0, QIcon(swatch))
            self.punch_checks.addTopLevelItem(row)
        comparison.addWidget(self.punch_checks)
        selection_actions = QHBoxLayout()
        self.select_all_button = QPushButton("全選")
        self.clear_selection_button = QPushButton("清除選取")
        self.select_all_button.clicked.connect(lambda: self._check_all(True))
        self.clear_selection_button.clicked.connect(lambda: self._check_all(False))
        selection_actions.addWidget(self.select_all_button)
        selection_actions.addWidget(self.clear_selection_button)
        selection_actions.addStretch(1)
        comparison.addLayout(selection_actions)
        layout.addWidget(self.comparison_controls)
        self.comparison_controls.hide()

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
            "綠點為起點｜同色三角形為終點。這是每一拳從原點開始的估算相對軌跡，"
            "不是絕對位置量測。"
        )
        self.legend.setWordWrap(True)
        self.legend.setAccessibleName("3D 軌跡方向與起終點圖例")
        layout.addWidget(self.legend)

        try:
            self._canvas = (canvas_factory or MatplotlibTrajectoryCanvas)()
            self._canvas.configure_result(self._trajectories)
            layout.addWidget(self._canvas.widget, 1)
        except Exception:
            self._canvas = None
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
        self.display_mode.currentIndexChanged.connect(self._mode_changed)
        self.punch_checks.itemChanged.connect(self._comparison_changed)
        earliest = min(self._trajectories, key=lambda item: (item["start_elapsed_us"], item["hand"]))
        self.hand_selector.setCurrentIndex(self.hand_selector.findData(earliest["hand"]))
        self._populate_punches(selected_index=int(earliest["punch_index"]))
        QWidget.setTabOrder(self.display_mode, self.hand_selector)
        QWidget.setTabOrder(self.hand_selector, self.punch_selector)
        QWidget.setTabOrder(self.punch_selector, self.punch_checks)
        QWidget.setTabOrder(self.punch_checks, self.select_all_button)
        QWidget.setTabOrder(self.select_all_button, self.clear_selection_button)
        previous: QWidget = self.clear_selection_button
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

    def selected_trajectories(self) -> list[dict]:
        if not self._trajectories:
            return []
        if self.display_mode.currentData() == "single":
            return [self.selected_trajectory()]
        return [
            self._trajectories[self.punch_checks.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole)]
            for i in range(self.punch_checks.topLevelItemCount())
            if self.punch_checks.topLevelItem(i).checkState(0) == Qt.CheckState.Checked
        ]

    def _mode_changed(self) -> None:
        single = self.display_mode.currentData() == "single"
        self.single_selectors.setVisible(single)
        self.comparison_controls.setVisible(not single)
        self._selection_changed()

    def _check_all(self, checked: bool) -> None:
        self.punch_checks.blockSignals(True)
        for i in range(self.punch_checks.topLevelItemCount()):
            self.punch_checks.topLevelItem(i).setCheckState(
                0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked,
            )
        self.punch_checks.blockSignals(False)
        self._comparison_changed()

    def _comparison_changed(self, *_args) -> None:
        if self.display_mode.currentData() != "single":
            self._selection_changed()

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
        if self.display_mode.currentData() != "single":
            trajectories = self.selected_trajectories()
            if trajectories:
                left = sum(item["hand"] == "left" for item in trajectories)
                self.summary.setText(
                    f"已選 {len(trajectories)} 拳｜左手 {left} 拳｜右手 {len(trajectories) - left} 拳"
                )
            else:
                self.summary.setText("尚未選取比較拳次。")
            if self._canvas is not None:
                self._canvas.show_trajectories(
                    trajectories, side_by_side=self.display_mode.currentData() == "grid",
                )
                self._canvas.set_camera(self._camera_preset, self._camera_distance)
            return
        trajectory = self.selected_trajectory()
        hand = "左手" if trajectory["hand"] == "left" else "右手"
        self.summary.setText(
            f"{hand}｜第 {trajectory['punch_index']} 拳｜"
            f"持續 {float(trajectory['duration_seconds']):.3f} 秒｜"
            f"路徑長度 {float(trajectory['path_length_m']):.3f} m｜"
            f"最大位移 {float(trajectory['maximum_displacement_m']):.3f} m"
        )
        if self._canvas is not None:
            self._canvas.show_trajectory(trajectory)
            self._canvas.set_camera(self._camera_preset, self._camera_distance)

    def apply_camera_preset(self, preset: str) -> None:
        if preset == "reset":
            preset = self._camera_preset
        else:
            self._camera_preset = preset
        if self._canvas is not None:
            self._canvas.set_camera(preset, self._camera_distance)
