"""Plain-language Traditional Chinese login and registration UI."""

from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QBoxLayout,
    QCheckBox,
    QFrame,
    QFormLayout,
    QHBoxLayout,
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
        self.setObjectName("authPage")
        self.session = session
        self.tabs = QTabWidget()
        self.login_username = QLineEdit()
        self.login_password = QLineEdit()
        self.login_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.remember = QCheckBox(text.REMEMBER_LOGIN)
        self.login_message = QLabel("")
        self.login_message.setObjectName("errorMessage")
        self.login_button = QPushButton(text.LOGIN)
        self.login_button.setProperty("role", "primary")
        self.show_login_password = QCheckBox(text.SHOW_PASSWORD)

        login = QWidget()
        login_form = QFormLayout(login)
        login_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        login_username_label = QLabel("Username")
        login_username_label.setBuddy(self.login_username)
        login_password_label = QLabel(text.PASSWORD)
        login_password_label.setBuddy(self.login_password)
        login_form.addRow(login_username_label, self.login_username)
        login_form.addRow(login_password_label, self.login_password)
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
        self.register_message.setObjectName("errorMessage")
        self.register_button = QPushButton(text.CREATE_ACCOUNT)
        self.register_button.setProperty("role", "primary")
        register = QWidget()
        register_form = QFormLayout(register)
        register_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        register_username_label = QLabel("Username")
        register_username_label.setBuddy(self.register_username)
        register_password_label = QLabel(text.PASSWORD)
        register_password_label.setBuddy(self.register_password)
        register_form.addRow(register_username_label, self.register_username)
        register_form.addRow("", self.username_rule)
        register_form.addRow(register_password_label, self.register_password)
        register_form.addRow("", self.password_rule)
        register_form.addRow("", self.register_button)
        register_form.addRow("", self.register_message)
        self._forms = (login_form, register_form)
        for hint in (self.username_rule, self.password_rule, self.login_message, self.register_message):
            hint.setWordWrap(True)

        self.tabs.addTab(login, text.LOGIN)
        self.tabs.addTab(register, text.REGISTER)
        intro = QFrame()
        intro.setObjectName("authIntro")
        intro_layout = QVBoxLayout(intro)
        intro_layout.setContentsMargins(28, 28, 28, 28)
        mark = QLabel("BAP")
        mark.setObjectName("brandMark")
        hero_title = QLabel("Boxing Analysis Platform")
        hero_title.setObjectName("authHeroTitle")
        hero_text = QLabel("連接 IMU、確認裝置狀態，為每一次拳擊分析做好準備。")
        hero_text.setObjectName("authHeroText")
        hero_text.setWordWrap(True)
        intro_layout.addWidget(mark, 0)
        intro_layout.addStretch(1)
        intro_layout.addWidget(hero_title)
        intro_layout.addWidget(hero_text)

        form_panel = QFrame()
        form_layout = QVBoxLayout(form_panel)
        form_layout.setContentsMargins(28, 28, 28, 28)
        form_title = QLabel("登入或建立帳號")
        form_title.setObjectName("pageTitle")
        form_layout.addWidget(form_title)
        form_layout.addWidget(self.tabs)

        card = QFrame()
        card.setObjectName("authCard")
        self.card_layout = QHBoxLayout(card)
        self.card_layout.setContentsMargins(0, 0, 0, 0)
        self.card_layout.setSpacing(0)
        self.card_layout.addWidget(intro, 4)
        self.card_layout.addWidget(form_panel, 6)

        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(48, 42, 48, 42)
        self.root_layout.addStretch(1)
        self.root_layout.addWidget(card)
        self.root_layout.addStretch(1)
        self._compact = False

        self.login_username.setAccessibleName("登入 Username")
        self.login_password.setAccessibleName("登入密碼")
        self.register_username.setAccessibleName("註冊 Username")
        self.register_password.setAccessibleName("註冊密碼")

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

    def resizeEvent(self, event) -> None:
        compact = event.size().width() < 760
        if compact != self._compact:
            self._compact = compact
            self.card_layout.setDirection(
                QBoxLayout.Direction.TopToBottom
                if compact
                else QBoxLayout.Direction.LeftToRight
            )
            margins = 20 if compact else 48
            vertical_margin = 18 if compact else 42
            self.root_layout.setContentsMargins(
                margins,
                vertical_margin,
                margins,
                vertical_margin,
            )
            wrap_policy = (
                QFormLayout.RowWrapPolicy.WrapLongRows
                if compact
                else QFormLayout.RowWrapPolicy.DontWrapRows
            )
            for form in self._forms:
                form.setRowWrapPolicy(wrap_policy)
        super().resizeEvent(event)

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
