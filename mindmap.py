"""Mind map: draggable nodes connected by smooth edges.

Nodes are `QGraphicsObject`s hosting a small `QTextEdit`; edges are plain
`QGraphicsItem`s that rebuild their path whenever one of their endpoints moves
or resizes.
"""

import math

from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt, QTimer, Signal
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
)

from config import (
    C_ACCENT,
    C_BORDER,
    C_BORDER_DARK,
    C_BG_HOVER,
    C_TEXT_MUTED,
    C_TEXT_PRIMARY,
    C_TOOL_BLUE,
    Z_MINDMAP_BASE,
    Z_MINDMAP_GHOST,
    Z_MINDMAP_MAX,
)
from note import NoteTextEdit
from util import clamp, new_id

NODE_COLORS = [
    "#FFFFFF", "#E8EDF2", "#E8DED0", "#D0E4D0", "#E4D0D8", "#E8E0D0", "#DDE6E0",
]
NODE_ROOT_COLOR = "#E8EDF2"
NODE_MIN_WIDTH = 110.0
NODE_MAX_WIDTH = 260.0
NODE_MIN_HEIGHT = 38.0
NODE_MAX_HEIGHT = 110.0
NODE_FONT_SIZE = 13

# -------------------------------------------------------------- hover slots
# Semi-transparent "you can add a box here" slots, revealed on node hover.
GHOST_GAP = 15.0
GHOST_WIDTH = 132.0
GHOST_HEIGHT = 32.0
GHOST_OPACITY = 0.60
GHOST_OPACITY_HOVER = 0.88
GHOST_Z = Z_MINDMAP_GHOST
# Children are always created to the right of their parent, so one slot per
# node is enough.
GHOST_DIRECTIONS = ("right",)

# Where the real child node lands, measured from the parent node's geometry.
CHILD_STEP_X = 170.0
CHILD_GAP_Y = 16.0

# Round "x" button shown in the node's top-right corner while it is hovered.
NODE_BUTTON_SIZE = 18


def node_button_style():
    """Translucent round button used to delete a node."""
    return """
        QPushButton {{
            background-color: rgba(255,255,255,110);
            color: {muted};
            border: none;
            border-radius: {radius}px;
            font-size: 12px;
            font-weight: bold;
            font-family: 'Segoe UI', Arial, sans-serif;
            padding: 0px;
        }}
        QPushButton:hover {{
            background-color: {accent};
            color: white;
        }}
    """.format(muted=C_TEXT_MUTED, accent=C_ACCENT, radius=NODE_BUTTON_SIZE // 2)

# The node body is covered by an embedded QTextEdit proxy widget, which eats
# the graphics-scene hover events, so the pointer is polled instead.
HOVER_POLL_MS = 70


class NodeTextEdit(NoteTextEdit):
    """Transparent single-purpose editor hosted inside a mind map node."""

    def apply_font_size(self, size):
        self.setStyleSheet(
            """
            QTextEdit {{
                background-color: transparent;
                border: none;
                font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
                font-size: {size}px;
                color: {color};
                padding: 2px;
            }}
            """.format(size=NODE_FONT_SIZE, color=C_TEXT_PRIMARY)
        )
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class MindMapEdge(QGraphicsItem):
    """Bezier connection between two nodes."""

    def __init__(self, source, target):
        super().__init__()
        self.source = source
        self.target = target
        self._path = QPainterPath()
        self.setZValue(1)
        self.rebuild()

    # ------------------------------------------------------------------
    def endpoints(self):
        src_rect = self.source.sceneBoundingRect()
        dst_rect = self.target.sceneBoundingRect()
        src_center = src_rect.center()
        dst_center = dst_rect.center()
        if dst_center.x() >= src_center.x():
            start = QPointF(src_rect.right(), src_center.y())
            end = QPointF(dst_rect.left(), dst_center.y())
        else:
            start = QPointF(src_rect.left(), src_center.y())
            end = QPointF(dst_rect.right(), dst_center.y())
        return start, end

    def rebuild(self):
        start, end = self.endpoints()
        dx = (end.x() - start.x()) * 0.5
        if abs(dx) < 20:
            dx = 20 if dx >= 0 else -20
        path = QPainterPath(start)
        path.cubicTo(
            QPointF(start.x() + dx, start.y()),
            QPointF(end.x() - dx, end.y()),
            end,
        )
        self._path = path

    def update_position(self):
        self.prepareGeometryChange()
        self.rebuild()
        self.update()

    def boundingRect(self):
        return self._path.boundingRect().adjusted(-8, -8, 8, 8)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(
            QPen(
                QColor(C_BORDER_DARK),
                1.4,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        painter.drawPath(self._path)


class GhostAddSlot(QGraphicsObject):
    """Semi-transparent dashed placeholder that creates a child node.

    Slots live at scene level (they are *not* children of the node) so their
    painting can never be clipped by the node's bounding rect; the manager
    keeps them glued to their node through ``follow()``.
    """

    activated = Signal(str, str)

    def __init__(self, node_id, direction, parent=None):
        super().__init__(parent)
        self.node_id = node_id
        self.direction = direction
        self._hovered = False
        self._w = GHOST_WIDTH
        self._h = GHOST_HEIGHT
        self.setZValue(GHOST_Z)
        self.setAcceptHoverEvents(True)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip("Click to add a child node to the right")
        self.setVisible(False)

    # ------------------------------------------------------------------
    def size(self):
        return self._w, self._h

    def boundingRect(self):
        return QRectF(0.0, 0.0, self._w, self._h)

    def follow(self, node_x, node_y, node_w, node_h):
        """Re-anchor to the right edge of the node (move / resize changes)."""
        pos = QPointF(node_x + node_w + GHOST_GAP, node_y + (node_h - self._h) / 2.0)
        if self.pos() != pos:
            self.setPos(pos)

    # ------------------------------------------------------------------
    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            self.activated.emit(self.node_id, self.direction)
            return
        super().mousePressEvent(event)

    # ------------------------------------------------------------------
    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(GHOST_OPACITY_HOVER if self._hovered else GHOST_OPACITY)

        accent = QColor(C_TOOL_BLUE)
        rect = QRectF(0.7, 0.7, self._w - 1.4, self._h - 1.4)
        path = QPainterPath()
        path.addRoundedRect(rect, 9, 9)

        fill = QColor(C_BG_HOVER)
        painter.setBrush(QBrush(fill))
        pen = QPen(accent, 1.3, Qt.PenStyle.DashLine)
        pen.setDashPattern([3.0, 2.4])
        painter.setPen(pen)
        painter.drawPath(path)

        # "+" glyph on the left
        cx = 18.0
        cy = rect.center().y()
        painter.setPen(
            QPen(accent, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        painter.drawLine(QPointF(cx - 5.5, cy), QPointF(cx + 5.5, cy))
        painter.drawLine(QPointF(cx, cy - 5.5), QPointF(cx, cy + 5.5))

        font = QFont()
        font.setPointSizeF(8.4)
        painter.setFont(font)
        painter.setPen(QPen(accent))
        painter.drawText(
            QRectF(cx + 11.0, rect.top(), rect.width() - cx - 15.0, rect.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            "Add child",
        )


class MindMapNode(QGraphicsObject):
    deleted = Signal(str)
    content_changed = Signal(str, str)
    moved = Signal(str, float, float)
    raise_requested = Signal(str)
    child_requested = Signal(str)

    def __init__(
        self,
        node_id,
        text="New idea",
        x=0.0,
        y=0.0,
        parent_id=None,
        color=None,
        parent=None,
    ):
        super().__init__(parent)
        self.node_id = node_id
        self.parent_id = parent_id
        self._text = text or ""
        self._color = color or NODE_COLORS[0]
        self._dragging = False
        self._drag_start_pos = None
        self._drag_start_scene = None
        self.edges = []
        self.ghosts = []

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setPos(x, y)
        # Mind map nodes always stack above the sticky-note band.
        self.setZValue(Z_MINDMAP_BASE)

        self.text_edit = NodeTextEdit(sticky_note=self)
        self.text_edit.setPlainText(self._text)
        self.text_edit.textChanged.connect(self._on_text_changed)
        self.text_edit.setFixedSize(int(NODE_MAX_WIDTH), int(NODE_MIN_HEIGHT))

        self.text_proxy = QGraphicsProxyWidget(self)
        self.text_proxy.setWidget(self.text_edit)

        # --- delete button (top-right, revealed while hovering) -----------
        self.del_btn = QPushButton("\u00d7")
        self.del_btn.setFixedSize(NODE_BUTTON_SIZE, NODE_BUTTON_SIZE)
        self.del_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.del_btn.setToolTip("Delete this node and its children")
        self.del_btn.setStyleSheet(node_button_style())
        self.del_btn.clicked.connect(self._confirm_delete)

        self.del_proxy = QGraphicsProxyWidget(self)
        self.del_proxy.setWidget(self.del_btn)
        self.del_proxy.setZValue(10)

        self._width = NODE_MIN_WIDTH
        self._height = NODE_MIN_HEIGHT
        self._auto_size()
        self._place_delete_button()
        self.del_proxy.setVisible(False)

    # ------------------------------------------------------------------
    # content
    # ------------------------------------------------------------------
    def _on_text_changed(self):
        self._text = self.text_edit.toPlainText()
        self._auto_size()
        self.content_changed.emit(self.node_id, self._text)

    def get_text(self):
        return self._text

    def set_text(self, text):
        self._text = text or ""
        if self.text_edit.toPlainText() != self._text:
            self.text_edit.blockSignals(True)
            self.text_edit.setPlainText(self._text)
            self.text_edit.blockSignals(False)
        self._auto_size()

    def rename(self):
        text, ok = QInputDialog.getText(
            self._dialog_parent(), "Rename Node", "Text:", text=self._text
        )
        if ok:
            self.set_text(text)
            self.content_changed.emit(self.node_id, self._text)

    def _auto_size(self):
        metrics = self.text_edit.fontMetrics()
        plain = self._text or " "
        longest = 0
        for line in plain.splitlines() or [" "]:
            longest = max(longest, metrics.horizontalAdvance(line))
        available = NODE_MAX_WIDTH - 20
        lines = max(1, int(math.ceil((longest + 20) / available))) if longest else 1
        width = clamp(longest + 26, NODE_MIN_WIDTH, NODE_MAX_WIDTH)
        height = clamp(NODE_MIN_HEIGHT + (lines - 1) * 18, NODE_MIN_HEIGHT, NODE_MAX_HEIGHT)
        if abs(width - self._width) < 1 and abs(height - self._height) < 1:
            return
        self._width = width
        self._height = height
        self._apply_size()
        for edge in list(self.edges):
            edge.update_position()

    def _apply_size(self):
        self.prepareGeometryChange()
        self.text_edit.setFixedSize(int(self._width), int(self._height))
        self.text_proxy.setGeometry(QRectF(0, 0, self._width, self._height))
        self._place_delete_button()
        self.sync_ghosts()
        self.update()

    def _place_delete_button(self):
        if getattr(self, "del_proxy", None) is None:
            return
        self.del_proxy.setPos(self._width - NODE_BUTTON_SIZE - 3, 3)

    # ------------------------------------------------------------------
    # hover slots
    # ------------------------------------------------------------------
    def size(self):
        return self._width, self._height

    def sync_ghosts(self):
        """Keep the hover slots glued to this node's geometry."""
        if not self.ghosts:
            return
        x, y = self.pos().x(), self.pos().y()
        for ghost in self.ghosts:
            ghost.follow(x, y, self._width, self._height)

    def show_ghosts(self):
        self.set_controls_visible(True)
        if not self.ghosts:
            return
        self.sync_ghosts()
        for ghost in self.ghosts:
            ghost.setVisible(True)

    def hide_ghosts(self):
        self.set_controls_visible(False)
        for ghost in self.ghosts:
            ghost.setVisible(False)

    def set_controls_visible(self, visible):
        """Show / hide the node's own controls (the delete button)."""
        if getattr(self, "del_proxy", None) is not None:
            self.del_proxy.setVisible(bool(visible))

    def ghosts_visible(self):
        return any(ghost.isVisible() for ghost in self.ghosts)

    def set_color(self, color):
        if color:
            self._color = color
            self.update()

    def boundingRect(self):
        return QRectF(-3, -3, self._width + 6, self._height + 6)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self._width, self._height), 6, 6)
        painter.setBrush(QBrush(QColor(self._color)))
        if self.isSelected():
            painter.setPen(QPen(QColor(C_TOOL_BLUE), 1.8))
        elif self.parent_id is None:
            painter.setPen(QPen(QColor(C_ACCENT), 1.2))
        else:
            painter.setPen(QPen(QColor(C_BORDER), 1.0))
        painter.drawPath(path)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for edge in list(self.edges):
                edge.update_position()
            self.sync_ghosts()
        return super().itemChange(change, value)

    # ------------------------------------------------------------------
    # drag
    # ------------------------------------------------------------------
    def _dialog_parent(self):
        if self.scene() and self.scene().views():
            return self.scene().views()[0]
        return None

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
        self.raise_requested.emit(self.node_id)

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
                self.moved.emit(self.node_id, self.pos().x(), self.pos().y())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.raise_requested.emit(self.node_id)
        super().mousePressEvent(event)

    def show_context_menu(self, global_pos):
        menu = QMenu(self._dialog_parent())

        act_child = QAction("Add child node", menu)
        act_child.triggered.connect(lambda: self.child_requested.emit(self.node_id))
        menu.addAction(act_child)

        act_rename = QAction("Rename…", menu)
        act_rename.triggered.connect(self.rename)
        menu.addAction(act_rename)

        color_menu = menu.addMenu("Color")
        for color in NODE_COLORS:
            action = QAction(color, color_menu)
            action.setCheckable(True)
            action.setChecked(color == self._color)
            action.triggered.connect(lambda _=False, c=color: self.set_color(c))
            color_menu.addAction(action)

        menu.addSeparator()
        act_delete = QAction("Delete node and children", menu)
        act_delete.triggered.connect(self._confirm_delete)
        menu.addAction(act_delete)

        act_delete_all = QAction("Delete entire mind map\u2026", menu)
        act_delete_all.triggered.connect(self._confirm_delete_all)
        menu.addAction(act_delete_all)

        menu.exec(global_pos)

    def _confirm_delete(self):
        reply = QMessageBox.question(
            self._dialog_parent(),
            "Delete Node",
            "Delete this node and all of its children?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.deleted.emit(self.node_id)

    def _confirm_delete_all(self):
        view = self._dialog_parent()
        handler = getattr(view, "delete_all_mindmaps", None)
        if callable(handler):
            handler()
        else:
            self._confirm_delete()

    def to_dict(self):
        return {
            "id": self.node_id,
            "text": self._text,
            "x": round(self.pos().x(), 2),
            "y": round(self.pos().y(), 2),
            "parent_id": self.parent_id,
            "color": self._color,
            "z": self.zValue(),
        }


class MindMapManager:
    """Owns every mind map node of the current project."""

    def __init__(self, canvas):
        self.canvas = canvas
        self.nodes = {}
        self.edges = []
        self._hover_node_id = None
        # The node body is covered by an embedded QTextEdit proxy widget which
        # swallows the scene hover events, so the pointer is polled instead.
        self._hover_timer = QTimer(canvas)
        self._hover_timer.setInterval(HOVER_POLL_MS)
        self._hover_timer.timeout.connect(self._poll_hover)
        self._hover_timer.start()

    # ------------------------------------------------------------------
    def create_node(self, x, y, text="New idea", parent_id=None, color=None,
                    node_id=None, persist=True):
        node_id = node_id or new_id("node")
        while node_id in self.nodes:
            node_id = new_id("node")
        node = MindMapNode(
            node_id, text=text, x=x, y=y, parent_id=parent_id,
            color=color or (NODE_ROOT_COLOR if parent_id is None else NODE_COLORS[0]),
        )
        node.deleted.connect(self.remove_subtree)
        node.content_changed.connect(self._on_node_changed)
        node.moved.connect(self._on_node_moved)
        node.raise_requested.connect(self.raise_node)
        node.child_requested.connect(self.add_child_to)
        self.canvas.scene.addItem(node)
        self.nodes[node_id] = node
        self._attach_ghosts(node)

        self._link(node, parent_id)

        if persist:
            self.canvas.save_mindmaps()
        return node

    def _link(self, node, parent_id):
        """Connect `node` to `parent_id` (no-op when the parent is unknown)."""
        parent = self.nodes.get(parent_id) if parent_id else None
        if parent is None or parent is node:
            node.parent_id = None
            return None
        node.parent_id = parent.node_id
        edge = MindMapEdge(parent, node)
        self.canvas.scene.addItem(edge)
        self.edges.append(edge)
        parent.edges.append(edge)
        node.edges.append(edge)
        return edge

    def add_root(self, x, y, text="New idea"):
        return self.create_node(x, y, text=text, parent_id=None)

    def add_child_to(self, parent_id):
        """Context-menu entry point: same result as clicking the right slot."""
        return self.create_child_at(parent_id, "right")

    # ------------------------------------------------------------------
    # hover slots
    # ------------------------------------------------------------------
    def _attach_ghosts(self, node):
        """Give a node its semi-transparent add-slot(s)."""
        for direction in GHOST_DIRECTIONS:
            ghost = GhostAddSlot(node.node_id, direction)
            ghost.activated.connect(self.create_child_at)
            self.canvas.scene.addItem(ghost)
            node.ghosts.append(ghost)
        node.sync_ghosts()

    def _detach_ghosts(self, node):
        for ghost in node.ghosts:
            if ghost.scene() is not None:
                self.canvas.scene.removeItem(ghost)
        node.ghosts = []
        if self._hover_node_id == node.node_id:
            self._hover_node_id = None

    def _ghost_at(self, scene_pos):
        for node in self.nodes.values():
            for ghost in node.ghosts:
                if ghost.isVisible() and ghost.sceneBoundingRect().contains(scene_pos):
                    return ghost
        return None

    def _clear_hover(self):
        node = self.nodes.get(self._hover_node_id) if self._hover_node_id else None
        if node is not None:
            node.hide_ghosts()
        self._hover_node_id = None

    def _set_hover_node(self, node_id):
        if node_id == self._hover_node_id:
            return
        self._clear_hover()
        node = self.nodes.get(node_id)
        if node is None:
            return
        node.show_ghosts()
        self._hover_node_id = node_id

    def _poll_hover(self):
        """Reveal the slots while the pointer rests on a node, hide them after."""
        canvas = self.canvas
        if not self.nodes or not canvas.isVisible():
            self._clear_hover()
            return
        if (
            QApplication.activePopupWidget() is not None
            or QApplication.activeModalWidget() is not None
            or getattr(canvas, "_panning", False)
            or any(node._dragging for node in self.nodes.values())
        ):
            self._clear_hover()
            return
        window = canvas.window()
        if window is not None and not window.isActiveWindow():
            self._clear_hover()
            return

        view_pos = canvas.viewport().mapFromGlobal(QCursor.pos())
        if not canvas.viewport().rect().contains(view_pos):
            self._clear_hover()
            return

        scene_pos = canvas.mapToScene(view_pos)
        if self._ghost_at(scene_pos) is not None:
            return  # the pointer is on a slot: keep them on screen

        matches = [
            node for node in self.nodes.values()
            if node.sceneBoundingRect().contains(scene_pos)
        ]
        if not matches:
            self._clear_hover()
            return
        best = max(matches, key=lambda item: item.zValue())
        self._set_hover_node(best.node_id)

    def create_child_at(self, node_id, direction="right"):
        """Create a child node - children always grow to the right.

        Siblings are stacked vertically and never overlap: the new node starts
        below the bottom edge of the ones that are already there.
        """
        parent = self.nodes.get(node_id)
        if parent is None:
            return None
        siblings = [n for n in self.nodes.values() if n.parent_id == node_id]
        node = self.create_node(
            0.0, 0.0, text="New idea", parent_id=node_id, persist=False
        )

        parent_w, _parent_h = parent.size()
        px, py = parent.pos().x(), parent.pos().y()
        x = px + parent_w + CHILD_STEP_X
        if siblings:
            bottom = max(s.pos().y() + s.size()[1] for s in siblings)
            y = max(bottom + CHILD_GAP_Y, py)
        else:
            y = py
        node.setPos(x, y)
        node.sync_ghosts()

        self._clear_hover()
        self.canvas.save_mindmaps()
        self.canvas.update_scene_rect()
        self.canvas.status_message.emit("Child node added to “{}”".format(parent.get_text()))
        return node

    def shutdown(self):
        self._hover_timer.stop()
        for node in self.nodes.values():
            node.hide_ghosts()
        self._hover_node_id = None

    def subtree_ids(self, node_id):
        """Every node id in the subtree rooted at `node_id` (inclusive)."""
        ids = set()
        pending = [node_id]
        while pending:
            current = pending.pop()
            if current in ids or current not in self.nodes:
                continue
            ids.add(current)
            pending.extend(
                n.node_id for n in self.nodes.values() if n.parent_id == current
            )
        return ids

    def remove_all(self):
        """Delete every node and edge of the current mind map."""
        count = len(self.nodes)
        if count == 0:
            return 0
        self.clear()
        self.canvas.save_mindmaps()
        self.canvas.update_scene_rect()
        self.canvas.status_message.emit(
            "Deleted the whole mind map ({} node(s))".format(count)
        )
        return count

    def remove_subtree(self, node_id):
        node = self.nodes.get(node_id)
        if not node:
            return
        for child_id in [n.node_id for n in self.nodes.values() if n.parent_id == node_id]:
            self.remove_subtree(child_id)
        node = self.nodes.pop(node_id, None)
        if not node:
            return
        for edge in list(node.edges):
            self._drop_edge(edge)
        for parent in self.nodes.values():
            for edge in list(parent.edges):
                if edge.source is node or edge.target is node:
                    self._drop_edge(edge)
        self._detach_ghosts(node)
        self.canvas.scene.removeItem(node)
        self.canvas.save_mindmaps()

    def _drop_edge(self, edge):
        if edge in self.edges:
            self.edges.remove(edge)
        for holder in (edge.source, edge.target):
            if holder is not None and edge in holder.edges:
                holder.edges.remove(edge)
        edge.source = None
        edge.target = None
        if edge.scene() is not None:
            self.canvas.scene.removeItem(edge)

    def _on_node_changed(self, node_id, text):
        self.canvas.save_mindmaps()

    def _on_node_moved(self, node_id, x, y):
        self.canvas.save_mindmaps()

    def raise_node(self, node_id):
        """Front of the mind map band - never above the note band."""
        node = self.nodes.get(node_id)
        if node is None:
            return
        top = max([n.zValue() for n in self.nodes.values()] or [Z_MINDMAP_BASE])
        node.setZValue(clamp(top + 1.0, Z_MINDMAP_BASE, Z_MINDMAP_MAX))

    # ------------------------------------------------------------------
    def clear(self):
        self._hover_node_id = None
        for edge in list(self.edges):
            if edge.scene() is not None:
                self.canvas.scene.removeItem(edge)
        self.edges = []
        for node in list(self.nodes.values()):
            self._detach_ghosts(node)
            node.edges = []
            if node.scene() is not None:
                self.canvas.scene.removeItem(node)
        self.nodes = {}

    def load(self, data):
        self.clear()
        if not isinstance(data, dict):
            return
        records = data.get("nodes", [])
        if not isinstance(records, list):
            return
        pending = []
        for record in records:
            if not isinstance(record, dict) or not record.get("id"):
                continue
            node = self.create_node(
                float(record.get("x", 0) or 0),
                float(record.get("y", 0) or 0),
                text=str(record.get("text", "") or ""),
                parent_id=record.get("parent_id"),
                color=record.get("color"),
                node_id=str(record["id"]),
                persist=False,
            )
            try:
                raw_z = float(record.get("z", Z_MINDMAP_BASE) or Z_MINDMAP_BASE)
            except (TypeError, ValueError):
                raw_z = Z_MINDMAP_BASE
            if not (Z_MINDMAP_BASE <= raw_z <= Z_MINDMAP_MAX):
                # legacy files stored notes and nodes in the same z band
                raw_z = Z_MINDMAP_BASE + len(pending)
            node.setZValue(raw_z)
            pending.append((node, record.get("parent_id")))
        # second pass: parents may appear after their children in the file
        for node, parent_id in pending:
            self._link(node, parent_id)

    def to_dict(self):
        return {"nodes": [node.to_dict() for node in self.nodes.values()]}

    def all_nodes(self):
        return list(self.nodes.values())

    def count(self):
        return len(self.nodes)
