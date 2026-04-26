"""
split_tab.py - Tab for splitting a PDF by page or by custom ranges
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple, Optional
import re

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QMessageBox, QFrame, QButtonGroup, QRadioButton,
    QLineEdit, QGroupBox, QSizePolicy, QSpacerItem
)

from core.pdf_operations import split_pdf_by_page, split_pdf_by_ranges


def _parse_ranges(text: str, max_page: int) -> Optional[List[Tuple[int, int]]]:
    """
    Parse a range string like '1-3, 5, 7-10' into 0-indexed (start, end) tuples.
    Returns None on parse error.
    """
    ranges = []
    parts = [p.strip() for p in text.split(",") if p.strip()]
    for part in parts:
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if not m:
            return None
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else a
        if a < 1 or b > max_page or a > b:
            return None
        ranges.append((a - 1, b - 1))  # convert to 0-indexed
    return ranges if ranges else None


class SplitTab(QWidget):
    """Tab for splitting PDF by page or custom ranges."""

    status_message = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pdf_path: Optional[str] = None
        self._page_count: int = 0
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header
        header = QLabel("PDF 分割")
        header.setStyleSheet("font-size: 22px; font-weight: 700; color: #e8f0fe;")
        layout.addWidget(header)

        # File selection
        file_row = QHBoxLayout()
        self._file_label = QLabel("ファイル未選択")
        self._file_label.setStyleSheet("""
            background: #111827;
            border: 1px solid #2a3a50;
            border-radius: 8px;
            padding: 8px 14px;
            color: #7a8fa8;
            font-size: 13px;
        """)
        self._file_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        btn_select = QPushButton("📂  ファイルを選択")
        btn_select.clicked.connect(self._select_file)
        btn_select.setStyleSheet("""
            QPushButton {
                background: #1a2840;
                color: #c9d4e0;
                border: 1px solid #2a3a50;
                border-radius: 8px;
                padding: 8px 18px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton:hover { background: #243450; border-color: #3a5a80; }
        """)

        file_row.addWidget(self._file_label)
        file_row.addWidget(btn_select)
        layout.addLayout(file_row)

        # Info
        self._info_label = QLabel("")
        self._info_label.setStyleSheet("color: #5a7090; font-size: 12px;")
        layout.addWidget(self._info_label)

        # Split mode group
        mode_box = QGroupBox("分割モード")
        mode_box.setStyleSheet("""
            QGroupBox {
                color: #9ab0c8;
                font-size: 13px;
                font-weight: 600;
                border: 1px solid #2a3a50;
                border-radius: 10px;
                margin-top: 8px;
                padding-top: 16px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 4px; }
        """)
        mode_layout = QVBoxLayout(mode_box)
        mode_layout.setSpacing(12)

        self._radio_page = QRadioButton("ページごとに分割 (各ページを個別ファイルに)")
        self._radio_range = QRadioButton("範囲指定で分割")
        self._radio_page.setChecked(True)

        radio_style = """
            QRadioButton { color: #c9d4e0; font-size: 13px; spacing: 8px; }
            QRadioButton::indicator { width: 16px; height: 16px; }
            QRadioButton::indicator:checked { background: #4a9eff; border-radius: 8px; border: 2px solid #4a9eff; }
            QRadioButton::indicator:unchecked { background: #1a2840; border-radius: 8px; border: 2px solid #2a3a50; }
        """
        self._radio_page.setStyleSheet(radio_style)
        self._radio_range.setStyleSheet(radio_style)

        mode_layout.addWidget(self._radio_page)
        mode_layout.addWidget(self._radio_range)

        # Range input (shown only in range mode)
        range_row = QHBoxLayout()
        self._range_label = QLabel("範囲 (例: 1-3, 5, 7-10):")
        self._range_label.setStyleSheet("color: #9ab0c8; font-size: 13px;")
        self._range_input = QLineEdit()
        self._range_input.setPlaceholderText("1-3, 5, 7-10")
        self._range_input.setStyleSheet("""
            QLineEdit {
                background: #111827;
                border: 1px solid #2a3a50;
                border-radius: 8px;
                padding: 6px 12px;
                color: #c9d4e0;
                font-size: 13px;
            }
            QLineEdit:focus { border-color: #4a9eff; }
        """)
        range_row.addWidget(self._range_label)
        range_row.addWidget(self._range_input)
        mode_layout.addLayout(range_row)

        self._range_label.setEnabled(False)
        self._range_input.setEnabled(False)

        self._radio_range.toggled.connect(lambda checked: (
            self._range_label.setEnabled(checked),
            self._range_input.setEnabled(checked),
        ))

        layout.addWidget(mode_box)

        # Output directory
        out_row = QHBoxLayout()
        self._out_label = QLabel("出力先: 未指定（保存ダイアログで選択）")
        self._out_label.setStyleSheet("color: #5a7090; font-size: 12px;")
        layout.addWidget(self._out_label)

        layout.addStretch()

        # Action button
        self._btn_split = QPushButton("✂️  分割して保存")
        self._btn_split.clicked.connect(self._split)
        self._btn_split.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #0ea5e9, stop:1 #6366f1);
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 28px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #38bdf8, stop:1 #818cf8);
            }
            QPushButton:disabled { background: #2a3a50; color: #5a7090; }
        """)
        self._btn_split.setEnabled(False)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self._btn_split)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------

    def _select_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "分割するPDFを選択", "", "PDF Files (*.pdf)"
        )
        if not path:
            return
        import fitz
        doc = fitz.open(path)
        self._page_count = len(doc)
        doc.close()
        self._pdf_path = path
        self._file_label.setText(Path(path).name)
        self._file_label.setStyleSheet(self._file_label.styleSheet().replace(
            "color: #7a8fa8", "color: #c9d4e0"
        ))
        self._info_label.setText(f"ページ数: {self._page_count} ページ")
        self._btn_split.setEnabled(True)

    def _split(self):
        if not self._pdf_path:
            return

        if self._radio_page.isChecked():
            # Each page → separate file
            out_dir = QFileDialog.getExistingDirectory(
                self, "出力ディレクトリを選択"
            )
            if not out_dir:
                return
            try:
                paths = split_pdf_by_page(self._pdf_path, out_dir)
                self.status_message.emit(f"✅ 分割完了: {len(paths)} ファイル出力")
                QMessageBox.information(
                    self, "完了",
                    f"{len(paths)} ページを個別ファイルに分割しました:\n{out_dir}"
                )
            except Exception as e:
                QMessageBox.critical(self, "エラー", f"分割に失敗しました:\n{e}")

        else:
            # Range-based split
            raw = self._range_input.text().strip()
            if not raw:
                QMessageBox.warning(self, "警告", "範囲を入力してください。")
                return
            ranges = _parse_ranges(raw, self._page_count)
            if ranges is None:
                QMessageBox.warning(
                    self, "入力エラー",
                    f"範囲の形式が正しくありません。\n"
                    f"例: '1-3, 5, 7-10'（1〜{self._page_count}の範囲で指定）"
                )
                return

            out_dir = QFileDialog.getExistingDirectory(
                self, "出力ディレクトリを選択"
            )
            if not out_dir:
                return
            try:
                out_paths = split_pdf_by_ranges(self._pdf_path, ranges, out_dir)
                self.status_message.emit(f"✅ 分割完了: {len(out_paths)} ファイル出力")
                QMessageBox.information(
                    self, "完了",
                    f"{len(out_paths)} 個のファイルに分割しました:\n{out_dir}"
                )
            except Exception as e:
                QMessageBox.critical(self, "エラー", f"分割に失敗しました:\n{e}")
