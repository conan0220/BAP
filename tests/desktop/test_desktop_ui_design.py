from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QBoxLayout, QLabel, QScrollArea, QWidget

from bap_desktop.services.imu_diagnostics import (
    DiagnosticCsvFile,
    DiagnosticReport,
    DiagnosticReportRow,
)
from bap_desktop.services.imu_discovery import DiscoveryResult, ImuSource
from bap_desktop.services.imu_scan import ConnectionType
from bap_desktop.ui.auth import AuthPage
from bap_desktop.ui.components import PageHeader
from bap_desktop.ui.home import HomePage
from bap_desktop.ui.imu_diagnostics import ImuDiagnosticsPage
from bap_desktop.ui.main_window import MainWindow
from bap_desktop.ui.punch_items import PunchItemPage
from bap_desktop.ui.styles import BAP_STYLESHEET


class SessionStub:
    api = object()

    def __init__(self, restored: bool = True) -> None:
        self.restored = restored
        self.logged_out = False
        self.closed = False

    def restore(self) -> bool:
        return self.restored

    def logout(self) -> None:
        self.logged_out = True

    def close(self) -> None:
        self.closed = True


class DiscoveryStub:
    duration_seconds = 3.0

    def __init__(self, result: DiscoveryResult) -> None:
        self.result = result
        self.clear_count = 0

    def discover(self, *, cancel_event=None) -> DiscoveryResult:
        return self.result

    def clear(self) -> None:
        self.clear_count += 1


class DiagnosticsStub:
    duration_seconds = 5.0

    def cleanup(self) -> None:
        pass

    def export_csv(self, destination: Path) -> Path:
        return destination


SOURCES = (
    ImuSource("COM1", ConnectionType.WIRED),
    ImuSource("COM2", ConnectionType.WIRED),
    ImuSource("COM7", ConnectionType.WIRELESS_RECEIVER, group_id=3, node_id=8),
)


def make_punch_page(qtbot, item_name: str, sources=SOURCES) -> PunchItemPage:
    result = DiscoveryResult(tuple(sources), ())
    page = PunchItemPage(item_name, DiscoveryStub(result))  # type: ignore[arg-type]
    qtbot.addWidget(page)
    page._show_sources(result)
    return page


@pytest.mark.scenario("desktop-ui-design", "user 登入後查看主畫面")
@pytest.mark.scenario("desktop-ui-design", "user 切換功能頁面")
def test_authenticated_shell_shows_navigation_account_and_current_page(qtbot) -> None:
    session = SessionStub()
    window = MainWindow(session)  # type: ignore[arg-type]
    qtbot.addWidget(window)

    assert window.stack.currentWidget() is window.app_shell
    assert window.app_shell.logout_button.text() == "登出"
    assert set(window.app_shell.nav_buttons) >= {"home", "diagnostics"}
    window.app_shell.nav_buttons["punch:出拳速度"].click()
    assert window.app_shell.page_name.text() == "出拳速度"
    assert window.app_shell.nav_buttons["punch:出拳速度"].isChecked()
    assert window.app_shell.content_stack.currentWidget() is window._feature_page


@pytest.mark.scenario("desktop-ui-design", "使用鍵盤切換頁面")
def test_keyboard_can_activate_navigation_and_focus_is_visually_defined(qtbot) -> None:
    window = MainWindow(SessionStub())  # type: ignore[arg-type]
    qtbot.addWidget(window)
    window.show()
    button = window.app_shell.nav_buttons["diagnostics"]
    button.setFocus()
    qtbot.keyClick(button, Qt.Key.Key_Space)

    assert window.app_shell.page_name.text() == "IMU 連線狀態"
    assert "QPushButton:focus" in BAP_STYLESHEET
    assert "border: 2px solid" in BAP_STYLESHEET


@pytest.mark.scenario("desktop-ui-design", "顯示待開發項目")
@pytest.mark.scenario("desktop-app-shell", "查看拳擊測量項目")
def test_home_has_five_separate_pending_items_with_new_name(qtbot) -> None:
    window = MainWindow(SessionStub())  # type: ignore[arg-type]
    qtbot.addWidget(window)

    assert tuple(window.home_page.punch_buttons) == (
        "出拳次數",
        "出拳速度",
        "出拳力量",
        "出拳軌跡",
        "拳種辨識",
    )
    assert all("待開發" in button.text() for button in window.home_page.punch_buttons.values())
    assert not any("拳型辨識" in button.text() for button in window.home_page.punch_buttons.values())


@pytest.mark.scenario("desktop-app-shell", "進入單一拳擊項目")
def test_opening_one_item_keeps_exactly_one_feature_page(qtbot) -> None:
    window = MainWindow(
        SessionStub(),
        discovery_service_factory=lambda: DiscoveryStub(DiscoveryResult((), ())),
    )  # type: ignore[arg-type]
    qtbot.addWidget(window)

    window.show_punch_item("出拳次數")
    first = window._feature_page
    window.show_punch_item("出拳軌跡")

    assert first is not window._feature_page
    assert window.app_shell.content_stack.count() == 2
    assert window.app_shell.page_name.text() == "出拳軌跡"


@pytest.mark.scenario("desktop-ui-design", "IMU Report 已完成")
@pytest.mark.scenario("desktop-ui-design", "顯示 IMU 連線結果")
@pytest.mark.scenario("imu-connection-diagnostics", "多個 Port 有不同取樣率")
def test_diagnostics_report_keeps_per_port_rates_without_average(qtbot, tmp_path: Path) -> None:
    page = ImuDiagnosticsPage(DiagnosticsStub())  # type: ignore[arg-type]
    qtbot.addWidget(page)
    report = DiagnosticReport(
        rows=(
            DiagnosticReportRow("COM1", "ANROT", "有線連接", 921600, "—", 100.0, "已連線", ""),
            DiagnosticReportRow("COM2", "ANROT", "有線連接", 921600, "—", 400.0, "未連線", "沒有資料"),
        ),
        csv_files=(
            DiagnosticCsvFile("COM1", ConnectionType.WIRED, tmp_path / "imu.csv", 100),
        ),
    )
    page._show_report(report)

    visible_text = " ".join(label.text() for label in page.findChildren(QLabel))
    assert "平均取樣率" not in visible_text
    assert page.table.item(0, 5).text() == "100.0 Hz"
    assert page.table.item(1, 5).text() == "400.0 Hz"
    assert page.table.item(0, 6).text() == "已連線"
    assert page.table.item(1, 6).text() == "未連線"
    assert page.retest_button.property("role") == "primary"
    assert page.export_button.property("role") == "secondary"


@pytest.mark.scenario("imu-connection-diagnostics", "只有一個 Port 成功連線")
def test_single_connected_port_still_has_only_its_own_sample_rate(qtbot) -> None:
    page = ImuDiagnosticsPage(DiagnosticsStub())  # type: ignore[arg-type]
    qtbot.addWidget(page)
    page._show_report(
        DiagnosticReport(
            (DiagnosticReportRow("COM9", "ANROT", "有線連接", 921600, "—", 200.0, "已連線", ""),),
            (),
        )
    )

    assert page.connected_count_value.text() == "1"
    assert page.table.item(0, 5).text() == "200.0 Hz"
    assert "平均" not in " ".join(label.text() for label in page.findChildren(QLabel))


@pytest.mark.scenario("imu-source-discovery", "設定出拳次數的 IMU")
@pytest.mark.scenario("imu-source-discovery", "設定出拳速度的 IMU")
@pytest.mark.scenario("imu-source-discovery", "設定出拳軌跡的 IMU")
@pytest.mark.scenario("imu-source-discovery", "設定拳種辨識的 IMU")
def test_each_decided_item_builds_its_required_two_placement_fields(qtbot) -> None:
    expected = {
        "出拳次數": ("左手腕", "右手腕"),
        "出拳速度": ("左手腕", "右手腕"),
        "出拳軌跡": ("左手腕", "右手腕"),
        "拳種辨識": ("左手把背面", "右手把背面"),
    }
    for item_name, placement_names in expected.items():
        page = make_punch_page(qtbot, item_name)
        assert tuple(placement.name for placement in page._source_selectors.values()) == placement_names
        assert all(selector.count() == len(SOURCES) + 1 for selector in page._source_selectors)


@pytest.mark.scenario("desktop-ui-design", "IMU 尚未完成分配")
@pytest.mark.scenario("imu-source-discovery", "尚有位置未分配")
def test_incomplete_assignment_keeps_continue_disabled(qtbot) -> None:
    page = make_punch_page(qtbot, "出拳次數")
    first = list(page._source_selectors)[0]
    first.setCurrentIndex(1)

    assert not page.continue_button.isEnabled()
    assert "待開發" not in page.status.text()


@pytest.mark.scenario("imu-source-discovery", "user 將同一顆 IMU 分配給兩個位置")
def test_duplicate_assignment_is_rejected_with_text(qtbot) -> None:
    page = make_punch_page(qtbot, "出拳速度")
    first, second = page._source_selectors
    first.setCurrentIndex(1)
    second.setCurrentIndex(1)

    assert page.message.isVisibleTo(page)
    assert "不能同時" in page.message.text()
    assert not page.continue_button.isEnabled()


@pytest.mark.scenario("imu-source-discovery", "可用 IMU 少於項目需求")
def test_insufficient_sources_are_shown_but_cannot_continue(qtbot) -> None:
    page = make_punch_page(qtbot, "出拳軌跡", SOURCES[:1])

    assert "不足" in page.message.text()
    assert all(selector.count() == 2 for selector in page._source_selectors)
    assert not page.continue_button.isEnabled()


@pytest.mark.scenario("imu-source-discovery", "user 進入出拳力量")
def test_punch_force_explains_that_configuration_is_pending(qtbot) -> None:
    page = make_punch_page(qtbot, "出拳力量")

    assert "配置待決定" in page.status.text()
    assert len(page._source_selectors) == 0
    assert not page.continue_button.isEnabled()


@pytest.mark.scenario("imu-source-discovery", "完成所有必要位置的分配並繼續")
def test_valid_distinct_assignments_show_pending_and_clear_discovery(qtbot) -> None:
    page = make_punch_page(qtbot, "拳種辨識")
    first, second = page._source_selectors
    first.setCurrentIndex(1)
    second.setCurrentIndex(2)
    assert page.continue_button.isEnabled()

    page.continue_button.click()

    assert page.status.text() == "拳種辨識：待開發"
    assert page.service.clear_count == 1
    assert len(page._source_selectors) == 0


@pytest.mark.scenario("desktop-ui-design", "使用鍵盤分配 IMU")
def test_keyboard_can_select_imus_in_visual_field_order(qtbot) -> None:
    page = make_punch_page(qtbot, "出拳次數")
    page.show()
    first, second = page._source_selectors
    first.setFocus()
    qtbot.keyClick(first, Qt.Key.Key_Down)
    assert first.currentIndex() == 1
    following = first.nextInFocusChain()
    while following.focusPolicy() == Qt.FocusPolicy.NoFocus:
        following = following.nextInFocusChain()
    assert following is second


@pytest.mark.scenario("desktop-ui-design", "使用支援的最小視窗")
def test_minimum_window_has_resizable_scrolling_content(qtbot) -> None:
    window = MainWindow(SessionStub())  # type: ignore[arg-type]
    qtbot.addWidget(window)
    window.resize(900, 650)
    window.show()
    scroll = window.app_shell.findChild(QScrollArea, "contentScroll")

    assert window.minimumWidth() == 900
    assert window.minimumHeight() == 650
    assert scroll is not None and scroll.widgetResizable()
    assert window.app_shell.logout_button.isVisibleTo(window)


@pytest.mark.scenario("desktop-ui-design", "系統使用高 DPI 顯示比例")
def test_text_controls_are_not_constrained_by_fixed_heights(qtbot) -> None:
    window = MainWindow(SessionStub())  # type: ignore[arg-type]
    qtbot.addWidget(window)
    page = make_punch_page(qtbot, "出拳速度")

    assert window.app_shell.page_name.maximumHeight() >= 16_777_215
    assert page.status.wordWrap()
    assert all(selector.maximumHeight() >= 16_777_215 for selector in page._source_selectors)


@pytest.mark.scenario("desktop-ui-design", "user 調整 App 視窗大小")
def test_main_window_reflows_using_actual_available_width(qtbot) -> None:
    window = MainWindow(SessionStub())  # type: ignore[arg-type]
    qtbot.addWidget(window)
    window.show()

    home = window.home_page
    def assert_actual_layout() -> None:
        # Windows may clamp top-level windows to the runner's virtual screen.
        # The layout must follow the size actually allocated, not resize()'s request.
        content_width = home.width() - 56
        columns = 1 if content_width < 700 else 2 if content_width < 1000 else 3
        assert home.punch_column_count == columns
        position = (2, 0) if content_width < 700 else (0, 1)
        assert home.diagnostic_layout.getItemPosition(
            home.diagnostic_layout.indexOf(home.diagnostics_button)
        )[:2] == position

    for width, height in ((900, 650), (1500, 900), (900, 650)):
        window.resize(width, height)
        qtbot.waitUntil(assert_actual_layout)


@pytest.mark.scenario("desktop-ui-design", "user 調整 App 視窗大小")
def test_main_pages_and_fields_reflow_with_available_width(qtbot) -> None:
    # Non-native child widgets can be wider than their host viewport. This
    # exercises real Qt resize events without depending on monitor resolution.
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(900, 650)
    host.show()

    def mount(page):
        page.setParent(host)
        page.show()
        return page

    home = mount(HomePage())
    for width, columns in ((600, 1), (900, 2), (1200, 3), (900, 2), (600, 1)):
        home.resize(width, 800)

        def assert_home_layout() -> None:
            assert home.width() == width
            assert home.punch_column_count == columns
            for index, button in enumerate(home.punch_buttons.values()):
                assert home.punch_grid.getItemPosition(
                    home.punch_grid.indexOf(button)
                )[:2] == (index // columns, index % columns)
            assert home.diagnostic_layout.getItemPosition(
                home.diagnostic_layout.indexOf(home.diagnostics_button)
            )[:2] == ((2, 0) if columns == 1 else (0, 1))

        qtbot.waitUntil(assert_home_layout)
    home.hide()

    auth = AuthPage(SessionStub())  # type: ignore[arg-type]
    mount(auth)
    auth.resize(700, 650)
    qtbot.waitUntil(lambda: auth.card_layout.direction() == QBoxLayout.Direction.TopToBottom)
    auth.resize(900, 650)
    qtbot.waitUntil(lambda: auth.card_layout.direction() == QBoxLayout.Direction.LeftToRight)
    auth.hide()

    header = PageHeader("頁面標題", "說明文字")
    header.add_action(QLabel("頁面操作"))
    mount(header)
    header.resize(560, 160)
    qtbot.waitUntil(lambda: header.root_layout.direction() == QBoxLayout.Direction.TopToBottom)
    header.resize(900, 160)
    qtbot.waitUntil(lambda: header.root_layout.direction() == QBoxLayout.Direction.LeftToRight)
    header.hide()

    punch = make_punch_page(qtbot, "出拳次數")
    punch._started = True
    mount(punch)
    row_layout, _label, selector = punch._assignment_rows[0]
    punch.resize(600, 650)
    qtbot.waitUntil(lambda: row_layout.getItemPosition(row_layout.indexOf(selector))[:2] == (1, 0))
    punch.resize(900, 650)
    qtbot.waitUntil(lambda: row_layout.getItemPosition(row_layout.indexOf(selector))[:2] == (0, 1))
    punch.hide()

    diagnostics = ImuDiagnosticsPage(DiagnosticsStub())  # type: ignore[arg-type]
    diagnostics._started = True  # Layout test: never start a real scan or worker.
    mount(diagnostics)
    diagnostics.resize(560, 650)
    qtbot.waitUntil(lambda: diagnostics.summary.getItemPosition(
        diagnostics.summary.indexOf(diagnostics.connected_count_card)
    )[:2] == (1, 0))
    diagnostics.resize(900, 650)
    qtbot.waitUntil(lambda: diagnostics.summary.getItemPosition(
        diagnostics.summary.indexOf(diagnostics.connected_count_card)
    )[:2] == (0, 1))


@pytest.mark.scenario("desktop-ui-design", "IMU 測試進行中顯示完整百分比")
def test_diagnostic_progress_has_room_for_complete_percentage(qtbot) -> None:
    page = ImuDiagnosticsPage(DiagnosticsStub())  # type: ignore[arg-type]
    page._started = True
    qtbot.addWidget(page)
    page.show()
    page.progress.setValue(page.progress.maximum() // 2)
    qtbot.wait(10)

    assert page.progress.isTextVisible()
    assert page.progress.format() == "%p%"
    assert page.progress.height() >= page.progress.fontMetrics().height() + 6
