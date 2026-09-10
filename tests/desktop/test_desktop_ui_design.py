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
from bap_desktop.api_client.analysis import AnalysisCapability
from bap_common.analysis_contracts import builtin_analysis_specifications
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
    window.app_shell.nav_buttons["punch:拳頭速度"].click()
    assert window.app_shell.page_name.text() == "拳頭速度"
    assert window.app_shell.nav_buttons["punch:拳頭速度"].isChecked()
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
def test_home_has_two_available_items_and_three_pending_items(qtbot) -> None:
    window = MainWindow(SessionStub())  # type: ignore[arg-type]
    qtbot.addWidget(window)

    assert tuple(window.home_page.punch_buttons) == (
        "出拳次數",
        "拳頭速度",
        "出拳力量",
        "出拳軌跡",
        "拳種辨識",
    )
    assert "可使用" in window.home_page.punch_buttons["出拳次數"].text()
    assert "可使用" in window.home_page.punch_buttons["拳頭速度"].text()
    assert all(
        "待開發" in button.text()
        for name, button in window.home_page.punch_buttons.items()
        if name not in {"出拳次數", "拳頭速度"}
    )
    assert not any("拳型辨識" in button.text() for button in window.home_page.punch_buttons.values())


def test_punch_count_page_is_not_labeled_as_pending(qtbot) -> None:
    page = make_punch_page(qtbot, "出拳次數")

    assert page.analysis_chip.text() == "可使用"
    assert page.analysis_chip.objectName() == "statusChip"


def test_punch_speed_page_is_not_labeled_as_pending(qtbot) -> None:
    page = make_punch_page(qtbot, "拳頭速度")

    assert page.analysis_chip.text() == "可使用"
    assert page.analysis_chip.objectName() == "statusChip"


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
@pytest.mark.scenario("desktop-ui-design", "user 進入出拳次數")
def test_each_decided_item_builds_its_required_two_placement_fields(qtbot) -> None:
    expected = {
        "出拳次數": ("左手腕", "右手腕"),
        "拳頭速度": ("左手腕", "右手腕"),
        "出拳軌跡": ("左手腕", "右手腕"),
        "拳種辨識": ("左手把背面", "右手把背面"),
    }
    for item_name, placement_names in expected.items():
        page = make_punch_page(qtbot, item_name)
        assert tuple(placement.name for placement in page._source_selectors.values()) == placement_names
        assert all(selector.count() == len(SOURCES) + 1 for selector in page._source_selectors)


@pytest.mark.scenario("desktop-ui-design", "IMU 尚未完成分配")
@pytest.mark.scenario("imu-source-discovery", "尚有位置未分配")
@pytest.mark.scenario("imu-source-discovery", "尚有必要 Input Role 未分配")
def test_incomplete_assignment_keeps_continue_disabled(qtbot) -> None:
    page = make_punch_page(qtbot, "出拳次數")
    first = list(page._source_selectors)[0]
    first.setCurrentIndex(1)

    assert not page.continue_button.isEnabled()
    assert "待開發" not in page.status.text()


@pytest.mark.scenario("imu-source-discovery", "user 將同一顆 IMU 分配給兩個位置")
def test_duplicate_assignment_is_rejected_with_text(qtbot) -> None:
    page = make_punch_page(qtbot, "拳頭速度")
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
    page = make_punch_page(qtbot, "拳頭速度")

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


@pytest.mark.scenario("imu-source-discovery", "已註冊分析完成有效分配")
@pytest.mark.scenario("desktop-ui-design", "IMU 分配完成且分析可執行")
@pytest.mark.scenario("boxing-analysis-session", "Analysis Executor 可用")
def test_executable_capability_enables_start_measurement(qtbot, tmp_path: Path) -> None:
    class Flow:
        pass

    result = DiscoveryResult(SOURCES, ())
    page = PunchItemPage(
        "出拳次數", DiscoveryStub(result), analysis_flow=Flow(), recording_root=tmp_path
    )
    qtbot.addWidget(page)
    page._show_sources(result)
    first, second = page._source_selectors
    first.setCurrentIndex(1)
    second.setCurrentIndex(2)
    capability = AnalysisCapability(builtin_analysis_specifications()[0], True)
    page._capability_ready(capability)

    assert page._measurement_state == "ready"
    assert page.continue_button.text() == "開始測量"
    assert page.continue_button.isEnabled()


@pytest.mark.scenario("imu-source-discovery", "分析 Executor 尚未提供")
@pytest.mark.scenario("boxing-analysis-session", "Analysis Executor 尚未提供")
@pytest.mark.scenario("punch-speed-analysis", "Backend 尚未提供可執行 Executor")
def test_unavailable_capability_does_not_record(qtbot) -> None:
    page = make_punch_page(qtbot, "出拳次數")
    page._capability_ready(AnalysisCapability(builtin_analysis_specifications()[0], False))
    assert "Backend 目前沒有提供" in page.status.text()
    assert page.analysis_chip.text() == "目前無法使用"
    assert not page.continue_button.isEnabled()


def test_unavailable_punch_speed_names_the_correct_analysis(qtbot) -> None:
    speed_specification = next(
        specification
        for specification in builtin_analysis_specifications()
        if specification.analysis_type == "punch_speed"
        and specification.spec_version == 2
    )
    page = make_punch_page(qtbot, "拳頭速度")
    page._capability_ready(AnalysisCapability(speed_specification, False))

    assert "Backend 目前沒有提供拳頭速度分析" in page.status.text()
    assert "出拳次數分析" not in page.status.text()
    assert page.analysis_chip.text() == "目前無法使用"
    assert not page.continue_button.isEnabled()


@pytest.mark.scenario("imu-source-discovery", "探索資料與正式資料分離")
def test_discovery_is_cleared_before_formal_recording(qtbot) -> None:
    page = make_punch_page(qtbot, "出拳次數")
    first, second = page._source_selectors
    first.setCurrentIndex(1)
    second.setCurrentIndex(2)
    page._capability_ready(AnalysisCapability(builtin_analysis_specifications()[0], True))
    assert page.service.clear_count == 1
    assert page._recording is None


@pytest.mark.scenario("desktop-ui-design", "正在錄製")
@pytest.mark.scenario("boxing-analysis-session", "user 開始新的測量")
@pytest.mark.scenario("boxing-analysis-session", "從出拳次數頁面建立 Session")
@pytest.mark.scenario("boxing-analysis-session", "使用預設時間開始")
def test_start_measurement_shows_elapsed_time_and_stop_action(qtbot, tmp_path: Path) -> None:
    class Recording:
        def __init__(self, *_args, **_kwargs):
            self.started = False
            self.kwargs = _kwargs

        def start(self):
            self.started = True

        def abort(self):
            pass

    page = make_punch_page(qtbot, "出拳次數")
    page.recording_root = tmp_path
    page.recording_factory = Recording
    first, second = page._source_selectors
    first.setCurrentIndex(1)
    second.setCurrentIndex(2)
    page._measurement_state = "ready"
    page._start_measurement()
    page._update_elapsed()

    assert page._recording.started
    assert page._measurement_state == "recording"
    assert page.continue_button.text() == "提前結束測量"
    assert page._recording.kwargs["requested_duration_seconds"] == 60
    assert "已錄製" in page.timer_details.text()
    assert "剩餘" in page.timer_details.text()
    page.shutdown()


@pytest.mark.scenario("punch-speed-analysis", "正式測量前先做兩秒靜止校正")
@pytest.mark.scenario("punch-speed-analysis", "user 完成靜止校正")
def test_punch_speed_calibrates_before_formal_measurement(qtbot, tmp_path: Path) -> None:
    class Recording:
        def __init__(self, *_args, **kwargs):
            self.kwargs = kwargs
            self.is_calibrating = True
            self.due = False
            self.began = False

        def start(self):
            pass

        def abort(self):
            pass

        def due_stop_reason(self):
            return None

        def calibration_remaining_seconds(self):
            return 0.0 if self.due else 2.0

        def calibration_due(self):
            return self.due

        def begin_measurement(self):
            self.began = True
            self.is_calibrating = False

        def elapsed_seconds(self):
            return 0.0

        def remaining_seconds(self):
            return 10.0

    page = make_punch_page(qtbot, "拳頭速度")
    page.recording_root = tmp_path
    page.recording_factory = Recording
    first, second = page._source_selectors
    first.setCurrentIndex(1)
    second.setCurrentIndex(2)
    page._measurement_state = "ready"
    page.duration_input.setText("10")
    page._start_measurement()

    assert page._measurement_state == "calibrating"
    assert page._recording.kwargs["spec_version"] == 2
    assert "保持不動" in page.status.text()
    assert not page.continue_button.isEnabled()
    page._recording.due = True
    page._update_elapsed()
    assert page._recording.began
    assert page._measurement_state == "recording"
    assert page.continue_button.isEnabled()
    page.shutdown()


@pytest.mark.scenario("punch-speed-analysis", "校正期間必要 IMU 中斷")
def test_punch_speed_calibration_interruption_returns_to_retry_state(qtbot) -> None:
    from bap_common.analysis_session import SessionStopReason

    class Recording:
        aborted = False

        def due_stop_reason(self):
            return SessionStopReason.SOURCE_INTERRUPTED

        def abort(self):
            self.aborted = True

    page = make_punch_page(qtbot, "拳頭速度")
    page._recording = Recording()
    page._measurement_state = "calibrating"
    page._update_elapsed()

    assert page._recording.aborted
    assert page._measurement_state == "calibration_failed"
    assert "校正期間 IMU 連線中斷" in page.status.text()
    assert page.continue_button.text() == "重新檢測 IMU"
    assert page.continue_button.isEnabled()


@pytest.mark.scenario("boxing-analysis-session", "輸入無效時間")
@pytest.mark.parametrize("value", ("", "4", "3601", "1.5", "abc"))
def test_invalid_session_duration_does_not_start_recording(qtbot, tmp_path: Path, value: str) -> None:
    class MustNotStart:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("invalid duration must not create a recording")

    page = make_punch_page(qtbot, "出拳次數")
    page.recording_root = tmp_path
    page.recording_factory = MustNotStart
    page._measurement_state = "ready"
    page.duration_input.setText(value)
    page._start_measurement()

    assert page._measurement_state == "ready"
    assert "5～3600" in page.status.text()


@pytest.mark.scenario("boxing-analysis-session", "輸入有效的自訂時間")
def test_custom_session_duration_is_forwarded_to_recording(qtbot, tmp_path: Path) -> None:
    captured = {}

    class Recording:
        def __init__(self, *_args, **kwargs):
            captured.update(kwargs)

        def start(self):
            pass

        def abort(self):
            pass

    page = make_punch_page(qtbot, "出拳次數")
    page.recording_root = tmp_path
    page.recording_factory = Recording
    page._measurement_state = "ready"
    page.duration_input.setText("125")
    page._start_measurement()
    assert captured["requested_duration_seconds"] == 125
    page.shutdown()


@pytest.mark.scenario("boxing-analysis-session", "錄製期間無線 Node 中斷")
def test_timer_forwards_source_interruption_to_single_finalizer(qtbot) -> None:
    reasons = []

    class Recording:
        def elapsed_seconds(self):
            return 1.1

        def remaining_seconds(self):
            return 58.9

        def due_stop_reason(self):
            from bap_common.analysis_session import SessionStopReason
            return SessionStopReason.SOURCE_INTERRUPTED

    page = make_punch_page(qtbot, "出拳次數")
    page._recording = Recording()
    page._measurement_state = "recording"
    page._finish_measurement = lambda reason: reasons.append(reason)
    page._update_elapsed()
    from bap_common.analysis_session import SessionStopReason
    assert reasons == [SessionStopReason.SOURCE_INTERRUPTED]


@pytest.mark.scenario("desktop-ui-design", "收到有效 Result")
@pytest.mark.scenario("boxing-analysis-session", "Backend 完成分析")
def test_completed_result_is_rendered_with_session_identity(qtbot) -> None:
    from types import SimpleNamespace

    class Flow:
        def validate_completed(self, _payload):
            return SimpleNamespace(
                session_id="session-123", analysis_id="analysis-1",
                result={
                    "left_punch_count": 2,
                    "right_punch_count": 3,
                    "total_punch_count": 5,
                },
            )

    page = make_punch_page(qtbot, "出拳次數")
    page.analysis_flow = Flow()
    page._analysis_status_ready({"status": "completed"})
    visible = " ".join(label.text() for label in page.findChildren(QLabel))
    assert "session-123" in visible
    assert "總出拳次數：5" in visible
    assert "左手：2" in visible
    assert "右手：3" in visible


@pytest.mark.scenario("punch-speed-analysis", "Result 顯示左右手摘要與每拳速度")
def test_completed_punch_speed_result_is_rendered_in_meters_per_second(qtbot) -> None:
    from types import SimpleNamespace

    class Flow:
        def validate_completed(self, _payload):
            return SimpleNamespace(
                session_id="speed-session", analysis_id="speed-analysis",
                result={
                    "algorithm_version": "rule_v1",
                    "left_punch_count": 1,
                    "right_punch_count": 0,
                    "total_punch_count": 1,
                    "left_average_speed_mps": 7.25,
                    "left_max_speed_mps": 7.25,
                    "right_average_speed_mps": 0.0,
                    "right_max_speed_mps": 0.0,
                    "punches": [{
                        "hand": "left", "punch_index": 1,
                        "start_elapsed_us": 2_500_000,
                        "peak_elapsed_us": 2_650_000,
                        "end_elapsed_us": 2_800_000,
                        "peak_speed_mps": 7.25,
                    }],
                },
            )

    page = make_punch_page(qtbot, "拳頭速度")
    page.analysis_flow = Flow()
    page._analysis_status_ready({"status": "completed"})
    visible = " ".join(label.text() for label in page.findChildren(QLabel))
    assert "平均拳頭速度 7.25 m/s" in visible
    assert "最高拳頭速度 0.00 m/s" in visible
    assert page.result_table.rowCount() == 1
    assert page.result_table.item(0, 2).text() == "7.25 m/s"


@pytest.mark.scenario("boxing-analysis-session", "user 在結果頁重新測量")
def test_completed_result_offers_restart_and_returns_to_imu_discovery(qtbot) -> None:
    from types import SimpleNamespace

    class Flow:
        def validate_completed(self, _payload):
            return SimpleNamespace(
                session_id="session-123",
                analysis_id="analysis-1",
                result={
                    "left_punch_count": 2,
                    "right_punch_count": 3,
                    "total_punch_count": 5,
                },
            )

    page = make_punch_page(qtbot, "出拳次數")
    page.analysis_flow = Flow()
    page.duration_row.setVisible(True)
    page.timer_details.setVisible(True)
    page.duration_input.setEnabled(False)
    page._analysis_status_ready({"status": "completed"})

    assert page.continue_button.text() == "重新測量"
    assert page.continue_button.isEnabled()
    assert not page.duration_row.isVisible()
    assert not page.timer_details.isVisible()

    page.continue_button.click()

    assert page._measurement_state == "assigning"
    assert page._draft is None
    assert page._remote_session_id is None
    assert page._remote_analysis_id is None
    assert page.continue_button.text() == "繼續"
    assert "分析完成" not in page.status.text()


@pytest.mark.scenario("desktop-ui-design", "正在上傳或分析")
def test_pending_backend_status_is_not_rendered_as_result(qtbot) -> None:
    page = make_punch_page(qtbot, "出拳次數")
    page._analysis_status_ready({"status": "pending"})
    assert page._measurement_state == "analyzing"
    assert "分析中" in page.status.text()
    assert "Result" not in page.status.text()


@pytest.mark.scenario("desktop-ui-design", "收到不符合規格的 Result")
def test_invalid_result_is_not_shown_as_success(qtbot) -> None:
    class Flow:
        def validate_completed(self, _payload):
            raise ValueError("bad result")

    page = make_punch_page(qtbot, "出拳次數")
    page.analysis_flow = Flow()
    page._analysis_status_ready({"status": "completed"})
    assert "格式不正確" in page.status.text()
    assert page._measurement_state == "failed"


@pytest.mark.scenario("desktop-ui-design", "上傳時網路中斷")
@pytest.mark.scenario("boxing-analysis-session", "上傳中斷")
def test_upload_failure_offers_retry_without_new_recording(qtbot) -> None:
    page = make_punch_page(qtbot, "出拳次數")
    page._upload_failed("網路中斷")
    assert page._measurement_state == "upload_failed"
    assert page.continue_button.text() == "重試上傳"
    assert "不需要重新測量" in page.message.text()
