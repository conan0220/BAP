"""BAP Desktop App entry point."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

from bap_desktop import APP_NAME, PRODUCT_NAME, __version__


def _run_api_e2e() -> int:
    """Exercise the packaged clients against a real CI Backend over HTTP."""

    from bap_desktop.api_client import ApiRejectedError, AuthApiClient, ReleaseApiClient
    from bap_desktop.settings import DesktopSettings

    settings = DesktopSettings()
    base_url = str(settings.api_base_url)
    username = "E2E" + uuid.uuid4().hex[:12]
    password = "BapE2E12345"
    auth = AuthApiClient(base_url)
    created = auth.register(username, password)
    if created.get("username") != username:
        raise RuntimeError("register response did not contain the expected Username")
    try:
        auth.login(username, password + "wrong")
    except ApiRejectedError as error:
        if error.status_code != 401:
            raise
    else:
        raise RuntimeError("invalid login was unexpectedly accepted")
    try:
        auth.register(username, password)
    except ApiRejectedError as error:
        if error.status_code != 409:
            raise
    else:
        raise RuntimeError("duplicate Username was unexpectedly accepted")
    tokens = auth.login(username, password)
    refreshed = auth.refresh(tokens.refresh_token)
    auth.logout(refreshed.refresh_token)
    release = ReleaseApiClient(base_url).latest("windows")
    if not release.source_tree_sha:
        raise RuntimeError("release response did not contain Source Tree SHA")
    return 0


def main() -> int:
    """Start the Qt application while keeping imports lightweight for tooling."""

    if "--write-version" in sys.argv:
        index = sys.argv.index("--write-version")
        if index + 1 >= len(sys.argv):
            return 2
        Path(sys.argv[index + 1]).write_text(__version__, encoding="utf-8")
        return 0
    if "--api-e2e-test" in sys.argv:
        return _run_api_e2e()

    from PySide6.QtWidgets import QApplication

    from bap_desktop.api_client import AuthApiClient, ReleaseApiClient
    from bap_desktop.services.imu_diagnostics import ImuDiagnosticsService
    from bap_desktop.services.session import SessionService
    from bap_desktop.services.update import UpdateInstaller, UpdateService
    from bap_desktop.settings import DesktopSettings
    from bap_desktop.ui.main_window import MainWindow
    from bap_desktop.ui.styles import apply_bap_style

    smoke_test = "--smoke-test" in sys.argv
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(PRODUCT_NAME)
    apply_bap_style(app)
    settings = DesktopSettings()
    settings.prepare_local_directories()
    base_url = str(settings.api_base_url)
    session = SessionService(AuthApiClient(base_url))
    update_service = UpdateService(
        ReleaseApiClient(base_url),
        current_version=__version__,
        platform="windows",
    )
    update_installer = UpdateInstaller(settings.update_dir)
    window = MainWindow(
        session,
        diagnostic_service_factory=lambda: ImuDiagnosticsService(temp_dir=settings.temp_imu_dir),
        update_service=None if smoke_test else update_service,
        update_installer=None if smoke_test else update_installer,
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
