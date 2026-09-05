"""Shared BAP visual language for the PySide6 Desktop App."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication


BAP_STYLESHEET = """
QMainWindow, QWidget#appRoot, QWidget#authenticatedShell, QScrollArea#contentScroll {
    background: #F5F7F8;
    color: #182027;
    font-family: "Segoe UI", "Noto Sans TC", sans-serif;
    font-size: 14px;
}
QWidget#authPage { background: #EEF1F3; }
QFrame#authCard, QFrame[card="true"], QFrame#topBar {
    background: #FFFFFF;
    border: 1px solid #DBE0E3;
    border-radius: 12px;
}
QFrame#authIntro, QFrame#sidebar { background: #20272D; color: #EAF0F2; border: 0; }
QFrame#topBar { border-radius: 0; border-left: 0; border-right: 0; border-top: 0; }
QLabel#brandMark {
    color: #FFFFFF;
    background: #BC2331;
    border-radius: 7px;
    padding: 6px;
    font-weight: 600;
}
QLabel#brandTitle, QLabel#authHeroTitle { color: #FFFFFF; font-size: 20px; font-weight: 600; }
QLabel#brandSubtitle, QLabel#authHeroText { color: #AEB8BD; }
QLabel#pageTitle { font-size: 24px; font-weight: 600; color: #182027; }
QLabel#pageSubtitle, QLabel[muted="true"] { color: #66727B; }
QLabel#sectionTitle { font-size: 16px; font-weight: 600; }
QLabel#pageName { font-weight: 600; }
QLabel#statusChip {
    color: #356646;
    background: #E3F4E8;
    border-radius: 10px;
    padding: 5px 9px;
}
QLabel#pendingChip {
    color: #795D16;
    background: #F7EDCE;
    border-radius: 10px;
    padding: 4px 8px;
}
QLabel#errorMessage { color: #A91F2B; }
QLabel#warningMessage {
    color: #6B571D;
    background: #FBF6E8;
    border-left: 3px solid #C59224;
    padding: 9px;
}
QPushButton {
    min-height: 38px;
    padding: 7px 13px;
    border-radius: 8px;
    border: 1px solid #CBD2D6;
    background: #FFFFFF;
    color: #182027;
}
QPushButton:hover { background: #F1F3F4; }
QPushButton:focus, QLineEdit:focus, QComboBox:focus, QTabBar::tab:focus {
    border: 2px solid #1769AA;
}
QPushButton:disabled { color: #929A9F; background: #E7EAED; border-color: #D8DDE0; }
QPushButton[role="primary"] { color: #FFFFFF; background: #BC2331; border-color: #BC2331; font-weight: 600; }
QPushButton[role="primary"]:hover { background: #A91F2B; }
QPushButton[role="secondary"] { background: #FFFFFF; border-color: #CBD2D6; }
QPushButton[role="card"] {
    min-height: 112px;
    padding: 16px;
    text-align: left;
    background: #FFFFFF;
    border: 1px solid #DBE0E3;
    font-weight: 600;
}
QPushButton[role="card"]:hover { border-color: #AEB8BD; background: #FAFBFB; }
QPushButton[nav="true"] {
    color: #CBD3D7;
    background: transparent;
    border: 0;
    text-align: left;
    padding: 9px 11px;
}
QPushButton[nav="true"]:hover { color: #FFFFFF; background: #30383E; }
QPushButton[nav="true"]:checked { color: #FFFFFF; background: #3B444B; border-left: 3px solid #E6535F; }
QLineEdit, QComboBox {
    min-height: 40px;
    padding: 5px 9px;
    background: #FFFFFF;
    color: #182027;
    border: 1px solid #CBD2D6;
    border-radius: 7px;
}
QTabWidget::pane { border: 0; }
QTabBar::tab { padding: 9px 15px; color: #66727B; background: transparent; }
QTabBar::tab:selected { color: #182027; background: #EDF0F2; border-radius: 7px; }
QProgressBar { min-height: 8px; max-height: 8px; border: 0; border-radius: 4px; background: #E7EBED; text-align: center; }
QProgressBar::chunk { border-radius: 4px; background: #BC2331; }
QProgressBar#diagnosticProgress {
    min-height: 26px;
    max-height: 26px;
    color: #182027;
    font-weight: 600;
}
QProgressBar#diagnosticProgress::chunk { border-radius: 4px; background: #E6535F; }
QTableWidget { background: #FFFFFF; border: 1px solid #DBE0E3; border-radius: 10px; gridline-color: #E4E8EA; }
QHeaderView::section { background: #F7F8F9; color: #66727B; padding: 9px; border: 0; border-bottom: 1px solid #DBE0E3; }
QScrollArea { border: 0; }
"""


def apply_bap_style(app: QApplication | None) -> None:
    """Apply the local stylesheet once without any network dependency."""

    if app is not None and app.property("bapStyleApplied") is not True:
        app.setStyleSheet(BAP_STYLESHEET)
        app.setProperty("bapStyleApplied", True)
