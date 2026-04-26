"""
merge_tab.py - Tab for merging multiple PDFs with drag-and-drop reordering
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple
import fitz

from PyQt6.QtCore import Qt, QMimeData, QPoint, QByteArray, pyqtSignal, QSize
from PyQt6.QtGui import QDrag, QPixmap, QImage, QDragEnterEvent, QDropEvent, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox,
    QScrollArea, QFrame, QSizePolicy, QAbstractItemView, QProgressDialog
)

from core.pdf_operations import merge_pdfs_with_order, render_page_thumbnail


class FileListItem(QListWidgetItem):
    def __init__(self, path: str):
        super().__init__()
        self.pdf_path = path
        name = Path(path).name
        self.setText(f"  {name}")
        self.setToolTip(path)
        self.setSizeHint(QSize(0, 44))


class MergeTab(QWidget):
    """
    Drag-and-drop zone for adding PDFs.
    Displays a file list that can be reordered by dragging.
    On 'Merge & Save', concatenates all PDFs in list order.
    """

    status_message = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pdf_paths: List[str] = []
        self._setup_ui()
        self.setAcceptDrops(True)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header
        header = QLabel("PDF 結合")
        header.setStyleSheet("font-size: 22px; font-weight: 700; color: #e8f0fe;")
        layout.addWidget(header)

        desc = QLabel(
            "PDFファイルをここにドラッグ＆ドロップするか「ファイルを追加」から選択してください。\n"
            "リスト内でドラッグして順序を変更できます。"
        )
        desc.setStyleSheet("color: #7a8fa8; font-size: 13px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Drop zone / file list
        self._list = QListWidget()
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.setAlternatingRowColors(False)
        self._list.setStyleSheet("""
            QListWidget {
                background: #111827;
                border: 2px dashed #2a3a50;
                border-radius: 12px;
                color: #c9d4e0;
                font-size: 13px;
                outline: none;
            }
            QListWidget::item {
                border-bottom: 1px solid #1e2a3a;
                padding: 4px 8px;
            }
            QListWidget::item:selected {
                background: #1e3a5f;
                color: #4a9eff;
            }
            QListWidget::item:hover:!selected {
                background: #1a2840;
            }
        """)
        self._list.setMinimumHeight(220)

        # Placeholder text
        self._placeholder = QLabel("ここにPDFをドロップ\nまたは下の「ファイルを追加」ボタンをクリック")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("color: #3a5070; font-size: 15px;")
        self._placeholder.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        drop_frame = QFrame()
        drop_frame.setStyleSheet("background: transparent;")
        drop_layout = QVBoxLayout(drop_frame)
        drop_layout.setContentsMargins(0, 0, 0, 0)
        drop_layout.addWidget(self._list)

        layout.addWidget(drop_frame, 1)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._btn_add = QPushButton("＋  ファイルを追加")
        self._btn_add.clicked.connect(self._add_files)

        self._btn_remove = QPushButton("－  選択を削除")
        self._btn_remove.clicked.connect(self._remove_selected)

        self._btn_clear = QPushButton("クリア")
        self._btn_clear.clicked.connect(self._clear_list)

        self._btn_merge = QPushButton("🔗  結合して保存")
        self._btn_merge.setObjectName("primaryBtn")
        self._btn_merge.clicked.connect(self._merge)

        for btn in [self._btn_add, self._btn_remove, self._btn_clear]:
            btn.setStyleSheet("""
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
                QPushButton:pressed { background: #1a2030; }
            """)

        self._btn_merge.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #2563eb, stop:1 #7c3aed);
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 24px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #3b82f6, stop:1 #8b5cf6);
            }
            QPushButton:pressed { opacity: 0.85; }
        """)

        btn_row.addWidget(self._btn_add)
        btn_row.addWidget(self._btn_remove)
        btn_row.addWidget(self._btn_clear)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_merge)
        layout.addLayout(btn_row)

        # Info label
        self._info_label = QLabel("ファイルが追加されていません")
        self._info_label.setStyleSheet("color: #5a7090; font-size: 12px; padding-top: 4px;")
        layout.addWidget(self._info_label)

    # ------------------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pdf"):
                self._add_path(path)
        self._update_info()

    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "PDFファイルを選択", "", "PDF Files (*.pdf)"
        )
        for p in paths:
            self._add_path(p)
        self._update_info()

    def _add_path(self, path: str):
        for row in range(self._list.count()):
            if self._list.item(row).toolTip() == path:
                return  # already in list
        item = FileListItem(path)
        self._list.addItem(item)

    def _remove_selected(self):
        for item in self._list.selectedItems():
            self._list.takeItem(self._list.row(item))
        self._update_info()

    def _clear_list(self):
        self._list.clear()
        self._update_info()

    def _update_info(self):
        n = self._list.count()
        if n == 0:
            self._info_label.setText("ファイルが追加されていません")
        else:
            self._info_label.setText(f"{n} 件のPDFが追加されています")

    def _get_ordered_paths(self) -> List[str]:
        paths = []
        for row in range(self._list.count()):
            paths.append(self._list.item(row).toolTip())
        return paths

    def _merge(self):
        paths = self._get_ordered_paths()
        if len(paths) < 2:
            QMessageBox.warning(self, "警告", "結合するには2つ以上のPDFが必要です。")
            return

        out_path, _ = QFileDialog.getSaveFileName(
            self, "結合PDFを保存", "merged.pdf", "PDF Files (*.pdf)"
        )
        if not out_path:
            return

        try:
            from core.pdf_operations import merge_pdfs
            merge_pdfs(paths, out_path)
            self.status_message.emit(f"✅ 結合完了: {Path(out_path).name}")
            QMessageBox.information(self, "完了", f"PDFを結合して保存しました:\n{out_path}")
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"結合に失敗しました:\n{e}")
