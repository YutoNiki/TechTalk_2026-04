from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QRadioButton,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from pdf_ops import (
    PDFOpsError,
    PDFPageRef,
    extract_selected_pages,
    load_pages_from_pdf,
    parse_page_ranges,
    render_thumbnail,
    save_pages_as_pdf,
    split_by_ranges,
    split_to_individual_pages,
)


class PageListWidget(QListWidget):
    files_dropped = pyqtSignal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setWrapping(True)
        self.setSpacing(16)
        self.setIconSize(QSize(180, 240))
        self.setMovement(QListWidget.Movement.Snap)
        self.setFrameShape(QFrame.Shape.NoFrame)

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
                local_path = url.toLocalFile()
                if local_path.lower().endswith(".pdf"):
                    paths.append(local_path)
            if paths:
                self.files_dropped.emit(paths)
                event.acceptProposedAction()
                return
        super().dropEvent(event)


class SplitDialog(QDialog):
    def __init__(self, page_count: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Split PDF")
        self.setModal(True)

        layout = QVBoxLayout(self)
        intro = QLabel(
            f"Choose how to split the current {page_count}-page document."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.each_page_radio = QRadioButton("Split into one file per page")
        self.range_radio = QRadioButton("Split by page ranges")
        self.each_page_radio.setChecked(True)

        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.each_page_radio)
        self.mode_group.addButton(self.range_radio)

        layout.addWidget(self.each_page_radio)
        layout.addWidget(self.range_radio)

        self.range_input = QLineEdit()
        self.range_input.setPlaceholderText("Example: 1-3, 4-6, 7")
        self.range_input.setEnabled(False)
        layout.addWidget(self.range_input)

        help_label = QLabel("Ranges are 1-based and inclusive.")
        help_label.setStyleSheet("color: #6b7280;")
        layout.addWidget(help_label)

        self.each_page_radio.toggled.connect(self._update_enabled_state)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.resize(420, 180)

    def _update_enabled_state(self) -> None:
        self.range_input.setEnabled(self.range_radio.isChecked())

    def values(self) -> tuple[str, str]:
        mode = "each" if self.each_page_radio.isChecked() else "ranges"
        return mode, self.range_input.text().strip()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PDF Studio")
        self.resize(1180, 760)

        self.page_list = PageListWidget()
        self.page_list.files_dropped.connect(self.add_pdf_files)
        self.page_list.model().rowsMoved.connect(lambda *_: self.update_status())
        self.page_list.itemSelectionChanged.connect(self.update_status)

        self.empty_label = QLabel("Drop PDF files here or use Add PDFs.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(
            """
            QLabel {
                border: 2px dashed #cbd5e1;
                border-radius: 18px;
                padding: 48px;
                color: #475569;
                background: rgba(255, 255, 255, 0.72);
                font-size: 18px;
            }
            """
        )

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(18, 18, 18, 18)
        central_layout.setSpacing(16)

        header = QLabel("Merge, split, delete, and extract PDF pages visually.")
        header.setStyleSheet("font-size: 24px; font-weight: 600; color: #0f172a;")
        central_layout.addWidget(header)

        subheader = QLabel(
            "Load one or more PDFs, reorder pages by drag-and-drop, then save the result."
        )
        subheader.setStyleSheet("color: #475569; font-size: 14px;")
        central_layout.addWidget(subheader)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        content_layout.addWidget(self.empty_label)
        content_layout.addWidget(self.page_list, stretch=1)
        self.page_list.setMinimumHeight(420)
        central_layout.addWidget(content, stretch=1)

        footer = QHBoxLayout()
        self.status_label = QLabel("No PDF loaded")
        self.status_label.setStyleSheet("color: #475569;")
        footer.addWidget(self.status_label)
        footer.addStretch(1)

        hint = QLabel("Tip: Use Ctrl/Cmd-click or Shift-click to select multiple pages.")
        hint.setStyleSheet("color: #64748b;")
        footer.addWidget(hint)
        central_layout.addLayout(footer)

        self.setCentralWidget(central)
        self._build_toolbar()
        self._apply_styles()
        self._refresh_empty_state()

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Tools")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(toolbar)

        add_action = QAction("Add PDFs", self)
        add_action.triggered.connect(self.open_pdf_files)
        toolbar.addAction(add_action)

        save_action = QAction("Save Merged PDF", self)
        save_action.triggered.connect(self.save_current_document)
        toolbar.addAction(save_action)

        toolbar.addSeparator()

        delete_action = QAction("Delete Selected", self)
        delete_action.triggered.connect(self.delete_selected_pages)
        toolbar.addAction(delete_action)

        extract_action = QAction("Extract Selected", self)
        extract_action.triggered.connect(self.extract_selected_pages)
        toolbar.addAction(extract_action)

        split_action = QAction("Split", self)
        split_action.triggered.connect(self.split_document)
        toolbar.addAction(split_action)

        toolbar.addSeparator()

        clear_action = QAction("Clear", self)
        clear_action.triggered.connect(self.clear_all_pages)
        toolbar.addAction(clear_action)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #f8fafc, stop:1 #e2e8f0);
            }
            QToolBar {
                background: rgba(255, 255, 255, 0.9);
                border: none;
                spacing: 8px;
                padding: 10px 12px;
            }
            QToolButton {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 8px 12px;
                color: #0f172a;
            }
            QToolButton:hover {
                background: #eff6ff;
                border-color: #93c5fd;
            }
            QListWidget {
                background: rgba(255, 255, 255, 0.75);
                border: 1px solid #dbe4f0;
                border-radius: 18px;
                padding: 18px;
                outline: none;
            }
            QListWidget::item {
                background: white;
                border: 1px solid #dbe4f0;
                border-radius: 14px;
                padding: 8px;
                margin: 4px;
            }
            QListWidget::item:selected {
                background: #dbeafe;
                border: 2px solid #60a5fa;
            }
            """
        )

    def open_pdf_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select PDF Files",
            "",
            "PDF Files (*.pdf)",
        )
        if files:
            self.add_pdf_files(files)

    def add_pdf_files(self, files: list[str]) -> None:
        added_pages = 0
        for file_path in files:
            try:
                refs = load_pages_from_pdf(file_path)
            except PDFOpsError as exc:
                self.show_error(str(exc))
                continue

            for ref in refs:
                self.page_list.addItem(self._build_page_item(ref))
                added_pages += 1

        if added_pages:
            self._refresh_empty_state()
            self.update_status()

    def _build_page_item(self, ref: PDFPageRef) -> QListWidgetItem:
        pixmap = self._thumbnail_to_qpixmap(ref)
        item = QListWidgetItem(QIcon(pixmap), ref.page_label)
        item.setData(Qt.ItemDataRole.UserRole, ref)
        item.setSizeHint(QSize(220, 320))
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return item

    def _thumbnail_to_qpixmap(self, ref: PDFPageRef) -> QPixmap:
        pix = render_thumbnail(ref.source_path, ref.page_index)
        image_format = (
            QImage.Format.Format_RGB888
            if pix.n < 4
            else QImage.Format.Format_RGBA8888
        )
        image = QImage(
            pix.samples,
            pix.width,
            pix.height,
            pix.stride,
            image_format,
        ).copy()
        return QPixmap.fromImage(image)

    def current_page_refs(self) -> list[PDFPageRef]:
        refs: list[PDFPageRef] = []
        for index in range(self.page_list.count()):
            item = self.page_list.item(index)
            refs.append(item.data(Qt.ItemDataRole.UserRole))
        return refs

    def selected_indexes(self) -> list[int]:
        return sorted(index.row() for index in self.page_list.selectedIndexes())

    def save_current_document(self) -> None:
        refs = self.current_page_refs()
        if not refs:
            self.show_error("Load at least one PDF page first.")
            return

        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save PDF",
            "merged.pdf",
            "PDF Files (*.pdf)",
        )
        if not output_path:
            return

        try:
            save_pages_as_pdf(refs, output_path)
        except PDFOpsError as exc:
            self.show_error(str(exc))
            return

        self.statusBar().showMessage(f"Saved: {output_path}", 5000)

    def delete_selected_pages(self) -> None:
        selected = self.page_list.selectedItems()
        if not selected:
            self.show_error("Select one or more pages to delete.")
            return

        for item in selected:
            row = self.page_list.row(item)
            self.page_list.takeItem(row)

        self._refresh_empty_state()
        self.update_status()

    def extract_selected_pages(self) -> None:
        refs = self.current_page_refs()
        indexes = self.selected_indexes()
        if not indexes:
            self.show_error("Select one or more pages to extract.")
            return

        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Extracted PDF",
            "extracted.pdf",
            "PDF Files (*.pdf)",
        )
        if not output_path:
            return

        try:
            extract_selected_pages(refs, indexes, output_path)
        except PDFOpsError as exc:
            self.show_error(str(exc))
            return

        self.statusBar().showMessage(f"Extracted pages to: {output_path}", 5000)

    def split_document(self) -> None:
        refs = self.current_page_refs()
        if not refs:
            self.show_error("Load at least one PDF page first.")
            return

        dialog = SplitDialog(len(refs), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        mode, range_text = dialog.values()
        output_dir = QFileDialog.getExistingDirectory(self, "Choose Output Folder")
        if not output_dir:
            return

        base_name = self._suggest_base_name()

        try:
            if mode == "each":
                files = split_to_individual_pages(refs, output_dir, base_name)
            else:
                ranges = parse_page_ranges(range_text, len(refs))
                files = split_by_ranges(refs, ranges, output_dir, base_name)
        except PDFOpsError as exc:
            self.show_error(str(exc))
            return

        self.statusBar().showMessage(f"Created {len(files)} files in {output_dir}", 5000)

    def clear_all_pages(self) -> None:
        self.page_list.clear()
        self._refresh_empty_state()
        self.update_status()

    def _suggest_base_name(self) -> str:
        refs = self.current_page_refs()
        if not refs:
            return "document"
        first_name = Path(refs[0].source_path).stem
        return f"{first_name}_edited"

    def _refresh_empty_state(self) -> None:
        has_pages = self.page_list.count() > 0
        self.empty_label.setVisible(not has_pages)

    def update_status(self) -> None:
        count = self.page_list.count()
        selected = len(self.page_list.selectedItems())
        if count == 0:
            self.status_label.setText("No PDF loaded")
            return
        self.status_label.setText(f"{count} pages loaded | {selected} selected")

    def show_error(self, message: str) -> None:
        QMessageBox.warning(self, "PDF Studio", message)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PDF Studio")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
