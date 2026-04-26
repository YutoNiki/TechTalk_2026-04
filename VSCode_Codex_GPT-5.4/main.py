from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import fitz
from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QIcon, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)


THUMBNAIL_WIDTH = 180
THUMBNAIL_HEIGHT = 240


@dataclass(frozen=True)
class PageRef:
    file_path: str
    page_index: int
    source_name: str


def render_page_thumbnail(file_path: str, page_index: int) -> QIcon:
    doc = fitz.open(file_path)
    try:
        page = doc.load_page(page_index)
        pix = page.get_pixmap(matrix=fitz.Matrix(0.35, 0.35), alpha=False)
    finally:
        doc.close()

    image = QImage(
        pix.samples,
        pix.width,
        pix.height,
        pix.stride,
        QImage.Format.Format_RGB888,
    ).copy()

    scaled = image.scaled(
        THUMBNAIL_WIDTH - 24,
        THUMBNAIL_HEIGHT - 50,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    canvas = QPixmap(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT)
    canvas.fill(QColor("#f4f6fb"))

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor("#d8dee9"))
    painter.setBrush(QColor("#ffffff"))
    painter.drawRoundedRect(10, 10, THUMBNAIL_WIDTH - 20, THUMBNAIL_HEIGHT - 42, 10, 10)

    x = (THUMBNAIL_WIDTH - scaled.width()) // 2
    y = 18
    painter.drawImage(x, y, scaled)
    painter.end()
    return QIcon(canvas)


def parse_range_token(token: str, max_page: int) -> list[int]:
    token = token.strip()
    if not token:
        return []
    if "-" in token:
        start_text, end_text = token.split("-", 1)
        start = int(start_text)
        end = int(end_text)
        if start < 1 or end < 1 or start > max_page or end > max_page or start > end:
            raise ValueError(f"Invalid range: {token}")
        return list(range(start - 1, end))
    page = int(token)
    if page < 1 or page > max_page:
        raise ValueError(f"Invalid page: {token}")
    return [page - 1]


def parse_grouped_ranges(text: str, max_page: int) -> list[list[int]]:
    groups: list[list[int]] = []
    for group_text in text.split(";"):
        indices: list[int] = []
        seen: set[int] = set()
        for token in group_text.split(","):
            for index in parse_range_token(token, max_page):
                if index not in seen:
                    indices.append(index)
                    seen.add(index)
        if indices:
            groups.append(indices)
    if not groups:
        raise ValueError("No valid page ranges were provided.")
    return groups


class ThumbnailListWidget(QListWidget):
    files_dropped = pyqtSignal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setMovement(QListWidget.Movement.Snap)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setIconSize(QSize(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT))
        self.setGridSize(QSize(THUMBNAIL_WIDTH + 28, THUMBNAIL_HEIGHT + 44))
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setAcceptDrops(True)
        self.setSpacing(14)
        self.setStyleSheet(
            """
            QListWidget {
                background: #f7f9fc;
                border: 1px solid #d6deeb;
                border-radius: 18px;
                padding: 14px;
            }
            QListWidget::item {
                border: 1px solid transparent;
                border-radius: 14px;
                padding: 6px;
                color: #263245;
            }
            QListWidget::item:selected {
                background: #dceeff;
                border: 1px solid #5da7ff;
            }
            """
        )

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            paths = []
            for url in event.mimeData().urls():
                local = url.toLocalFile()
                if local.lower().endswith(".pdf"):
                    paths.append(local)
            if paths:
                self.files_dropped.emit(paths)
                event.acceptProposedAction()
                return
        super().dropEvent(event)


class PdfEditorWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PDF Studio Desk")
        self.resize(1280, 820)
        self._setup_ui()
        self._setup_actions()
        self._update_state()

    def _setup_ui(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: #edf2f8;
            }
            QLabel#titleLabel {
                color: #132238;
                font-size: 28px;
                font-weight: 700;
            }
            QLabel#subtitleLabel {
                color: #607086;
                font-size: 14px;
            }
            QFrame#sidePanel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #16324f, stop:1 #234f7d);
                border-radius: 22px;
            }
            QLabel#panelTitle {
                color: white;
                font-size: 18px;
                font-weight: 700;
            }
            QLabel#panelText {
                color: #dce9f7;
                font-size: 13px;
            }
            QPushButton {
                background: #ffffff;
                color: #16324f;
                border: none;
                border-radius: 12px;
                padding: 12px 14px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #e7f1fb;
            }
            QPushButton:disabled {
                background: #b3c0ce;
                color: #f4f7fb;
            }
            """
        )

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("PDF Studio Desk")
        title.setObjectName("titleLabel")
        subtitle = QLabel("ドラッグ&ドロップとサムネイル操作で、結合・分割・削除・抽出をひとつに。")
        subtitle.setObjectName("subtitleLabel")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()
        root.addLayout(header)

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)

        side_panel = QFrame()
        side_panel.setObjectName("sidePanel")
        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(22, 22, 22, 22)
        side_layout.setSpacing(12)

        panel_title = QLabel("Quick Actions")
        panel_title.setObjectName("panelTitle")
        panel_text = QLabel("サムネイルの順序がそのまま出力順になります。Shift/Ctrl で複数ページ選択できます。")
        panel_text.setWordWrap(True)
        panel_text.setObjectName("panelText")
        side_layout.addWidget(panel_title)
        side_layout.addWidget(panel_text)

        self.open_button = QPushButton("PDFを追加")
        self.merge_button = QPushButton("現在の並びで結合保存")
        self.extract_button = QPushButton("選択ページを抽出")
        self.delete_button = QPushButton("選択ページを削除")
        self.split_button = QPushButton("分割して保存")
        self.clear_button = QPushButton("一覧をクリア")

        for button in (
            self.open_button,
            self.merge_button,
            self.extract_button,
            self.delete_button,
            self.split_button,
            self.clear_button,
        ):
            side_layout.addWidget(button)
        side_layout.addStretch()

        self.stats_label = QLabel("PDF未読込")
        self.stats_label.setObjectName("panelText")
        self.stats_label.setWordWrap(True)
        side_layout.addWidget(self.stats_label)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        self.drop_hint = QLabel("ここにPDFをドロップするか、「PDFを追加」を選択してください。")
        self.drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_hint.setStyleSheet(
            """
            QLabel {
                background: #ffffff;
                border: 1px dashed #7ba8d9;
                color: #47617f;
                border-radius: 18px;
                padding: 18px;
                font-size: 15px;
            }
            """
        )
        content_layout.addWidget(self.drop_hint)

        self.thumbnail_list = ThumbnailListWidget()
        content_layout.addWidget(self.thumbnail_list, 1)

        splitter.addWidget(side_panel)
        splitter.addWidget(content)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 900])

        root.addWidget(splitter, 1)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())

    def _setup_actions(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        add_action = QAction("追加", self)
        add_action.triggered.connect(self.add_pdfs)
        toolbar.addAction(add_action)

        merge_action = QAction("結合", self)
        merge_action.triggered.connect(self.merge_all_pages)
        toolbar.addAction(merge_action)

        extract_action = QAction("抽出", self)
        extract_action.triggered.connect(self.extract_selected_pages)
        toolbar.addAction(extract_action)

        self.open_button.clicked.connect(self.add_pdfs)
        self.merge_button.clicked.connect(self.merge_all_pages)
        self.extract_button.clicked.connect(self.extract_selected_pages)
        self.delete_button.clicked.connect(self.delete_selected_pages)
        self.split_button.clicked.connect(self.split_pdf)
        self.clear_button.clicked.connect(self.clear_all_pages)
        self.thumbnail_list.files_dropped.connect(self.load_pdf_files)
        self.thumbnail_list.itemSelectionChanged.connect(self._update_state)
        model = self.thumbnail_list.model()
        if model is not None:
            model.rowsMoved.connect(lambda *_: self._update_state())

    def add_pdfs(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "PDFを選択",
            "",
            "PDF Files (*.pdf)",
        )
        if files:
            self.load_pdf_files(files)

    def load_pdf_files(self, files: Iterable[str]) -> None:
        added_pages = 0
        for file_path in files:
            path = Path(file_path)
            if not path.exists():
                continue
            try:
                doc = fitz.open(str(path))
                page_count = doc.page_count
                doc.close()
            except Exception as exc:  # noqa: BLE001
                self._show_error(f"{path.name} を開けませんでした。\n{exc}")
                continue

            for page_index in range(page_count):
                ref = PageRef(str(path), page_index, path.name)
                item = QListWidgetItem(
                    render_page_thumbnail(ref.file_path, ref.page_index),
                    f"{ref.source_name}\nPage {page_index + 1}",
                )
                item.setData(Qt.ItemDataRole.UserRole, ref)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.thumbnail_list.addItem(item)
                added_pages += 1

        if added_pages:
            self.statusBar().showMessage(f"{added_pages} ページを追加しました。", 4000)
        self._update_state()

    def _iter_page_refs(self, selected_only: bool = False) -> list[PageRef]:
        refs: list[PageRef] = []
        items = self.thumbnail_list.selectedItems() if selected_only else [
            self.thumbnail_list.item(i) for i in range(self.thumbnail_list.count())
        ]
        for item in items:
            ref = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(ref, PageRef):
                refs.append(ref)
        return refs

    def _export_pages(self, page_refs: list[PageRef], output_path: str) -> None:
        out_doc = fitz.open()
        opened_docs: dict[str, fitz.Document] = {}
        try:
            for ref in page_refs:
                if ref.file_path not in opened_docs:
                    opened_docs[ref.file_path] = fitz.open(ref.file_path)
                source_doc = opened_docs[ref.file_path]
                out_doc.insert_pdf(source_doc, from_page=ref.page_index, to_page=ref.page_index)
            out_doc.save(output_path, garbage=4, deflate=True)
        finally:
            out_doc.close()
            for doc in opened_docs.values():
                doc.close()

    def merge_all_pages(self) -> None:
        page_refs = self._iter_page_refs()
        if not page_refs:
            self._show_info("結合するPDFがありません。")
            return
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "結合PDFを保存",
            "merged.pdf",
            "PDF Files (*.pdf)",
        )
        if not output_path:
            return
        try:
            self._export_pages(page_refs, output_path)
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"結合に失敗しました。\n{exc}")
            return
        self.statusBar().showMessage("結合PDFを保存しました。", 5000)

    def extract_selected_pages(self) -> None:
        page_refs = self._iter_page_refs(selected_only=True)
        if not page_refs:
            self._show_info("抽出したいページを選択してください。")
            return
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "抽出PDFを保存",
            "extracted.pdf",
            "PDF Files (*.pdf)",
        )
        if not output_path:
            return
        try:
            self._export_pages(page_refs, output_path)
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"抽出に失敗しました。\n{exc}")
            return
        self.statusBar().showMessage("抽出PDFを保存しました。", 5000)

    def delete_selected_pages(self) -> None:
        selected_rows = sorted(
            {self.thumbnail_list.row(item) for item in self.thumbnail_list.selectedItems()},
            reverse=True,
        )
        if not selected_rows:
            self._show_info("削除したいページを選択してください。")
            return
        for row in selected_rows:
            self.thumbnail_list.takeItem(row)
        self.statusBar().showMessage(f"{len(selected_rows)} ページを一覧から削除しました。", 4000)
        self._update_state()

    def split_pdf(self) -> None:
        page_refs = self._iter_page_refs()
        if not page_refs:
            self._show_info("分割対象のPDFがありません。")
            return

        mode, ok = QInputDialog.getItem(
            self,
            "分割方法",
            "分割方法を選択してください。",
            ["ページごとに分割", "範囲指定で分割"],
            0,
            False,
        )
        if not ok:
            return

        output_dir = QFileDialog.getExistingDirectory(self, "保存先フォルダを選択")
        if not output_dir:
            return

        output_path = Path(output_dir)

        try:
            if mode == "ページごとに分割":
                for idx, ref in enumerate(page_refs, start=1):
                    file_name = f"page_{idx:03d}.pdf"
                    self._export_pages([ref], str(output_path / file_name))
            else:
                range_text, ok = QInputDialog.getText(
                    self,
                    "範囲指定",
                    "例: 1-3;4-6;7,8\nセミコロン区切りで複数PDFを作成します。",
                )
                if not ok or not range_text.strip():
                    return
                groups = parse_grouped_ranges(range_text, len(page_refs))
                for idx, group in enumerate(groups, start=1):
                    refs = [page_refs[index] for index in group]
                    file_name = f"split_{idx:03d}.pdf"
                    self._export_pages(refs, str(output_path / file_name))
        except Exception as exc:  # noqa: BLE001
            self._show_error(f"分割に失敗しました。\n{exc}")
            return

        self.statusBar().showMessage("分割PDFを保存しました。", 5000)

    def clear_all_pages(self) -> None:
        self.thumbnail_list.clear()
        self._update_state()
        self.statusBar().showMessage("一覧をクリアしました。", 3000)

    def _update_state(self) -> None:
        total_pages = self.thumbnail_list.count()
        selected_pages = len(self.thumbnail_list.selectedItems())
        has_pages = total_pages > 0
        has_selection = selected_pages > 0

        self.merge_button.setEnabled(has_pages)
        self.split_button.setEnabled(has_pages)
        self.clear_button.setEnabled(has_pages)
        self.extract_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)

        self.drop_hint.setVisible(not has_pages)
        self.stats_label.setText(
            f"総ページ数: {total_pages}\n選択ページ数: {selected_pages}\nドラッグで並べ替え可能"
        )

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Error", message)

    def _show_info(self, message: str) -> None:
        QMessageBox.information(self, "Info", message)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PDF Studio Desk")
    window = PdfEditorWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
