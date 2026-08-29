"""Plain-language Traditional Chinese login and registration UI."""

from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from bap_common.validation import validate_password, validate_username
from bap_desktop.api_client import ApiRejectedError, ApiUnavailableError
from bap_desktop.resources import text
from bap_desktop.services.session import SessionService


class AuthPage(QWidget):
    authenticated = Signal()

    def __init__(self, session: SessionService, parent=None) -> None:
        super().__init__(parent)
        self.session = session
        self.tabs = QTabWidget()
        self.login_username = QLineEdit()
        self.login_password = QLineEdit()
        self.login_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.remember = QCheckBox(text.REMEMBER_LOGIN)
        self.login_message = QLabel("")
        self.login_button = QPushButton(text.LOGIN)
        self.show_login_password = QCheckBox(text.SHOW_PASSWORD)

        login = QWidget()
        login_form = QFormLayout(login)
        login_form.addRow("Username", self.login_username)
        login_form.addRow(text.PASSWORD, self.login_password)
        login_form.addRow("", self.show_login_password)
        login_form.addRow("", self.remember)
        login_form.addRow("", self.login_button)
        login_form.addRow("", self.login_message)

        self.register_username = QLineEdit()
        self.register_password = QLineEdit()
        self.register_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.username_rule = QLabel(text.USERNAME_RULE)
        self.password_rule = QLabel(text.PASSWORD_RULE)
        self.register_message = QLabel("")
        self.register_button = QPushButton(text.CREATE_ACCOUNT)
        register = QWidget()
        register_form = QFormLayout(register)
        register_form.addRow("Username", self.register_username)
        register_form.addRow("", self.username_rule)
        register_form.addRow(text.PASSWORD, self.register_password)
        register_form.addRow("", self.password_rule)
        register_form.addRow("", self.register_button)
        register_form.addRow("", self.register_message)

        self.tabs.addTab(login, text.LOGIN)
        self.tabs.addTab(register, text.REGISTER)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(text.APP_TITLE))
        layout.addWidget(self.tabs)

        self.show_login_password.toggled.connect(
            lambda shown: self.login_password.setEchoMode(
                QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password
            )
        )
        self.login_button.clicked.connect(self._login)
        self.register_button.clicked.connect(self._register)
        self.register_username.textChanged.connect(self._update_rules)
        self.register_password.textChanged.connect(self._update_rules)
        self._update_rules()

    @Slot()
    def _update_rules(self) -> None:
        username_ok = validate_username(self.register_username.text())
        password_ok = validate_password(self.register_password.text())
        self.username_rule.setProperty("valid", username_ok)
        self.password_rule.setProperty("valid", password_ok)
        self.register_button.setEnabled(username_ok and password_ok)

    @Slot()
    def _register(self) -> None:
        try:
            self.session.api.register(self.register_username.text(), self.register_password.text())
        except (ApiRejectedError, ApiUnavailableError) as error:
            self.register_message.setText(str(error))
            return
        self.register_message.setText(text.REGISTER_SUCCEEDED)
        self.login_username.setText(self.register_username.text())
        self.tabs.setCurrentIndex(0)

    @Slot()
    def _login(self) -> None:
        username = self.login_username.text()
        try:
            self.session.login(
                username,
                self.login_password.text(),
                remember=self.remember.isChecked(),
            )
        except ApiRejectedError:
            self.login_message.setText(text.LOGIN_REJECTED)
            return
        except ApiUnavailableError:
            self.login_message.setText(text.SERVER_UNAVAILABLE)
            return
        self.login_message.clear()
        self.authenticated.emit()
