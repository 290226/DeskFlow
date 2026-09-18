"""Sticky note graphics item.

A note is a `QGraphicsObject` that hosts a `QTextEdit` (via a proxy widget) for
editing, a tag button, a delete button and a bottom-right resize grip.

Interaction model
-----------------
* Click inside the text area          -> edit the text
* Drag inside the text area (>5 px)   -> move the note
* Drag the bottom-right grip          -> resize the note
* Right click anywhere on the note    -> context menu (color, size, tags, ...)
"""

import random

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QCursor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsProxyWidget,
    QInputDialog,
    QMenu,
    QMessageBox,
    QPushButton,
    QTextEdit,
)

from deskflow.config import (
    C_ACCENT,
    C_BORDER,
    C_HIGHLIGHT,
    C_TEXT_MUTED,
    C_TEXT_PRIMARY,
    C_TOOL_BLUE,
    NOTE_COLORS,
    NOTE_DEFAULT_HEIGHT,
    NOTE_DEFAULT_WIDTH,
    NOTE_FONT_SIZES,
    NOTE_GRIP_SIZE,
    NOTE_MAX_HEIGHT,
    NOTE_MAX_WIDTH,
    NOTE_MIN_HEIGHT,
    NOTE_MIN_WIDTH,
    NOTE_SIZES,
    TAG_COLOR_DEFAULT,
    TAG_COLORS,
    Z_NOTE_BASE,
    Z_NOTE_MAX,
)
from deskflow.core.util import clamp, clean_tags, new_id

TAG_FONT = QFont("Segoe UI", 8, QFont.Weight.Bold)


class NoteTextEdit(QTextEdit):
    """Embedded editor that forwards drag gestures to its sticky note."""

    DRAG_THRESHOLD = 5

    def __init__(self, sticky_note=None, parent=None):
        super().__init__(parent)
        self.sticky_note = sticky_note
        self._pressed = False
        self._press_pos = None
        self._dragging = False
        self._font_size = NOTE_FONT_SIZES["medium"]
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.apply_font_size(self._font_size)

    def apply_font_size(self, size):
        self._font_size = size
        self.setStyleSheet(
            """
            QTextEdit {{
                background-color: transparent;
                border: none;
                font-family: "Georgia", "Times New Roman", serif;
                font-size: {size}px;
                color: {color};
                padding: 8px;
                padding-top: {top}px;
                padding-bottom: 8px;
            }}
            """.format(size=size, color=C_TEXT_PRIMARY, top=NOTE_GRIP_SIZE + 10)
        )

    def _on_context_menu(self, pos):
        if self.sticky_note is not None:
            self.sticky_note.show_context_menu(self.mapToGlobal(pos))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self._press_pos = event.position().toPoint()
            self._dragging = False
            self._select_owner()
        super().mousePressEvent(event)

    def _select_owner(self):
        """Select the item hosting this editor (the editor covers it)."""
        owner = self.sticky_note
        if owner is None:
            return
        scene = owner.scene()
        if scene is not None and not (
            QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            scene.clearSelection()
        owner.setSelected(True)

    def mouseMoveEvent(self, event):
        if self._pressed and not self._dragging and self.sticky_note:
            delta = event.position().toPoint() - self._press_pos
            if abs(delta.x()) + abs(delta.y()) > self.DRAG_THRESHOLD:
                self._dragging = True
                self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                self.sticky_note.start_drag(event.globalPosition())
        if self._dragging and self.sticky_note:
            self.sticky_note.do_drag(event.globalPosition())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging and self.sticky_note:
            self._dragging = False
            self._pressed = False
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.sticky_note.end_drag()
            return
        self._pressed = False
        super().mouseReleaseEvent(event)


class StickyNote(QGraphicsObject):
    deleted = Signal(str)
    content_changed = Signal(str, str)
    moved = Signal(str, float, float)
    tags_changed = Signal(str, list)
    raise_requested = Signal(str)

    def __init__(
        self,
        note_id,
        content="",
        x=100,
        y=100,
        width=NOTE_DEFAULT_WIDTH,
        height=NOTE_DEFAULT_HEIGHT,
        rotation=0.0,
        color=None,
        tags=None,
        font_size=None,
        z=0.0,
        parent=None,
    ):
        super().__init__(parent)
        self.note_id = note_id
        self._content = content or ""
        self._width = float(width)
        self._height = float(height)
        self._color = color if color in NOTE_COLORS else random.choice(NOTE_COLORS)
        self._tags = clean_tags(tags)
        self._font_size = int(font_size) if font_size else NOTE_FONT_SIZES["medium"]
        self._dragging = False
        self._drag_start_pos = None
        self._drag_start_scene = None
        self._resizing = False
        self._resize_origin = None
        self._resize_start_size = (self._width, self._height)
        self._flash_count = 0
        self._flash_on = False

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setPos(x, y)
        self.setRotation(float(rotation or 0.0))
        # Notes live inside their own z band, so a mind map node can never be
        # hidden behind a sticky note.
        try:
            z_value = float(z)
        except (TypeError, ValueError):
            z_value = Z_NOTE_BASE
        self.setZValue(clamp(z_value, Z_NOTE_BASE, Z_NOTE_MAX))

        text_w = max(40.0, self._width - NOTE_GRIP_SIZE)
        text_h = max(40.0, self._height - NOTE_GRIP_SIZE)

        # --- text editor -------------------------------------------------
        self.text_edit = NoteTextEdit(sticky_note=self)
        self.text_edit.setPlainText(self._content)
        self.text_edit.apply_font_size(self._font_size)
        self.text_edit.setFixedSize(int(text_w), int(text_h))
        self.text_edit.textChanged.connect(self._on_text_changed)

        self.text_proxy = QGraphicsProxyWidget(self)
        self.text_proxy.setWidget(self.text_edit)
        self.text_proxy.setGeometry(QRectF(0, 0, text_w, text_h))

        # --- delete button (top-right) -----------------------------------
        self.del_btn = QPushButton("\u00d7")
        self.del_btn.setFixedSize(20, 20)
        self.del_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.del_btn.setToolTip("Delete note")
        self.del_btn.setStyleSheet(self._round_button_style())
        self.del_btn.clicked.connect(self._confirm_delete)

        self.del_proxy = QGraphicsProxyWidget(self)
        self.del_proxy.setWidget(self.del_btn)
        self.del_proxy.setPos(self._width - 24, 4)
        self.del_proxy.setZValue(10)

        # --- tag button (top-right, left of delete) ----------------------
        self.tag_btn = QPushButton("#")
        self.tag_btn.setFixedSize(20, 20)
        self.tag_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.tag_btn.setToolTip("Edit tags")
        self.tag_btn.setStyleSheet(self._round_button_style())
        self.tag_btn.clicked.connect(self.edit_tags)

        self.tag_proxy = QGraphicsProxyWidget(self)
        self.tag_proxy.setWidget(self.tag_btn)
        self.tag_proxy.setPos(self._width - 48, 4)
        self.tag_proxy.setZValue(10)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _round_button_style():
        return """
            QPushButton {{
                background-color: rgba(255,255,255,90);
                color: {muted};
                border: none;
                border-radius: 10px;
                font-size: 12px;
                font-weight: bold;
                font-family: 'Segoe UI', Arial, sans-serif;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {accent};
                color: white;
            }}
        """.format(muted=C_TEXT_MUTED, accent=C_ACCENT)

    def _grip_rect(self):
        return QRectF(
            self._width - NOTE_GRIP_SIZE,
            self._height - NOTE_GRIP_SIZE,
            NOTE_GRIP_SIZE,
            NOTE_GRIP_SIZE,
        )

    def _apply_size(self):
        self.prepareGeometryChange()
        text_w = max(40.0, self._width - NOTE_GRIP_SIZE)
        text_h = max(40.0, self._height - NOTE_GRIP_SIZE)
        self.text_edit.setFixedSize(int(text_w), int(text_h))
        self.text_proxy.setGeometry(QRectF(0, 0, text_w, text_h))
        self.del_proxy.setPos(self._width - 24, 4)
        self.tag_proxy.setPos(self._width - 48, 4)
        self.update()

    # ------------------------------------------------------------------
    # content
    # ------------------------------------------------------------------
    def _on_text_changed(self):
        self._content = self.text_edit.toPlainText()
        self.content_changed.emit(self.note_id, self._content)

    def get_content(self):
        return self._content

    def set_content(self, text, silent=False):
        self._content = text or ""
        if self.text_edit.toPlainText() != self._content:
            if silent:
                self.text_edit.blockSignals(True)
            self.text_edit.setPlainText(self._content)
            if silent:
                self.text_edit.blockSignals(False)

    def get_tags(self):
        return list(self._tags)

    def set_tags(self, tags):
        self._tags = clean_tags(tags)
        self.update()

    def edit_tags(self):
        current = ", ".join(self._tags)
        text, ok = QInputDialog.getText(
            self._dialog_parent(), "Edit Tags", "Tags (comma separated):", text=current
        )
        if not ok:
            return
        self._tags = clean_tags(text)
        self.tags_changed.emit(self.note_id, self._tags)
        self.update()

    # ------------------------------------------------------------------
    # appearance
    # ------------------------------------------------------------------
    def set_color(self, color):
        if color:
            self._color = color
            self.update()

    def cycle_color(self):
        try:
            index = NOTE_COLORS.index(self._color)
        except ValueError:
            index = -1
        self.set_color(NOTE_COLORS[(index + 1) % len(NOTE_COLORS)])

    def set_font_size(self, size):
        try:
            size = int(size)
        except (TypeError, ValueError):
            return
        self._font_size = size
        self.text_edit.apply_font_size(size)

    def set_size(self, width, height):
        self._width = float(clamp(width, NOTE_MIN_WIDTH, NOTE_MAX_WIDTH))
        self._height = float(clamp(height, NOTE_MIN_HEIGHT, NOTE_MAX_HEIGHT))
        self._apply_size()
        self.moved.emit(self.note_id, self.pos().x(), self.pos().y())

    def flash(self, times=3):
        """Temporarily highlight the note (used when locating from search)."""
        self._flash_count = max(1, int(times))
        self._pulse()

    def _pulse(self):
        if self._flash_count <= 0:
            self._flash_on = False
            self.update()
            return
        self._flash_count -= 1
        self._flash_on = not self._flash_on
        self.update()
        QTimer.singleShot(220, self._pulse)

    # ------------------------------------------------------------------
    # deletion
    # ------------------------------------------------------------------
    def request_delete(self):
        """Delete without asking (caller already confirmed)."""
        self.deleted.emit(self.note_id)

    def _confirm_delete(self):
        reply = QMessageBox.question(
            self._dialog_parent(),
            "Delete Note",
            "Delete this sticky note?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.deleted.emit(self.note_id)

    def duplicate(self):
        return {
            "id": new_id("note"),
            "content": self._content,
            "x": self.pos().x() + 28,
            "y": self.pos().y() + 28,
            "width": self._width,
            "height": self._height,
            "rotation": self.rotation(),
            "color": self._color,
            "tags": list(self._tags),
            "font_size": self._font_size,
            "z": self.zValue() + 1,
        }

    # ------------------------------------------------------------------
    # context menu
    # ------------------------------------------------------------------
    def _dialog_parent(self):
        if self.scene() and self.scene().views():
            return self.scene().views()[0]
        return None

    def show_context_menu(self, global_pos):
        menu = QMenu(self._dialog_parent())

        act_duplicate = QAction("Duplicate note", menu)
        act_duplicate.triggered.connect(self._emit_duplicate)
        menu.addAction(act_duplicate)

        act_front = QAction("Bring to front", menu)
        act_front.triggered.connect(lambda: self.raise_requested.emit(self.note_id))
        menu.addAction(act_front)

        menu.addSeparator()

        color_menu = menu.addMenu("Color")
        for color in NOTE_COLORS:
            action = QAction(color, color_menu)
            action.setCheckable(True)
            action.setChecked(color == self._color)
            action.triggered.connect(lambda _=False, c=color: self.set_color(c))
            color_menu.addAction(action)

        size_menu = menu.addMenu("Text size")
        for label, size in (("Small", NOTE_FONT_SIZES["small"]),
                            ("Medium", NOTE_FONT_SIZES["medium"]),
                            ("Large", NOTE_FONT_SIZES["large"])):
            action = QAction(label, size_menu)
            action.setCheckable(True)
            action.setChecked(size == self._font_size)
            action.triggered.connect(lambda _=False, s=size: self.set_font_size(s))
            size_menu.addAction(action)

        box_menu = menu.addMenu("Note size")
        for label, dims in NOTE_SIZES.items():
            action = QAction(label.capitalize(), box_menu)
            action.triggered.connect(
                lambda _=False, d=dims: self.set_size(d[0], d[1])
            )
            box_menu.addAction(action)

        act_tags = QAction("Edit tags…", menu)
        act_tags.triggered.connect(self.edit_tags)
        menu.addAction(act_tags)

        menu.addSeparator()
        act_delete = QAction("Delete note", menu)
        act_delete.triggered.connect(self._confirm_delete)
        menu.addAction(act_delete)

        menu.exec(global_pos)

    def _emit_duplicate(self):
        # The canvas owns note creation, so ask the hosting view to do it.
        view = self._dialog_parent()
        duplicate = getattr(view, "duplicate_note", None)
        if callable(duplicate):
            duplicate(self.note_id)

    # ------------------------------------------------------------------
    # drag / resize (driven by NoteTextEdit or by direct item events)
    # ------------------------------------------------------------------
    def _global_to_scene(self, global_pos):
        views = self.scene().views() if self.scene() else []
        if not views:
            return QPointF(0, 0)
        view = views[0]
        return view.mapToScene(view.mapFromGlobal(global_pos.toPoint()))

    def start_drag(self, global_pos):
        self._dragging = True
        self._drag_start_pos = self.pos()
        self._drag_start_scene = self._global_to_scene(global_pos)
        self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
        self.raise_requested.emit(self.note_id)

    def do_drag(self, global_pos):
        if not self._dragging:
            return
        delta = self._global_to_scene(global_pos) - self._drag_start_scene
        self.setPos(self._drag_start_pos + delta)

    def end_drag(self):
        if self._dragging:
            self._dragging = False
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            if self._drag_start_pos != self.pos():
                self.moved.emit(self.note_id, self.pos().x(), self.pos().y())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.raise_requested.emit(self.note_id)
            if self._grip_rect().contains(event.pos()):
                self._resizing = True
                self._resize_origin = event.scenePos()
                self._resize_start_size = (self._width, self._height)
                self.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
                event.accept()
                return
            self._dragging = True
            self._drag_start_pos = self.pos()
            self._drag_start_scene = event.scenePos()
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            delta = event.scenePos() - self._resize_origin
            self._width = clamp(
                self._resize_start_size[0] + delta.x(), NOTE_MIN_WIDTH, NOTE_MAX_WIDTH
            )
            self._height = clamp(
                self._resize_start_size[1] + delta.y(), NOTE_MIN_HEIGHT, NOTE_MAX_HEIGHT
            )
            self._apply_size()
            return
        if self._dragging:
            delta = event.scenePos() - self._drag_start_scene
            self.setPos(self._drag_start_pos + delta)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            self.moved.emit(self.note_id, self.pos().x(), self.pos().y())
        elif self._dragging:
            self._dragging = False
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            if self._drag_start_pos != self.pos():
                self.moved.emit(self.note_id, self.pos().x(), self.pos().y())
        super().mouseReleaseEvent(event)

    def hoverMoveEvent(self, event):
        if self._grip_rect().contains(event.pos()):
            self.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        super().hoverMoveEvent(event)

    # ------------------------------------------------------------------
    # geometry / painting
    # ------------------------------------------------------------------
    def boundingRect(self):
        return QRectF(-4, -4, self._width + 8, self._height + 8)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # soft shadow
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(5, 0, -1):
            painter.setBrush(QBrush(QColor(0, 0, 0, 18 - i * 3)))
            path = QPainterPath()
            path.addRoundedRect(
                QRectF(i * 0.6, i * 0.8, self._width, self._height), 4, 4
            )
            painter.drawPath(path)

        # body
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self._width, self._height), 3, 3)
        painter.setBrush(QBrush(QColor(self._color)))
        if self._flash_on:
            painter.setPen(QPen(QColor(C_ACCENT), 2.2))
        elif self.isSelected():
            painter.setPen(QPen(QColor(C_BORDER), 1.4))
        else:
            painter.setPen(QPen(QColor(C_BORDER), 0.8))
        painter.drawPath(path)

        if self._flash_on:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(C_HIGHLIGHT)))
            painter.setOpacity(0.35)
            painter.drawRoundedRect(QRectF(0, 0, self._width, self._height), 3, 3)
            painter.setOpacity(1.0)

        # ruled lines
        painter.setPen(QPen(QColor(0, 0, 0, 6), 0.5))
        line_y = 30
        while line_y < self._height - 10:
            painter.drawLine(int(10), int(line_y), int(self._width - 10), int(line_y))
            line_y += 20

        # tag pills
        if self._tags:
            painter.setFont(TAG_FONT)
            metrics = painter.fontMetrics()
            x_off = 8.0
            for tag in self._tags:
                width = metrics.horizontalAdvance(tag) + 14
                rect = QRectF(x_off, 5, width, 16)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(TAG_COLORS.get(tag, TAG_COLOR_DEFAULT))))
                pill = QPainterPath()
                pill.addRoundedRect(rect, 8, 8)
                painter.drawPath(pill)
                painter.setPen(QPen(QColor("white"), 0.5))
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, tag)
                x_off += width + 6

        # resize grip
        painter.setPen(QPen(QColor(0, 0, 0, 45), 1))
        for i in range(3):
            offset = 4 + i * 4
            painter.drawLine(
                QPointF(self._width - offset, self._height - 2),
                QPointF(self._width - 2, self._height - offset),
            )

    # ------------------------------------------------------------------
    # serialization
    # ------------------------------------------------------------------
    def to_dict(self):
        return {
            "id": self.note_id,
            "content": self._content,
            "x": round(self.pos().x(), 2),
            "y": round(self.pos().y(), 2),
            "width": round(self._width, 2),
            "height": round(self._height, 2),
            "rotation": round(self.rotation(), 3),
            "color": self._color,
            "pinned": False,
            "tags": list(self._tags),
            "font_size": self._font_size,
            "z": self.zValue(),
        }
