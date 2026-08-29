"""Authenticated navigation shell for the BAP Desktop App."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from bap_desktop.api_client import ApiUnavailableError
from bap_desktop.resources import text
from bap_desktop.services.imu_diagnostics import ImuDiagnosticsService
from bap_desktop.services.imu_discovery import ImuDiscoveryService
from bap_desktop.services.session import SessionService
from bap_desktop.services.shutdown import ShutdownCoordinator
from bap_desktop.services.update import UpdateResult, UpdateService
from bap_desktop.ui.auth import AuthPage
from bap_desktop.ui.home import HomePage
from bap_desktop.ui.imu_diagnostics import ImuDiagnosticsPage
from bap_desktop.ui.punch_items import PunchItemPage
from bap_desktop.ui.update_banner import UpdateBanner


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

        self.stack = QStackedWidget()
        self.auth_page = AuthPage(session)
        self.home_page = HomePage()
        self.stack.addWidget(self.auth_page)
        self.stack.addWidget(self.home_page)
        self.update_banner = UpdateBanner()
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(self.update_banner)
        root_layout.addWidget(self.stack)
        self.setCentralWidget(root)
        self.setWindowTitle("BAP")
        self.resize(900, 640)

        self.auth_page.authenticated.connect(self.show_home)
        self.home_page.open_diagnostics.connect(self.show_diagnostics)
        self.home_page.open_punch_item.connect(self.show_punch_item)
        self.home_page.logout_requested.connect(self.logout)
        self.update_banner.download_requested.connect(self._open_update_url)
        self.shutdown_coordinator.register(self.session.close)

        restored = False
        if restore_session:
            try:
                restored = self.session.restore()
            except ApiUnavailableError:
                restored = False
        self.stack.setCurrentWidget(self.home_page if restored else self.auth_page)
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
        self.stack.setCurrentWidget(self.home_page)

    @Slot()
    def show_diagnostics(self) -> None:
        self._show_feature(ImuDiagnosticsPage(service=self.diagnostic_service_factory()))

    @Slot(str)
    def show_punch_item(self, item_name: str) -> None:
        if item_name not in text.PUNCH_ITEMS:
            return
        self._show_feature(PunchItemPage(item_name, service=self.discovery_service_factory()))

    @Slot()
    def logout(self) -> None:
        self._discard_feature_page()
        self.session.logout()
        self.stack.setCurrentWidget(self.auth_page)

    def _show_feature(self, page: QWidget) -> None:
        self._discard_feature_page()
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        back = QPushButton(text.BACK_HOME)
        back.clicked.connect(self.show_home)
        layout.addWidget(back)
        layout.addWidget(page)
        self._feature_wrapper = wrapper
        self._feature_page = page
        shutdown = getattr(page, "shutdown", None)
        if callable(shutdown):
            self.shutdown_coordinator.register(shutdown)
        self.stack.addWidget(wrapper)
        self.stack.setCurrentWidget(wrapper)

    def _discard_feature_page(self) -> None:
        page = self._feature_page
        wrapper = self._feature_wrapper
        if page is not None:
            shutdown = getattr(page, "shutdown", None)
            if callable(shutdown):
                shutdown()
                self.shutdown_coordinator.unregister(shutdown)
        if wrapper is not None:
            self.stack.removeWidget(wrapper)
            wrapper.deleteLater()
        self._feature_page = None
        self._feature_wrapper = None

    def closeEvent(self, event) -> None:
        self.shutdown_coordinator.shutdown()
        super().closeEvent(event)
