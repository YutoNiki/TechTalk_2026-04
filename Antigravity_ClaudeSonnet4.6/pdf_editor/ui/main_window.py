"""
main_window.py - MainWindow with tab bar, sidebar navigation, and global styling
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QIcon, QFont, QPalette, QColor, QFontDatabase
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QStatusBar, QFrame,
    QSizePolicy, QApplication
)

from ui.merge_tab import MergeTab
from ui.split_tab import SplitTab
from ui.edit_tab import EditTab


SIDEBAR_WIDTH = 220

NAV_ITEMS = [
    ("🔗", "PDF 結合", "Merge"),
    ("✂️", "PDF 分割", "Split"),
    ("🗑️", "ページ削除", "Delete"),
    ("📄", "ページ抽出", "Extract"),
]

APP_STYLESHEET = """
QMainWindow, QWidget#centralWidget {
    background: #0a1018;
}

/* Sidebar */
QWidget#sidebar {
    background: #0d1520;
    border-right: 1px solid #1a2840;
}

/* Nav buttons */
QPushButton.navBtn {
    background: transparent;
    color: #7a8fa8;
    border: none;
    border-radius: 10px;
    text-align: left;
    padding: 10px 14px;
    font-size: 13px;
    font-weight: 500;
}
QPushButton.navBtn:hover {
    background: #1a2840;
    color: #c9d4e0;
}
QPushButton.navBtn[active=true] {
    background: #1e3a5f;
    color: #4a9eff;
}

/* Status bar */
QStatusBar {
    background: #0d1520;
    color: #5a7090;
    border-top: 1px solid #1a2840;
    font-size: 12px;
    padding: 2px 8px;
}

/* Content area */
QWidget#contentArea {
    background: #0a1018;
}

/* Tooltip */
QToolTip {
    background: #1a2840;
    color: #c9d4e0;
    border: 1px solid #2a3a50;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 12px;
}

/* ScrollArea background */
QScrollArea { background: transparent; }
"""


class NavButton(QPushButton):
    def __init__(self, icon_text: str, label: str, parent=None):
        super().__init__(parent)
        self._icon_text = icon_text
        self._label = label
        self._active = False
        self.setProperty("class", "navBtn")
        self.setCheckable(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(48)
        self._update_text()

    def _update_text(self):
        self.setText(f"  {self._icon_text}  {self._label}")

    def set_active(self, active: bool):
        self._active = active
        self.setProperty("active", "true" if active else "false")
        # Force style refresh
        self.style().unpolish(self)
        self.style().polish(self)
        self._update_style()

    def _update_style(self):
        if self._active:
            self.setStyleSheet("""
                QPushButton {
                    background: #1e3a5f;
                    color: #4a9eff;
                    border: none;
                    border-left: 3px solid #4a9eff;
                    border-radius: 0px;
                    text-align: left;
                    padding: 10px 14px;
                    font-size: 13px;
                    font-weight: 600;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #7a8fa8;
                    border: none;
                    border-radius: 0px;
                    text-align: left;
                    padding: 10px 17px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background: #1a2840;
                    color: #c9d4e0;
                }
            """)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Editor Pro")
        self.resize(1200, 780)
        self.setMinimumSize(900, 600)

        self._nav_buttons: list[NavButton] = []
        self._setup_ui()
        self._setup_status_bar()
        self._switch_to(0)

    def _setup_ui(self):
        self.setStyleSheet(APP_STYLESHEET)

        # Central widget
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)

        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Sidebar ──────────────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # Logo / title
        logo_frame = QFrame()
        logo_frame.setStyleSheet("background: #0d1520; border-bottom: 1px solid #1a2840;")
        logo_layout = QVBoxLayout(logo_frame)
        logo_layout.setContentsMargins(18, 20, 18, 20)
        logo_layout.setSpacing(4)

        logo_icon = QLabel("📑")
        logo_icon.setStyleSheet("font-size: 32px;")
        logo_label = QLabel("PDF Editor Pro")
        logo_label.setStyleSheet(
            "color: #e8f0fe; font-size: 16px; font-weight: 700; letter-spacing: 0.5px;"
        )
        tagline = QLabel("高機能PDF編集ツール")
        tagline.setStyleSheet("color: #4a6080; font-size: 11px;")

        logo_layout.addWidget(logo_icon)
        logo_layout.addWidget(logo_label)
        logo_layout.addWidget(tagline)
        sidebar_layout.addWidget(logo_frame)

        sidebar_layout.addSpacing(12)

        # Nav label
        nav_section = QLabel("  機能")
        nav_section.setStyleSheet(
            "color: #3a5060; font-size: 10px; font-weight: 700; "
            "letter-spacing: 1px; padding: 4px 0;"
        )
        sidebar_layout.addWidget(nav_section)

        # Nav buttons — only 3 shown; edit_tab covers both Delete & Extract
        nav_data = [
            ("🔗", "PDF 結合"),
            ("✂️", "PDF 分割"),
            ("✏️", "削除 / 抽出"),
        ]
        for icon, label in nav_data:
            btn = NavButton(icon, label)
            btn.clicked.connect(
                lambda checked, idx=len(self._nav_buttons): self._switch_to(idx)
            )
            sidebar_layout.addWidget(btn)
            self._nav_buttons.append(btn)

        sidebar_layout.addStretch()

        # Version footer
        ver_label = QLabel("  v1.0.0")
        ver_label.setStyleSheet("color: #2a3a50; font-size: 11px; padding: 12px 0;")
        sidebar_layout.addWidget(ver_label)

        root_layout.addWidget(sidebar)

        # ── Content area ──────────────────────────────────────────────
        content_area = QWidget()
        content_area.setObjectName("contentArea")
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: #0a1018;")

        self._merge_tab = MergeTab()
        self._split_tab = SplitTab()
        self._edit_tab = EditTab()

        self._merge_tab.status_message.connect(self._show_status)
        self._split_tab.status_message.connect(self._show_status)
        self._edit_tab.status_message.connect(self._show_status)

        self._stack.addWidget(self._merge_tab)
        self._stack.addWidget(self._split_tab)
        self._stack.addWidget(self._edit_tab)

        content_layout.addWidget(self._stack)
        root_layout.addWidget(content_area, 1)

    def _setup_status_bar(self):
        bar = QStatusBar()
        bar.setObjectName("statusBar")
        self.setStatusBar(bar)
        bar.showMessage("準備完了")

    def _switch_to(self, index: int):
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            btn.set_active(i == index)

    def _show_status(self, msg: str):
        self.statusBar().showMessage(msg, 8000)
