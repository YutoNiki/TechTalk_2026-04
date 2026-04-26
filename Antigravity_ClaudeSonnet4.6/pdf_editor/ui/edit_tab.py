"""
edit_tab.py - Combined Delete / Extract tab with thumbnail grid
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Set

import fitz
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QMessageBox, QFrame, QSizePolicy, QSplitter
)

from ui.thumbnail_widget import ThumbnailGrid
from core.pdf_operations import delete_pages, extract_pages


BTN_BASE = """
    QPushButton {{
        background: {bg};
        color: {fg};
        border: {border};
        border-radius: 8px;
        padding: 8px 20px;
        font-size: 13px;
        font-weight: 600;
    }}
    QPushButton:hover {{ background: {hover}; }}
    QPushButton:disabled {{ background: #1a2330; color: #3a5060; border-color: #1e2a3a; }}
"""


def _make_btn(label: str, bg: str, hover: str, fg: str = "white", border: str = "none") -> QPushButton:
    btn = QPushButton(label)
    btn.setStyleSheet(BTN_BASE.format(bg=bg, fg=fg, hover=hover, border=border))
    return btn


class EditTab(QWidget):
    """Tab for deleting or extracting selected pages from a PDF."""

    status_message = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_indices: List[int] = []
        self._pdf_path: Optional[str] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # Header row
        header_row = QHBoxLayout()
        header = QLabel("ページの削除・抽出")
        header.setStyleSheet("font-size: 22px; font-weight: 700; color: #e8f0fe;")
        header_row.addWidget(header)
        header_row.addStretch()

        # Open file button
        self._btn_open = _make_btn(
            "📂  PDFを開く",
            bg="#1a2840", hover="#243450", fg="#c9d4e0",
            border="1px solid #2a3a50"
        )
        self._btn_open.clicked.connect(self._open_file)
        header_row.addWidget(self._btn_open)
        layout.addLayout(header_row)

        # Sub-description
        self._desc = QLabel(
            "PDFをドラッグ＆ドロップするか「PDFを開く」で読み込んでください。\n"
            "クリック（Ctrl/Shift 併用で範囲選択）でページを選択し、削除または抽出できます。"
        )
        self._desc.setStyleSheet("color: #7a8fa8; font-size: 13px;")
        self._desc.setWordWrap(True)
        layout.addWidget(self._desc)

        # File info bar
        self._file_bar = QFrame()
        self._file_bar.setStyleSheet("""
            QFrame {
                background: #111827;
                border: 1px solid #1e2a3a;
                border-radius: 8px;
                padding: 4px;
            }
        """)
        file_bar_layout = QHBoxLayout(self._file_bar)
        file_bar_layout.setContentsMargins(12, 6, 12, 6)

        self._file_name_label = QLabel("ファイル未読込")
        self._file_name_label.setStyleSheet("color: #7a8fa8; font-size: 13px;")
        self._page_count_label = QLabel("")
        self._page_count_label.setStyleSheet("color: #4a9eff; font-size: 13px; font-weight: 600;")
        self._selection_label = QLabel("選択: なし")
        self._selection_label.setStyleSheet("color: #f59e0b; font-size: 13px;")

        file_bar_layout.addWidget(self._file_name_label)
        file_bar_layout.addStretch()
        file_bar_layout.addWidget(self._page_count_label)
        file_bar_layout.addSpacing(20)
        file_bar_layout.addWidget(self._selection_label)
        layout.addWidget(self._file_bar)

        # Select all / deselect all row
        sel_row = QHBoxLayout()
        self._btn_select_all = _make_btn(
            "全選択", bg="#1a2840", hover="#243450",
            fg="#c9d4e0", border="1px solid #2a3a50"
        )
        self._btn_select_all.clicked.connect(self._select_all)
        self._btn_deselect = _make_btn(
            "選択解除", bg="#1a2840", hover="#243450",
            fg="#c9d4e0", border="1px solid #2a3a50"
        )
        self._btn_deselect.clicked.connect(self._deselect_all)
        self._btn_invert = _make_btn(
            "選択反転", bg="#1a2840", hover="#243450",
            fg="#c9d4e0", border="1px solid #2a3a50"
        )
        self._btn_invert.clicked.connect(self._invert_selection)

        for b in [self._btn_select_all, self._btn_deselect, self._btn_invert]:
            sel_row.addWidget(b)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        # Thumbnail grid – fills remaining space
        self._grid = ThumbnailGrid()
        self._grid.setStyleSheet("background: #0d1520; border-radius: 12px;")
        self._grid.selection_changed.connect(self._on_selection_changed)
        self._grid.setAcceptDrops(True)
        layout.addWidget(self._grid, 1)

        # Action buttons
        action_row = QHBoxLayout()
        action_row.addStretch()

        self._btn_delete = _make_btn(
            "🗑️  選択ページを削除",
            bg="#7f1d1d", hover="#991b1b", fg="white"
        )
        self._btn_delete.clicked.connect(self._delete_pages)
        self._btn_delete.setEnabled(False)

        self._btn_extract = _make_btn(
            "📄  選択ページを抽出",
            bg="qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #059669,stop:1 #0891b2)",
            hover="qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #10b981,stop:1 #06b6d4)",
        )
        self._btn_extract.clicked.connect(self._extract_pages)
        self._btn_extract.setEnabled(False)

        action_row.addWidget(self._btn_delete)
        action_row.addSpacing(12)
        action_row.addWidget(self._btn_extract)
        layout.addLayout(action_row)

        # Accept drops on the EditTab level too
        self.setAcceptDrops(True)

    # ------------------------------------------------------------------
    # Drop support – open PDF dragged from e.g. file explorer
    # ------------------------------------------------------------------

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    return

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pdf"):
                self._load_pdf(path)
                break

    # ------------------------------------------------------------------

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "PDFを開く", "", "PDF Files (*.pdf)"
        )
        if path:
            self._load_pdf(path)

    def _load_pdf(self, path: str):
        self._pdf_path = path
        self._file_name_label.setText(Path(path).name)
        self._file_name_label.setStyleSheet("color: #c9d4e0; font-size: 13px;")
        self._grid.load_pdf(path)
        import fitz
        doc = fitz.open(path)
        n = len(doc)
        doc.close()
        self._page_count_label.setText(f"全 {n} ページ")
        self._selection_label.setText("選択: なし")
        self._selected_indices = []
        self._update_action_buttons()

    def _on_selection_changed(self, indices: List[int]):
        self._selected_indices = indices
        if indices:
            self._selection_label.setText(f"選択: {len(indices)} ページ")
        else:
            self._selection_label.setText("選択: なし")
        self._update_action_buttons()

    def _update_action_buttons(self):
        has_sel = bool(self._selected_indices)
        has_pdf = self._pdf_path is not None
        self._btn_delete.setEnabled(has_sel and has_pdf)
        self._btn_extract.setEnabled(has_sel and has_pdf)
        self._btn_select_all.setEnabled(has_pdf)
        self._btn_deselect.setEnabled(has_pdf)
        self._btn_invert.setEnabled(has_pdf)

    def _select_all(self):
        # Simulate clicking all cards
        if self._grid._doc is None:
            return
        all_indices = list(range(self._grid.page_count()))
        self._grid._selected = set(self._grid.get_display_order())
        self._grid._refresh_selection_visuals()
        self._grid.selection_changed.emit(sorted(self._grid._selected))

    def _deselect_all(self):
        self._grid._selected.clear()
        self._grid._refresh_selection_visuals()
        self._grid.selection_changed.emit([])

    def _invert_selection(self):
        all_orig = set(self._grid.get_display_order())
        self._grid._selected = all_orig - self._grid._selected
        self._grid._refresh_selection_visuals()
        self._grid.selection_changed.emit(sorted(self._grid._selected))

    # ------------------------------------------------------------------

    def _delete_pages(self):
        if not self._pdf_path or not self._selected_indices:
            return

        n = len(self._selected_indices)
        reply = QMessageBox.question(
            self, "確認",
            f"選択した {n} ページを削除しますか？\n（削除後、別ファイルとして保存します）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        stem = Path(self._pdf_path).stem
        out_path, _ = QFileDialog.getSaveFileName(
            self, "保存先を選択", f"{stem}_deleted.pdf", "PDF Files (*.pdf)"
        )
        if not out_path:
            return

        try:
            delete_pages(self._pdf_path, self._selected_indices, out_path)
            self.status_message.emit(f"✅ 削除完了: {Path(out_path).name}")
            reply2 = QMessageBox.information(
                self, "完了",
                f"{n} ページを削除して保存しました:\n{out_path}\n\n新しいファイルを読み込みますか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply2 == QMessageBox.StandardButton.Yes:
                self._load_pdf(out_path)
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"削除に失敗しました:\n{e}")

    def _extract_pages(self):
        if not self._pdf_path or not self._selected_indices:
            return

        n = len(self._selected_indices)
        stem = Path(self._pdf_path).stem
        out_path, _ = QFileDialog.getSaveFileName(
            self, "抽出PDFを保存", f"{stem}_extracted.pdf", "PDF Files (*.pdf)"
        )
        if not out_path:
            return

        try:
            extract_pages(self._pdf_path, self._selected_indices, out_path)
            self.status_message.emit(f"✅ 抽出完了: {Path(out_path).name}")
            QMessageBox.information(
                self, "完了",
                f"{n} ページを抽出して保存しました:\n{out_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"抽出に失敗しました:\n{e}")
