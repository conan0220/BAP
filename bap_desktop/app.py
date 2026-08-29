"""BAP Desktop App entry point."""

from __future__ import annotations

import sys

from bap_desktop import APP_NAME, PRODUCT_NAME, __version__


def main() -> int:
    """Start the Qt application while keeping imports lightweight for tooling."""

    from PySide6.QtWidgets import QApplication

    from bap_desktop.api_client import AuthApiClient, ReleaseApiClient
    from bap_desktop.services.imu_diagnostics import ImuDiagnosticsService
    from bap_desktop.services.session import SessionService
    from bap_desktop.services.update import UpdateService
    from bap_desktop.settings import DesktopSettings
    from bap_desktop.ui.main_window import MainWindow

    # QApplication may consume command-line options, so read our smoke flag first.
    smoke_test = "--smoke-test" in sys.argv
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(PRODUCT_NAME)
    settings = DesktopSettings()
    settings.prepare_local_directories()
    base_url = str(settings.api_base_url)
    session = SessionService(AuthApiClient(base_url))
    update_service = UpdateService(
        ReleaseApiClient(base_url),
        current_version=__version__,
        platform="windows",
    )
    window = MainWindow(
        session,
        diagnostic_service_factory=lambda: ImuDiagnosticsService(temp_dir=settings.temp_imu_dir),
        update_service=None if smoke_test else update_service,
        restore_session=not smoke_test,
    )
    window.show()
    if smoke_test:
        app.processEvents()
        window.hide()
        return 0
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
