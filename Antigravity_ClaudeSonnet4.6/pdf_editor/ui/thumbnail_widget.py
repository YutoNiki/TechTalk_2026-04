"""
thumbnail_widget.py - Draggable, selectable page thumbnail grid widget
"""
from __future__ import annotations

from typing import List, Optional, Set, Tuple, Dict
import fitz

from PyQt6.QtCore import (
    Qt, QSize, QPoint, QMimeData, pyqtSignal, QByteArray, QBuffer, QIODevice
)
from PyQt6.QtGui import (
    QPixmap, QColor, QPainter, QPen, QDrag, QMouseEvent, QImage,
    QFont, QFontMetrics, QPalette
)
from PyQt6.QtWidgets import (
    QWidget, QScrollArea, QGridLayout, QLabel, QVBoxLayout,
    QFrame, QSizePolicy, QApplication, QAbstractScrollArea
)

from core.pdf_operations import render_page_thumbnail


class PageCard(QFrame):
    """A single thumbnail card representing one PDF page."""

    clicked = pyqtSignal(int, Qt.KeyboardModifier)   # page_index, modifiers
    drag_started = pyqtSignal(int)

    def __init__(self, page_index: int, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.page_index = page_index
        self._pixmap = pixmap
        self._selected = False
        self._drag_start: Optional[QPoint] = None

        self.setFixedSize(160, 220)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptDrops(False)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Image label
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setPixmap(self._pixmap.scaled(
            148, 185, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))
        self.img_label.setStyleSheet("border: none;")
        layout.addWidget(self.img_label)

        # Page number label
        self.num_label = QLabel(str(self.page_index + 1))
        self.num_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.num_label.setStyleSheet("color: #8a9bb0; font-size: 11px; font-weight: 500;")
        layout.addWidget(self.num_label)

        self._update_style()

    def _update_style(self):
        if self._selected:
            self.setStyleSheet("""
                PageCard {
                    background: #1e3a5f;
                    border: 2px solid #4a9eff;
                    border-radius: 10px;
                }
            """)
        else:
            self.setStyleSheet("""
                PageCard {
                    background: #1a2332;
                    border: 2px solid #2a3a50;
                    border-radius: 10px;
                }
                PageCard:hover {
                    border: 2px solid #3a5a80;
                    background: #1e2a3a;
                }
            """)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._update_style()

    def is_selected(self) -> bool:
        return self._selected

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.pos()
            self.clicked.emit(self.page_index, event.modifiers())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if (self._drag_start is not None
                and (event.pos() - self._drag_start).manhattanLength() > QApplication.startDragDistance()):
            self.drag_started.emit(self.page_index)
            self._drag_start = None
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_start = None
        super().mouseReleaseEvent(event)


class ThumbnailGrid(QWidget):
    """
    Scrollable grid of PageCard widgets.

    Signals:
        selection_changed(selected_indices): emitted when the selection changes.
        order_changed(new_order): emitted when pages are reordered via DnD.
    """

    selection_changed = pyqtSignal(list)   # List[int] — selected page indices
    order_changed = pyqtSignal(list)       # List[int] — new page order (original indices)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: List[PageCard] = []
        self._order: List[int] = []        # original page indices in display order
        self._selected: Set[int] = set()   # original page indices
        self._last_clicked: Optional[int] = None
        self._pdf_path: Optional[str] = None
        self._doc: Optional[fitz.Document] = None

        self.setAcceptDrops(True)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                background: #0d1520; width: 8px; border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #2a3a50; border-radius: 4px; min-height: 20px;
            }
            QScrollBar::handle:vertical:hover { background: #4a9eff; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar:horizontal {
                background: #0d1520; height: 8px; border-radius: 4px;
            }
            QScrollBar::handle:horizontal {
                background: #2a3a50; border-radius: 4px; min-width: 20px;
            }
            QScrollBar::handle:horizontal:hover { background: #4a9eff; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
        """)

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(self._container)
        self._grid.setSpacing(12)
        self._grid.setContentsMargins(16, 16, 16, 16)
        self._scroll.setWidget(self._container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._scroll)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_pdf(self, pdf_path: str):
        """Load a PDF and render thumbnails for every page."""
        if self._doc:
            self._doc.close()
        self._doc = fitz.open(pdf_path)
        self._pdf_path = pdf_path
        self._order = list(range(len(self._doc)))
        self._selected.clear()
        self._last_clicked = None
        self._rebuild_grid()
        self.selection_changed.emit([])

    def clear(self):
        """Remove all thumbnails."""
        if self._doc:
            self._doc.close()
            self._doc = None
        self._pdf_path = None
        self._order.clear()
        self._selected.clear()
        self._last_clicked = None
        self._rebuild_grid()
        self.selection_changed.emit([])

    def get_selected_original_indices(self) -> List[int]:
        """Return selected page indices (in original document order, sorted)."""
        return sorted(self._selected)

    def get_display_order(self) -> List[int]:
        """Return all page original-indices in current display order."""
        return list(self._order)

    def get_pdf_path(self) -> Optional[str]:
        return self._pdf_path

    def page_count(self) -> int:
        return len(self._order)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rebuild_grid(self):
        """Clear and repopulate the grid from self._order."""
        # Remove all existing cards
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()

        if self._doc is None:
            return

        columns = max(1, (self.width() - 32) // (160 + 12)) or 4
        columns = max(columns, 1)

        for display_idx, orig_idx in enumerate(self._order):
            png_bytes = render_page_thumbnail(self._doc, orig_idx, width=148)
            img = QImage.fromData(png_bytes, "PNG")
            pixmap = QPixmap.fromImage(img)

            card = PageCard(orig_idx, pixmap, self._container)
            card.clicked.connect(self._on_card_clicked)
            card.drag_started.connect(self._on_card_drag)
            card.set_selected(orig_idx in self._selected)

            row, col = divmod(display_idx, columns)
            self._grid.addWidget(card, row, col)
            self._cards.append(card)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rebuild_grid()

    # ------------------------------------------------------------------
    # Selection logic
    # ------------------------------------------------------------------

    def _card_by_orig_index(self, orig_idx: int) -> Optional[PageCard]:
        for c in self._cards:
            if c.page_index == orig_idx:
                return c
        return None

    def _on_card_clicked(self, orig_idx: int, modifiers: Qt.KeyboardModifier):
        ctrl = modifiers & Qt.KeyboardModifier.ControlModifier
        shift = modifiers & Qt.KeyboardModifier.ShiftModifier

        if shift and self._last_clicked is not None:
            # Range select in display order
            display_indices = [c.page_index for c in self._cards]
            try:
                a = display_indices.index(self._last_clicked)
                b = display_indices.index(orig_idx)
            except ValueError:
                a, b = 0, len(display_indices) - 1
            lo, hi = min(a, b), max(a, b)
            if not ctrl:
                self._selected.clear()
            for di in range(lo, hi + 1):
                self._selected.add(display_indices[di])
        elif ctrl:
            if orig_idx in self._selected:
                self._selected.discard(orig_idx)
            else:
                self._selected.add(orig_idx)
        else:
            self._selected = {orig_idx}

        self._last_clicked = orig_idx
        self._refresh_selection_visuals()
        self.selection_changed.emit(sorted(self._selected))

    def _refresh_selection_visuals(self):
        for card in self._cards:
            card.set_selected(card.page_index in self._selected)

    # ------------------------------------------------------------------
    # Drag-and-drop reordering
    # ------------------------------------------------------------------

    def _on_card_drag(self, orig_idx: int):
        """Initiate a drag from the card with orig_idx."""
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(str(orig_idx))
        drag.setMimeData(mime)

        # Drag pixmap
        card = self._card_by_orig_index(orig_idx)
        if card:
            drag.setPixmap(card.grab().scaled(80, 110, Qt.AspectRatioMode.KeepAspectRatio))
            drag.setHotSpot(QPoint(40, 55))

        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not event.mimeData().hasText():
            return
        try:
            dragged_orig = int(event.mimeData().text())
        except ValueError:
            return

        # Find drop position
        drop_pos = event.position().toPoint()
        drop_display_idx = len(self._cards)  # default: end

        for di, card in enumerate(self._cards):
            card_pos = card.mapTo(self, QPoint(0, 0))
            if drop_pos.y() < card_pos.y() + card.height() // 2:
                if drop_pos.x() < card_pos.x() + card.width() // 2:
                    drop_display_idx = di
                    break

        # Reorder self._order
        if dragged_orig in self._order:
            drag_display_idx = self._order.index(dragged_orig)
            self._order.remove(dragged_orig)
            insert_at = drop_display_idx
            if drag_display_idx < drop_display_idx:
                insert_at -= 1
            insert_at = max(0, min(insert_at, len(self._order)))
            self._order.insert(insert_at, dragged_orig)

        self._rebuild_grid()
        event.acceptProposedAction()
        self.order_changed.emit(list(self._order))
