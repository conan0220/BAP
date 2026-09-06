"""Authenticated navigation shell for the BAP Desktop App."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot
from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from bap_desktop.api_client import ApiUnavailableError
from bap_desktop.resources import text
from bap_desktop.services.imu_diagnostics import ImuDiagnosticsService
from bap_desktop.services.imu_discovery import ImuDiscoveryService
from bap_desktop.services.session import SessionService
from bap_desktop.services.analysis_flow import AnalysisFlowService
from bap_desktop.services.shutdown import ShutdownCoordinator
from bap_desktop.services.update import (
    UpdateInstallError,
    UpdateInstaller,
    UpdateResult,
    UpdateService,
    consume_latest_update_outcome,
)
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


class _InstallSignals(QObject):
    progress = Signal(int)
    finished = Signal()
    failed = Signal(str)


class _InstallWorker(QRunnable):
    def __init__(self, installer: UpdateInstaller, result: UpdateResult) -> None:
        super().__init__()
        self.installer = installer
        self.result = result
        self.signals = _InstallSignals()

    @Slot()
    def run(self) -> None:
        try:
            self.installer.download_and_launch(
                self.result,
                progress=self.signals.progress.emit,
            )
        except UpdateInstallError as error:
            self.signals.failed.emit(str(error))
            return
        self.signals.finished.emit()


class MainWindow(QMainWindow):
    """Show login, home, diagnostics, or exactly one punch item page."""

    def __init__(
        self,
        session: SessionService,
        *,
        diagnostic_service_factory: Callable[[], ImuDiagnosticsService] = ImuDiagnosticsService,
        discovery_service_factory: Callable[[], ImuDiscoveryService] = ImuDiscoveryService,
        analysis_flow: AnalysisFlowService | None = None,
        measurement_sessions_dir=None,
        desktop_version: str = "0.0.0",
        update_service: UpdateService | None = None,
        update_installer: UpdateInstaller | None = None,
        quit_for_update: Callable[[], None] | None = None,
        restore_session: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self.diagnostic_service_factory = diagnostic_service_factory
        self.discovery_service_factory = discovery_service_factory
        self.analysis_flow = analysis_flow
        self.measurement_sessions_dir = measurement_sessions_dir
        self.desktop_version = desktop_version
        self.update_service = update_service
        self.update_installer = update_installer
        self.quit_for_update = quit_for_update or self._quit_application
        self.shutdown_coordinator = ShutdownCoordinator()
        self.worker_pool = QThreadPool(self)
        self._install_worker: _InstallWorker | None = None
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
        self.update_banner.install_requested.connect(self._start_update_install)
        self.shutdown_coordinator.register(self.session.close)
        if self.update_installer is not None:
            self.shutdown_coordinator.register(self.update_installer.close)
        self.shutdown_coordinator.register(lambda: self.worker_pool.waitForDone(30_000))

        restored = False
        if restore_session:
            try:
                restored = self.session.restore()
            except ApiUnavailableError:
                restored = False
        self.stack.setCurrentWidget(self.app_shell if restored else self.auth_page)
        update_dir = getattr(self.update_installer, "update_dir", None)
        update_outcome = consume_latest_update_outcome(update_dir) if update_dir is not None else None
        if update_outcome is not None:
            self.update_banner.show_update_outcome(update_outcome)
        elif self.update_service is not None:
            self.update_banner.message.setText(text.UPDATE_CHECKING)
            self.update_banner.show()
            QTimer.singleShot(0, self.start_update_check)

    @Slot()
    def start_update_check(self) -> None:
        if self.update_service is None:
            return
        worker = _UpdateWorker(self.update_service)
        worker.signals.finished.connect(self._show_update_result)
        self.worker_pool.start(worker)

    @Slot(object)
    def _show_update_result(self, result: UpdateResult) -> None:
        self.update_banner.show_result(result)

    @Slot(object)
    def _start_update_install(self, result: UpdateResult) -> None:
        if self.update_installer is None or self._install_worker is not None:
            self.update_banner.show_install_failed()
            return
        self.update_banner.show_download_progress()
        worker = _InstallWorker(self.update_installer, result)
        self._install_worker = worker
        worker.signals.progress.connect(self.update_banner.show_download_progress)
        worker.signals.failed.connect(self._update_install_failed)
        worker.signals.finished.connect(self._update_install_started)
        self.worker_pool.start(worker)

    @Slot(str)
    def _update_install_failed(self, message: str) -> None:
        self._install_worker = None
        self.update_banner.show_install_failed(message)

    @Slot()
    def _update_install_started(self) -> None:
        self._install_worker = None
        self.update_banner.show_handoff()
        self.shutdown()
        self.update_banner.show_installing()
        QTimer.singleShot(0, self.quit_for_update)

    @staticmethod
    def _quit_application() -> None:
        app = QApplication.instance()
        if app is not None:
            app.quit()

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
            PunchItemPage(
                item_name,
                service=self.discovery_service_factory(),
                analysis_flow=self.analysis_flow,
                recording_root=self.measurement_sessions_dir,
                desktop_version=self.desktop_version,
            ),
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

    def shutdown(self) -> None:
        self.shutdown_coordinator.shutdown()

    def closeEvent(self, event) -> None:
        self.shutdown()
        super().closeEvent(event)
