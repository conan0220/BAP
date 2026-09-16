"""Readable, embedded presentation for a punch-force Analysis Result."""

from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class MatplotlibForceCanvas:
    def __init__(self, result: dict) -> None:
        logging.getLogger("matplotlib").setLevel(logging.WARNING)
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure

        self.widget = QWidget()
        self.widget.setAccessibleName("內嵌出拳力量曲線")
        layout = QVBoxLayout(self.widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.figure = Figure(figsize=(8.0, 7.0), layout="constrained")
        self.figure.set_facecolor("#f8f9fa")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setAccessibleName("沙袋加速度、角加速度與力量曲線")
        self.canvas.setMinimumHeight(440)
        layout.addWidget(self.canvas)

        points = result["curve_points"]
        origin = int(points[0]["elapsed_us"])
        time = [(int(point["elapsed_us"]) - origin) / 1_000_000 for point in points]
        axes = self.figure.subplots(3, 1, sharex=True)
        axes[0].plot(time, [point["top_horizontal_acceleration_mps2"] for point in points], label="Bag top")
        axes[0].plot(time, [point["bottom_horizontal_acceleration_mps2"] for point in points], label="Bag bottom")
        axes[0].set_ylabel("Acceleration (m/s²)")
        axes[0].legend(loc="upper right")
        axes[1].plot(time, [point["angular_acceleration_x_radps2"] for point in points], label="X")
        axes[1].plot(time, [point["angular_acceleration_y_radps2"] for point in points], label="Y")
        axes[1].set_ylabel("Angular acceleration (rad/s²)")
        axes[1].legend(loc="upper right")
        force = [point["force_kgf"] for point in points]
        axes[2].plot(time, force, color="#c72538", label="Estimated force")
        peak_elapsed = int(result["peak_elapsed_us"])
        peak_index = next(index for index, point in enumerate(points) if int(point["elapsed_us"]) == peak_elapsed)
        axes[2].scatter([time[peak_index]], [force[peak_index]], color="#c72538", zorder=3, label="Global maximum")
        axes[2].set_ylabel("Force (kgf)")
        axes[2].set_xlabel("Measurement elapsed time (s)")
        axes[2].legend(loc="upper right")
        for axis in axes:
            axis.grid(True, alpha=0.25)
        self.canvas.draw_idle()


class ForceResultView(QWidget):
    def __init__(
        self,
        result: dict,
        *,
        canvas_factory: Callable[[dict], object] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        summary = QLabel(
            f"最大打擊力：{float(result['peak_force_kgf']):.2f} kgf "
            f"（{float(result['peak_force_n']):.2f} N）"
        )
        summary.setObjectName("sectionTitle")
        summary.setWordWrap(True)
        summary.setAccessibleName("最大打擊力")
        layout.addWidget(summary)
        detail = QLabel(
            f"打擊位置：距沙袋底部 {float(result['impact_height_from_bottom_m']):.3f} m｜"
            f"相對中心 {float(result['impact_offset_from_center_m']):+.3f} m｜"
            f"峰值時間 {int(result['peak_elapsed_us']) / 1_000_000:.3f} 秒｜"
            f"質心加速度 {float(result['peak_com_acceleration_g']):.3f} g｜"
            f"取樣率 {float(result['sample_rate_hz']):.1f} Hz"
        )
        detail.setWordWrap(True)
        layout.addWidget(detail)

        estimate = QLabel("本結果是依 IMU 資料與沙袋物理模型得到的估算值，不是 Force Plate 的直接量測值。")
        estimate.setWordWrap(True)
        estimate.setAccessibleName("出拳力量估算限制")
        layout.addWidget(estimate)

        warnings = list(result.get("warnings", ()))
        quality = QLabel("資料品質：需要注意" if warnings else "資料品質：有效")
        quality.setObjectName("warningMessage" if warnings else "statusChip")
        quality.setWordWrap(True)
        layout.addWidget(quality)
        for warning in warnings:
            label = QLabel(f"• {warning}")
            label.setObjectName("warningMessage")
            label.setWordWrap(True)
            layout.addWidget(label)

        try:
            self._canvas = (canvas_factory or MatplotlibForceCanvas)(result)
            layout.addWidget(self._canvas.widget)
        except Exception:
            fallback = QLabel("此電腦目前無法載入內嵌曲線；數值結果與重新測量功能仍可使用。")
            fallback.setObjectName("warningMessage")
            fallback.setWordWrap(True)
            fallback.setAccessibleName("出拳力量曲線文字替代畫面")
            layout.addWidget(fallback)
            self.fallback_label = fallback
