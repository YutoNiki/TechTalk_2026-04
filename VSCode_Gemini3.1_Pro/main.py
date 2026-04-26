import sys
import os
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QFileDialog, QListWidget, QListWidgetItem, QLabel, QMessageBox, QAbstractItemView
)
from PyQt6.QtGui import QIcon, QPixmap, QImage
from PyQt6.QtCore import Qt, QSize, pyqtSignal

from pdf_engine import PDFEngine

class ThumbnailListWidget(QListWidget):
    dropped_files = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(150, 200)) # サムネイルサイズ
        self.setGridSize(QSize(170, 230))
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection) # 複数選択可
        self.setSpacing(10)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            filepaths = [url.toLocalFile() for url in urls if url.toLocalFile().lower().endswith('.pdf')]
            if filepaths:
                event.acceptProposedAction()
                self.dropped_files.emit(filepaths)
        else:
            super().dropEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Editor (Merge, Split, Extract, Delete)")
        self.resize(1000, 700)
        self.setup_ui()
        self.page_data_map = {} # QListWidgetItemへの参照情報保持

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # ツールバー（上部ボタン群）
        top_layout = QHBoxLayout()
        
        self.btn_add = QPushButton("PDFを追加")
        self.btn_add.clicked.connect(self.add_pdfs_dialog)
        top_layout.addWidget(self.btn_add)

        self.btn_delete = QPushButton("選択したページを削除")
        self.btn_delete.clicked.connect(self.delete_selected_pages)
        top_layout.addWidget(self.btn_delete)
        
        self.btn_extract = QPushButton("選択したページを新規PDFとして抽出")
        self.btn_extract.clicked.connect(self.extract_selected_pages)
        top_layout.addWidget(self.btn_extract)

        self.btn_split = QPushButton("現在の一覧をすべて個別PDFに分割")
        self.btn_split.clicked.connect(self.split_all_pages)
        top_layout.addWidget(self.btn_split)

        self.btn_merge = QPushButton("現在の一覧でPDFを保存 (結合/並び替え)")
        self.btn_merge.clicked.connect(self.save_current_list)
        top_layout.addWidget(self.btn_merge)
        
        main_layout.addLayout(top_layout)

        # サムネイル表示エリア
        self.thumbnail_view = ThumbnailListWidget()
        self.thumbnail_view.dropped_files.connect(self.load_pdfs)
        main_layout.addWidget(self.thumbnail_view)
        
        # ドラッグ＆ドロップ説明
        info_label = QLabel("PDFファイルをここにドラッグ＆ドロップしてください。\nドラッグでページの順番を入れ替え、複数選択して削除・抽出などの操作が可能です。")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(info_label)

    def add_pdfs_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "PDFファイルを選択", "", "PDF Files (*.pdf)"
        )
        if files:
            self.load_pdfs(files)

    def load_pdfs(self, filepaths):
        for filepath in filepaths:
            base_name = os.path.basename(filepath)
            
            # get_pages_images は CPU ヘビーなため、大規模ファイルは非同期処理推奨ですが、
            # シンプルな構成として同期的に実行
            page_data = PDFEngine.get_pages_images(filepath, zoom=0.5)
            
            for index, p_data in enumerate(page_data):
                pixmap = QPixmap()
                pixmap.loadFromData(p_data["image_bytes"], "PNG")
                icon = QIcon(pixmap)
                
                label_text = f"{base_name}\nPage {index + 1}"
                item = QListWidgetItem(icon, label_text)
                # カスタムデータ保持
                item.setData(Qt.ItemDataRole.UserRole, {
                    "filepath": filepath,
                    "page_index": index
                })
                self.thumbnail_view.addItem(item)

    def get_selected_page_data(self):
        items = self.thumbnail_view.selectedItems()
        if not items:
            QMessageBox.warning(self, "エラー", "1つ以上のページを選択してください。")
            return None
        return [item.data(Qt.ItemDataRole.UserRole) for item in items]

    def get_all_page_data(self):
        items = [self.thumbnail_view.item(i) for i in range(self.thumbnail_view.count())]
        if not items:
            QMessageBox.warning(self, "エラー", "ページが存在しません。")
            return None
        return [item.data(Qt.ItemDataRole.UserRole) for item in items]

    def delete_selected_pages(self):
        items = self.thumbnail_view.selectedItems()
        if not items:
            return
        
        reply = QMessageBox.question(self, "確認", f"{len(items)} ページを一覧から削除しますか？\n(元のファイルは変更されません)", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            for item in items:
                row = self.thumbnail_view.row(item)
                self.thumbnail_view.takeItem(row)

    def extract_selected_pages(self):
        page_data = self.get_selected_page_data()
        if not page_data:
            return

        save_path, _ = QFileDialog.getSaveFileName(self, "抽出したPDFを保存", "extracted.pdf", "PDF Files (*.pdf)")
        if save_path:
            PDFEngine.build_pdf_from_pages(page_data, save_path)
            QMessageBox.information(self, "完了", f"抽出したPDFを保存しました:\n{save_path}")

    def save_current_list(self):
        page_data = self.get_all_page_data()
        if not page_data:
            return

        save_path, _ = QFileDialog.getSaveFileName(self, "結合/再編成したPDFを保存", "merged.pdf", "PDF Files (*.pdf)")
        if save_path:
            PDFEngine.build_pdf_from_pages(page_data, save_path)
            QMessageBox.information(self, "完了", f"PDFを保存しました:\n{save_path}")

    def split_all_pages(self):
        page_data = self.get_all_page_data()
        if not page_data:
            return
            
        save_dir = QFileDialog.getExistingDirectory(self, "分割したPDFを保存するフォルダを選択")
        if save_dir:
            PDFEngine.split_pdf_to_pages(page_data, save_dir)
            QMessageBox.information(self, "完了", f"各ページを分割して保存しました:\n{save_dir}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
