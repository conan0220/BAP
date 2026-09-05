"""Authenticated navigation shell shared by all BAP feature pages."""

from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from bap_desktop.resources import text


class AppShell(QWidget):
    home_requested = Signal()
    diagnostics_requested = Signal()
    punch_item_requested = Signal(str)
    logout_requested = Signal()

    def __init__(self, home_page: QWidget, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("authenticatedShell")
        self.home_page = home_page
        self._feature_page: QWidget | None = None
        self.nav_buttons: dict[str, QPushButton] = {}

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(224)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 20, 14, 16)
        sidebar_layout.setSpacing(6)

        brand_mark = QLabel("BAP")
        brand_mark.setObjectName("brandMark")
        brand_mark.setAccessibleName("BAP")
        brand_title = QLabel("Boxing Analysis")
        brand_title.setObjectName("brandTitle")
        brand_subtitle = QLabel("精準掌握每一次出拳")
        brand_subtitle.setObjectName("brandSubtitle")
        sidebar_layout.addWidget(brand_mark, 0)
        sidebar_layout.addWidget(brand_title)
        sidebar_layout.addWidget(brand_subtitle)
        sidebar_layout.addSpacing(18)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self._add_section_label(sidebar_layout, "工作區")
        home_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        refresh_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        self._add_nav_button(sidebar_layout, "home", "總覽", home_icon, self.home_requested.emit)
        self._add_nav_button(
            sidebar_layout,
            "diagnostics",
            text.IMU_DIAGNOSTICS,
            refresh_icon,
            self.diagnostics_requested.emit,
        )

        self._add_section_label(sidebar_layout, "拳擊分析")
        item_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        for item_name in text.PUNCH_ITEMS:
            self._add_nav_button(
                sidebar_layout,
                f"punch:{item_name}",
                item_name,
                item_icon,
                lambda name=item_name: self.punch_item_requested.emit(name),
            )
        sidebar_layout.addStretch(1)
        self.server_status = QLabel(text.SERVER_CONNECTED)
        self.server_status.setObjectName("brandSubtitle")
        self.server_status.setAccessibleName(f"服務狀態：{text.SERVER_CONNECTED}")
        sidebar_layout.addWidget(self.server_status)
        self.logout_button = QPushButton(text.LOGOUT)
        self.logout_button.setProperty("nav", True)
        self.logout_button.setAccessibleName("登出目前帳號")
        self.logout_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCloseButton))
        self.logout_button.clicked.connect(self.logout_requested.emit)
        sidebar_layout.addWidget(self.logout_button)

        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(24, 10, 24, 10)
        self.page_name = QLabel("總覽")
        self.page_name.setObjectName("pageName")
        self.page_name.setAccessibleName("目前頁面：總覽")
        self.account_label = QLabel("一般使用者")
        self.account_label.setProperty("muted", True)
        self.account_label.setAccessibleName("目前登入帳號：一般使用者")
        top_layout.addWidget(self.page_name)
        top_layout.addStretch(1)
        top_layout.addWidget(self.account_label)

        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self.home_page)
        content_scroll = QScrollArea()
        content_scroll.setObjectName("contentScroll")
        content_scroll.setWidgetResizable(True)
        content_scroll.setWidget(self.content_stack)

        body = QWidget()
        body.setObjectName("appRoot")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(top_bar)
        body_layout.addWidget(content_scroll, 1)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(sidebar)
        root.addWidget(body, 1)
        self.show_home()

    @staticmethod
    def _add_section_label(layout: QVBoxLayout, label: str) -> None:
        heading = QLabel(label)
        heading.setObjectName("brandSubtitle")
        layout.addWidget(heading)

    def _add_nav_button(self, layout, key, label, icon, callback) -> None:
        button = QPushButton(label)
        button.setCheckable(True)
        button.setProperty("nav", True)
        button.setAccessibleName(f"前往{label}")
        button.setIcon(icon)
        button.clicked.connect(lambda _checked=False, action=callback: action())
        self.nav_group.addButton(button)
        self.nav_buttons[key] = button
        layout.addWidget(button)

    def set_account_name(self, username: str | None) -> None:
        display = username or "一般使用者"
        self.account_label.setText(display)
        self.account_label.setAccessibleName(f"目前登入帳號：{display}")

    @Slot()
    def show_home(self) -> None:
        self.content_stack.setCurrentWidget(self.home_page)
        self._set_current("home", "總覽")

    def set_feature(self, page: QWidget, *, key: str, title: str) -> None:
        self.remove_feature()
        self._feature_page = page
        self.content_stack.addWidget(page)
        self.content_stack.setCurrentWidget(page)
        self._set_current(key, title)

    def remove_feature(self) -> QWidget | None:
        page = self._feature_page
        if page is not None:
            self.content_stack.removeWidget(page)
            page.setParent(None)
        self._feature_page = None
        return page

    def _set_current(self, key: str, title: str) -> None:
        button = self.nav_buttons.get(key)
        if button is not None:
            button.setChecked(True)
        self.page_name.setText(title)
        self.page_name.setAccessibleName(f"目前頁面：{title}")
