"""Authenticated home page with one entry per available feature."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from bap_desktop.resources import text
from bap_desktop.ui.components import Card, PageHeader


class HomePage(QWidget):
    open_diagnostics = Signal()
    open_punch_item = Signal(str)
    logout_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.diagnostics_button = QPushButton(text.IMU_DIAGNOSTICS)
        self.diagnostics_button.setProperty("role", "primary")
        self.diagnostics_button.setAccessibleName("開始 IMU 連線測試")
        self.logout_button = QPushButton(text.LOGOUT)
        self.logout_button.setVisible(False)
        self.punch_buttons: dict[str, QPushButton] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 28)
        layout.setSpacing(18)
        layout.addWidget(PageHeader("午安", "先確認 IMU 狀態，再開始你的拳擊分析。"))

        diagnostic_card = Card()
        self.diagnostic_layout = QGridLayout(diagnostic_card)
        self.diagnostic_title = QLabel("確認 IMU 連線狀態")
        self.diagnostic_title.setObjectName("sectionTitle")
        self.diagnostic_description = QLabel("自動掃描所有 Port，錄製五秒資料並檢查連線與取樣率。")
        self.diagnostic_description.setProperty("muted", True)
        self.diagnostic_description.setWordWrap(True)
        self.diagnostic_layout.addWidget(self.diagnostic_title, 0, 0)
        self.diagnostic_layout.addWidget(self.diagnostic_description, 1, 0)
        self.diagnostic_layout.addWidget(self.diagnostics_button, 0, 1, 2, 1)
        self.diagnostic_layout.setColumnStretch(0, 1)
        layout.addWidget(diagnostic_card)

        section = QLabel("拳擊分析項目")
        section.setObjectName("sectionTitle")
        layout.addWidget(section)
        self.punch_grid = QGridLayout()
        self.punch_grid.setSpacing(12)
        descriptions = {
            "出拳次數": "指定左、右手腕各自使用的 IMU。",
            "出拳速度": "指定左、右手腕各自使用的 IMU。",
            "出拳力量": "所需 IMU 數量與安裝位置待決定。",
            "出拳軌跡": "指定左、右手腕各自使用的 IMU。",
            "拳種辨識": "指定持把人左右手把背面的 IMU。",
        }
        for index, item_name in enumerate(text.PUNCH_ITEMS):
            button = QPushButton(f"{item_name}\n{text.PENDING}｜{descriptions[item_name]}")
            button.setProperty("role", "card")
            button.setAccessibleName(f"{item_name}，{text.PENDING}")
            button.clicked.connect(lambda _checked=False, name=item_name: self.open_punch_item.emit(name))
            self.punch_buttons[item_name] = button
            self.punch_grid.addWidget(button, index // 3, index % 3)
        layout.addLayout(self.punch_grid)
        layout.addStretch(1)

        self.punch_column_count = 3
        self._compact_diagnostic = False
        self._reflow(self.width())

        self.diagnostics_button.clicked.connect(self.open_diagnostics)
        self.logout_button.clicked.connect(self.logout_requested)

    def resizeEvent(self, event) -> None:
        self._reflow(event.size().width())
        super().resizeEvent(event)

    def _reflow(self, width: int) -> None:
        """Rearrange dashboard cards instead of squeezing them to fixed columns."""

        content_width = max(0, width - 56)
        columns = 1 if content_width < 700 else 2 if content_width < 1_000 else 3
        if columns != self.punch_column_count:
            self.punch_column_count = columns
            for button in self.punch_buttons.values():
                self.punch_grid.removeWidget(button)
            for index, button in enumerate(self.punch_buttons.values()):
                self.punch_grid.addWidget(button, index // columns, index % columns)
            for column in range(3):
                self.punch_grid.setColumnStretch(column, 1 if column < columns else 0)

        compact_diagnostic = content_width < 700
        if compact_diagnostic != self._compact_diagnostic:
            self._compact_diagnostic = compact_diagnostic
            if compact_diagnostic:
                self.diagnostic_layout.addWidget(self.diagnostics_button, 2, 0)
            else:
                self.diagnostic_layout.addWidget(self.diagnostics_button, 0, 1, 2, 1)
