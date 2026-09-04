"""Small reusable building blocks for BAP pages."""

from __future__ import annotations

from PySide6.QtWidgets import QBoxLayout, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class PageHeader(QWidget):
    """A consistent page title, description, and optional action area."""

    def __init__(self, title: str, subtitle: str = "", parent=None) -> None:
        super().__init__(parent)
        self.title = QLabel(title)
        self.title.setObjectName("pageTitle")
        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("pageSubtitle")
        self.subtitle.setWordWrap(True)
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)
        text_layout.addWidget(self.title)
        if subtitle:
            text_layout.addWidget(self.subtitle)

        self.actions = QHBoxLayout()
        self.actions.setContentsMargins(0, 0, 0, 0)
        self.actions.setSpacing(8)
        self.root_layout = QHBoxLayout(self)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(18)
        self.root_layout.addLayout(text_layout, 1)
        self.root_layout.addLayout(self.actions)
        self._compact = False

    def add_action(self, widget: QWidget) -> None:
        self.actions.addWidget(widget)

    def resizeEvent(self, event) -> None:
        """Place actions below the title when horizontal room is limited."""

        compact = event.size().width() < 620
        if compact != self._compact:
            self._compact = compact
            self.root_layout.setDirection(
                QBoxLayout.Direction.TopToBottom
                if compact
                else QBoxLayout.Direction.LeftToRight
            )
            self.root_layout.setSpacing(10 if compact else 18)
        super().resizeEvent(event)


class Card(QFrame):
    """A simple opaque content surface shared by overview and setup pages."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("card", True)
