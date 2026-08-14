"""Sticky note widget with true QPushButton delete and click-to-edit drag-to-move."""

import random

from PySide6.QtWidgets import (
    QTextEdit, QMessageBox, QGraphicsObject, QGraphicsItem,
    QGraphicsProxyWidget, QPushButton
)
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath, QCursor

from config import C_TEXT_PRIMARY, C_TEXT_MUTED, C_BORDER, C_ACCENT, NOTE_COLORS


class NoteTextEdit(QTextEdit):
    """Embedded text editor.

    Click  -> edit (normal QTextEdit behavior)
    Drag   -> move note (forwarded to StickyNote after 5px threshold)
    """

    def __init__(self, sticky_note=None, parent=None):
        super().__init__(parent)
        self.sticky_note = sticky_note
        self._pressed = False
        self._press_pos = None
        self._dragging = False
        self.setStyleSheet(f"""
            QTextEdit {{
                background-color: transparent;
                border: none;
                font-family: "Georgia", "Times New Roman", serif;
                font-size: 13px;
                color: {C_TEXT_PRIMARY};
                padding: 8px;
                padding-top: 28px;
                padding-bottom: 22px;
                line-height: 1.5;
            }}
        """)

    def mousePressEvent(self, event):
        self._pressed = True
        self._press_pos = event.position().toPoint()
        self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pressed and not self._dragging and self.sticky_note:
            dist = (event.position().toPoint() - self._press_pos).manhattanLength()
            if dist > 5:
                self._dragging = True
                self.sticky_note._start_drag(event.globalPosition())
        if self._dragging and self.sticky_note:
            self.sticky_note._do_drag(event.globalPosition())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging and self.sticky_note:
            self._dragging = False
            self._pressed = False
            self.sticky_note._end_drag()
            return
        self._pressed = False
        super().mouseReleaseEvent(event)


class StickyNote(QGraphicsObject):
    deleted = Signal(str)
    content_changed = Signal(str, str)
    moved = Signal(str, float, float)

    def __init__(self, note_id, content="", x=100, y=100, width=220, height=180,
                 rotation=0, color=None, parent=None):
        super().__init__(parent)
        self.note_id = note_id
        self._content = content
        self._width = width
        self._height = height
        self._color = color or random.choice(NOTE_COLORS)
        self._dragging = False
        self._drag_start_pos = None
        self._drag_start_scene = None

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setPos(x, y)
        self.setRotation(rotation)

        # Text editor (covers full note)
        self.text_edit = NoteTextEdit(sticky_note=self)
        self.text_edit.setPlainText(content)
        self.text_edit.textChanged.connect(self._on_text_changed)

        self.text_proxy = QGraphicsProxyWidget(self)
        self.text_proxy.setWidget(self.text_edit)
        self.text_proxy.setGeometry(QRectF(0, 0, width, height))
        self.text_edit.setFixedSize(int(width), int(height))

        # Delete button (true QPushButton, sits on top of text)
        self.del_btn = QPushButton("\u00d7")  # ×
        self.del_btn.setFixedSize(22, 22)
        self.del_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.del_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(200,200,200,80);
                color: {C_TEXT_MUTED};
                border: none;
                border-radius: 11px;
                font-size: 14px;
                font-weight: bold;
                font-family: Arial;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {C_ACCENT};
                color: white;
            }}
        """)
        self.del_btn.clicked.connect(self._confirm_delete)

        self.del_proxy = QGraphicsProxyWidget(self)
        self.del_proxy.setWidget(self.del_btn)
        self.del_proxy.setPos(width - 26, height - 26)
        # Ensure delete button is above text
        self.del_proxy.setZValue(10)

    # ------------------------------------------------------------------
    # Text
    # ------------------------------------------------------------------
    def _on_text_changed(self):
        self._content = self.text_edit.toPlainText()
        self.content_changed.emit(self.note_id, self._content)

    def _confirm_delete(self):
        parent = None
        if self.scene() and self.scene().views():
            parent = self.scene().views()[0]
        reply = QMessageBox.question(
            parent, "Delete Note", "Delete this sticky note?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.deleted.emit(self.note_id)

    # ------------------------------------------------------------------
    # Drag (called by NoteTextEdit)
    # ------------------------------------------------------------------
    def _global_to_scene(self, global_pos):
        view = self.scene().views()[0]
        view_pos = view.mapFromGlobal(global_pos.toPoint())
        return view.mapToScene(view_pos)

    def _start_drag(self, global_pos):
        self._dragging = True
        self._drag_start_pos = self.pos()
        self._drag_start_scene = self._global_to_scene(global_pos)
        self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))

    def _do_drag(self, global_pos):
        if not self._dragging:
            return
        scene_pos = self._global_to_scene(global_pos)
        delta = scene_pos - self._drag_start_scene
        self.setPos(self._drag_start_pos + delta)

    def _end_drag(self):
        if self._dragging:
            self._dragging = False
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            if self._drag_start_pos != self.pos():
                self.moved.emit(self.note_id, self.pos().x(), self.pos().y())

    # ------------------------------------------------------------------
    # Qt events (for shadow area outside proxy widgets)
    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start_pos = self.pos()
            self._drag_start_scene = event.scenePos()
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))

    def mouseMoveEvent(self, event):
        if self._dragging:
            delta = event.scenePos() - self._drag_start_scene
            self.setPos(self._drag_start_pos + delta)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            if self._drag_start_pos != self.pos():
                self.moved.emit(self.note_id, self.pos().x(), self.pos().y())

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------
    def boundingRect(self):
        return QRectF(-3, -3, self._width + 6, self._height + 6)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Soft shadow
        for i in range(5, 0, -1):
            alpha = 18 - i * 3
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(0, 0, 0, alpha)))
            r = QRectF(i * 0.6, i * 0.8, self._width, self._height)
            p = QPainterPath()
            p.addRoundedRect(r, 4, 4)
            painter.drawPath(p)

        # Body
        rect = QRectF(0, 0, self._width, self._height)
        path = QPainterPath()
        path.addRoundedRect(rect, 3, 3)
        painter.setBrush(QBrush(QColor(self._color)))
        painter.setPen(QPen(QColor(C_BORDER), 0.8))
        painter.drawPath(path)

        # Ruled lines
        painter.setPen(QPen(QColor(0, 0, 0, 5), 0.5))
        ly = 30
        while ly < self._height - 8:
            painter.drawLine(int(10), int(ly), int(self._width - 10), int(ly))
            ly += 20

    # ------------------------------------------------------------------
    # Serialize
    # ------------------------------------------------------------------
    def to_dict(self):
        return {
            "id": self.note_id,
            "content": self._content,
            "x": self.pos().x(),
            "y": self.pos().y(),
            "width": self._width,
            "height": self._height,
            "rotation": self.rotation(),
            "color": self._color,
            "pinned": False,
        }
