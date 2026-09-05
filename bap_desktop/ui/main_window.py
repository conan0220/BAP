"""Authenticated navigation shell for the BAP Desktop App."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from bap_desktop.api_client import ApiUnavailableError
from bap_desktop.resources import text
from bap_desktop.services.imu_diagnostics import ImuDiagnosticsService
from bap_desktop.services.imu_discovery import ImuDiscoveryService
from bap_desktop.services.session import SessionService
from bap_desktop.services.shutdown import ShutdownCoordinator
from bap_desktop.services.update import UpdateResult, UpdateService
from bap_desktop.ui.auth import AuthPage
from bap_desktop.ui.app_shell import AppShell
from bap_desktop.ui.home import HomePage
from bap_desktop.ui.imu_diagnostics import ImuDiagnosticsPage
from bap_desktop.ui.punch_items import PunchItemPage
from bap_desktop.ui.update_banner import UpdateBanner
from bap_desktop.ui.styles import apply_bap_style


class _UpdateSignals(QObject):
    finished = Signal(object)


class _UpdateWorker(QRunnable):
    def __init__(self, service: UpdateService) -> None:
        super().__init__()
        self.service = service
        self.signals = _UpdateSignals()

    @Slot()
    def run(self) -> None:
        self.signals.finished.emit(self.service.check())


class MainWindow(QMainWindow):
    """Show login, home, diagnostics, or exactly one punch item page."""

    def __init__(
        self,
        session: SessionService,
        *,
        diagnostic_service_factory: Callable[[], ImuDiagnosticsService] = ImuDiagnosticsService,
        discovery_service_factory: Callable[[], ImuDiscoveryService] = ImuDiscoveryService,
        update_service: UpdateService | None = None,
        url_opener: Callable[[QUrl], object] = QDesktopServices.openUrl,
        restore_session: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self.diagnostic_service_factory = diagnostic_service_factory
        self.discovery_service_factory = discovery_service_factory
        self.update_service = update_service
        self.url_opener = url_opener
        self.shutdown_coordinator = ShutdownCoordinator()
        self._feature_wrapper: QWidget | None = None
        self._feature_page: QWidget | None = None

        apply_bap_style(QApplication.instance())
        self.stack = QStackedWidget()
        self.auth_page = AuthPage(session)
        self.home_page = HomePage()
        self.app_shell = AppShell(self.home_page)
        self.stack.addWidget(self.auth_page)
        self.stack.addWidget(self.app_shell)
        self.update_banner = UpdateBanner()
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(self.update_banner)
        root_layout.addWidget(self.stack)
        self.setCentralWidget(root)
        self.setWindowTitle("BAP")
        self.setMinimumSize(900, 650)
        self.resize(1040, 720)

        self.auth_page.authenticated.connect(self.show_home)
        self.home_page.open_diagnostics.connect(self.show_diagnostics)
        self.home_page.open_punch_item.connect(self.show_punch_item)
        self.app_shell.home_requested.connect(self.show_home)
        self.app_shell.diagnostics_requested.connect(self.show_diagnostics)
        self.app_shell.punch_item_requested.connect(self.show_punch_item)
        self.app_shell.logout_requested.connect(self.logout)
        self.update_banner.download_requested.connect(self._open_update_url)
        self.shutdown_coordinator.register(self.session.close)

        restored = False
        if restore_session:
            try:
                restored = self.session.restore()
            except ApiUnavailableError:
                restored = False
        self.stack.setCurrentWidget(self.app_shell if restored else self.auth_page)
        if self.update_service is not None:
            self.update_banner.message.setText(text.UPDATE_CHECKING)
            self.update_banner.show()
            QTimer.singleShot(0, self.start_update_check)

    @Slot()
    def start_update_check(self) -> None:
        if self.update_service is None:
            return
        worker = _UpdateWorker(self.update_service)
        worker.signals.finished.connect(self._show_update_result)
        QThreadPool.globalInstance().start(worker)

    @Slot(object)
    def _show_update_result(self, result: UpdateResult) -> None:
        self.update_banner.show_result(result)

    @Slot(str)
    def _open_update_url(self, url: str) -> None:
        self.url_opener(QUrl(url))

    @Slot()
    def show_home(self) -> None:
        self._discard_feature_page()
        username = self.auth_page.login_username.text().strip() or None
        self.app_shell.set_account_name(username)
        self.app_shell.show_home()
        self.stack.setCurrentWidget(self.app_shell)

    @Slot()
    def show_diagnostics(self) -> None:
        self._show_feature(
            ImuDiagnosticsPage(service=self.diagnostic_service_factory()),
            key="diagnostics",
            title=text.IMU_DIAGNOSTICS,
        )

    @Slot(str)
    def show_punch_item(self, item_name: str) -> None:
        if item_name not in text.PUNCH_ITEMS:
            return
        self._show_feature(
            PunchItemPage(item_name, service=self.discovery_service_factory()),
            key=f"punch:{item_name}",
            title=item_name,
        )

    @Slot()
    def logout(self) -> None:
        self._discard_feature_page()
        self.session.logout()
        self.stack.setCurrentWidget(self.auth_page)

    def _show_feature(self, page: QWidget, *, key: str, title: str) -> None:
        self._discard_feature_page()
        self._feature_wrapper = page
        self._feature_page = page
        shutdown = getattr(page, "shutdown", None)
        if callable(shutdown):
            self.shutdown_coordinator.register(shutdown)
        self.app_shell.set_feature(page, key=key, title=title)
        self.stack.setCurrentWidget(self.app_shell)

    def _discard_feature_page(self) -> None:
        page = self._feature_page
        if page is not None:
            shutdown = getattr(page, "shutdown", None)
            if callable(shutdown):
                shutdown()
                self.shutdown_coordinator.unregister(shutdown)
        removed = self.app_shell.remove_feature()
        if removed is not None:
            removed.deleteLater()
        self._feature_page = None
        self._feature_wrapper = None

    def closeEvent(self, event) -> None:
        self.shutdown_coordinator.shutdown()
        super().closeEvent(event)
