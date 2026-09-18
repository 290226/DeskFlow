"""Canvas: the sticky-note board that hosts notes and mind maps.

Adds (compared to v0.1.0)
-------------------------
* zoom (Ctrl + wheel), pan (middle mouse / hold Space), reset, fit-to-content
* background grid that can be toggled
* a real context menu (notes, mind map, paste, arrange, zoom, undo delete)
* Delete / Ctrl+D / Ctrl+Z keyboard handling with a small undo stack
* debounced auto-save so typing does not hammer the disk
"""

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QCursor,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QMenu,
    QMessageBox,
)

from deskflow.config import (
    C_ACCENT,
    C_BG_CANVAS,
    C_GRID,
    C_GRID_STRONG,
    CANVAS_MIN_SIZE,
    CANVAS_PADDING,
    NOTE_DEFAULT_HEIGHT,
    NOTE_DEFAULT_WIDTH,
    UNDO_STACK_LIMIT,
    ZOOM_MAX,
    ZOOM_MIN,
    ZOOM_STEP,
    Z_NOTE_BASE,
    Z_NOTE_MAX,
)
from deskflow.ui.mindmap import MindMapManager
from deskflow.ui.note import StickyNote
from deskflow.core.util import clamp, new_id

SAVE_DEBOUNCE_MS = 600


class CanvasScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.grid_visible = True

    def drawBackground(self, painter: QPainter, rect: QRectF):
        painter.fillRect(rect, QColor(C_BG_CANVAS))
        if not self.grid_visible:
            return
        step = 32
        left = int(math.floor(rect.left() / step) * step)
        top = int(math.floor(rect.top() / step) * step)
        right = int(math.ceil(rect.right()))
        bottom = int(math.ceil(rect.bottom()))
        if (right - left) / step > 400 or (bottom - top) / step > 400:
            return
        painter.setPen(QPen(QColor(C_GRID), 1))
        x = left
        while x < right:
            painter.drawLine(x, top, x, bottom)
            x += step
        y = top
        while y < bottom:
            painter.drawLine(left, y, right, y)
            y += step
        painter.setPen(QPen(QColor(C_GRID_STRONG), 1.2))
        x = left
        while x < right:
            if x % (step * 4) == 0:
                painter.drawLine(x, top, x, bottom)
            x += step
        y = top
        while y < bottom:
            if y % (step * 4) == 0:
                painter.drawLine(left, y, right, y)
            y += step


class DesktopCanvas(QGraphicsView):
    content_changed = Signal()
    status_message = Signal(str)

    def __init__(self, data_manager, parent=None):
        super().__init__(parent)
        self.data_manager = data_manager
        self.current_project_id = None
        self.notes = {}
        self.mind_map_manager = None
        self._undo_stack = []
        self._saving_blocked = False
        self._panning = False
        self._space_held = False

        self.scene = CanvasScene(self)
        self.setScene(self.scene)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setBackgroundBrush(QColor(C_BG_CANVAS))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)

        self._pan_origin = None

        self.scene.setSceneRect(0, 0, CANVAS_MIN_SIZE, CANVAS_MIN_SIZE)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(SAVE_DEBOUNCE_MS)
        self._save_timer.timeout.connect(self.flush)

    # ==================================================================
    # project lifecycle
    # ==================================================================
    def load_project(self, proj_id):
        self._saving_blocked = True
        self.clear_all()
        # the previous mind map manager owns a hover-polling timer: stop it
        if self.mind_map_manager is not None:
            self.mind_map_manager.shutdown()
        self.current_project_id = proj_id
        if proj_id:
            for record in self.data_manager.load_notes(proj_id):
                self._create_note_from_dict(record, persist=False)
            self.mind_map_manager = MindMapManager(self)
            self.mind_map_manager.load(self.data_manager.load_mindmaps(proj_id))
        else:
            self.mind_map_manager = MindMapManager(self)
        self._saving_blocked = False
        self._undo_stack = []
        self.update_scene_rect()
        self.content_changed.emit()

    def clear_all(self):
        if self.mind_map_manager is not None:
            self.mind_map_manager.clear()
        for note in list(self.notes.values()):
            self._remove_note_item(note)
        self.notes = {}

    def _remove_note_item(self, note):
        try:
            note.text_edit.clearFocus()
        except RuntimeError:
            pass
        if note.scene() is not None:
            self.scene.removeItem(note)

    # ==================================================================
    # notes
    # ==================================================================
    def _viewport_center_scene(self):
        return self.mapToScene(self.viewport().rect().center())

    def suggest_note_position(self):
        center = self._viewport_center_scene()
        return (
            center.x() - NOTE_DEFAULT_WIDTH / 2 + random.randint(-60, 60),
            center.y() - NOTE_DEFAULT_HEIGHT / 2 + random.randint(-60, 60),
        )

    def add_note(self, x=None, y=None, content="", **extra):
        if not self.current_project_id:
            self.status_message.emit("Create or open a project first.")
            return None
        if x is None or y is None:
            x, y = self.suggest_note_position()
        payload = {
            "id": extra.pop("id", None) or new_id("note"),
            "content": content,
            "x": x,
            "y": y,
            "rotation": extra.pop("rotation", random.uniform(-1.8, 1.8)),
        }
        payload.update(extra)
        note = self._create_note_from_dict(payload, persist=False)
        self.save_notes()
        self.update_scene_rect()
        return note

    def _create_note_from_dict(self, record, persist=False):
        note = StickyNote(
            note_id=str(record.get("id") or new_id("note")),
            content=record.get("content", ""),
            x=float(record.get("x", 100) or 0),
            y=float(record.get("y", 100) or 0),
            width=float(record.get("width", NOTE_DEFAULT_WIDTH) or NOTE_DEFAULT_WIDTH),
            height=float(record.get("height", NOTE_DEFAULT_HEIGHT) or NOTE_DEFAULT_HEIGHT),
            rotation=float(record.get("rotation", 0) or 0),
            color=record.get("color"),
            tags=record.get("tags"),
            font_size=record.get("font_size"),
            z=float(record.get("z", 0) or 0),
        )
        note.deleted.connect(self.delete_note)
        note.content_changed.connect(self.on_note_content_changed)
        note.moved.connect(self.on_note_moved)
        note.tags_changed.connect(self.on_note_tags_changed)
        note.raise_requested.connect(self.raise_note)

        self.scene.addItem(note)
        self.notes[note.note_id] = note
        if persist:
            self.save_notes()
        return note

    def delete_note(self, note_id, record_undo=True):
        note = self.notes.pop(note_id, None)
        if not note:
            return
        if record_undo:
            self._push_undo("note", note.to_dict())
        self._remove_note_item(note)
        self.save_notes()
        self.update_scene_rect()

    def duplicate_note(self, note_id):
        note = self.notes.get(note_id)
        if not note:
            return None
        payload = note.duplicate()
        payload["rotation"] = random.uniform(-1.8, 1.8)
        clone = self._create_note_from_dict(payload, persist=False)
        self.save_notes()
        self.update_scene_rect()
        return clone

    def raise_note(self, note_id):
        """Bring a note to the front *of the note band*.

        Notes and mind map nodes are stacked in separate z bands, so raising a
        note can never push it above a mind map node.
        """
        note = self.notes.get(note_id)
        if not note:
            return
        top = max([n.zValue() for n in self.notes.values()] or [Z_NOTE_BASE])
        note.setZValue(float(clamp(top + 1.0, Z_NOTE_BASE, Z_NOTE_MAX)))

    def on_note_content_changed(self, note_id, content):
        self.schedule_save()

    def on_note_moved(self, note_id, x, y):
        self.schedule_save()
        self.update_scene_rect()

    def on_note_tags_changed(self, note_id, tags):
        self.save_notes()
        self.content_changed.emit()

    def all_tags(self):
        tags = set()
        for note in self.notes.values():
            tags.update(note.get_tags())
        return sorted(tags)

    def filter_by_tag(self, tag):
        """Dim every note that does not carry `tag` (None or '' clears it)."""
        tag = (tag or "").strip().lower()
        for note in self.notes.values():
            if not tag:
                note.setOpacity(1.0)
            else:
                note.setOpacity(1.0 if tag in note.get_tags() else 0.22)

    def arrange_notes(self):
        if not self.notes:
            return
        gap = 40
        columns = max(1, int(math.ceil(math.sqrt(len(self.notes)))))
        width = max(n.to_dict()["width"] for n in self.notes.values()) + gap
        height = max(n.to_dict()["height"] for n in self.notes.values()) + gap
        ordered = sorted(
            self.notes.values(), key=lambda n: (round(n.pos().y() / 50), n.pos().x())
        )
        origin = self._viewport_center_scene()
        start_x = origin.x() - (columns * width) / 2
        start_y = origin.y() - (math.ceil(len(ordered) / columns) * height) / 2
        for index, note in enumerate(ordered):
            row, col = divmod(index, columns)
            note.setRotation(0.0)
            note.setPos(start_x + col * width, start_y + row * height)
        self.save_notes()
        self.update_scene_rect()
        self.status_message.emit("Arranged {} notes".format(len(ordered)))

    # ==================================================================
    # mind maps
    # ==================================================================
    def add_mind_map(self, x=None, y=None, text="New idea"):
        if not self.current_project_id:
            self.status_message.emit("Create or open a project first.")
            return None
        if self.mind_map_manager is None:
            self.mind_map_manager = MindMapManager(self)
        if x is None or y is None:
            center = self._viewport_center_scene()
            x = center.x() - 80 + random.randint(-40, 40)
            y = center.y() - 20 + random.randint(-40, 40)
        node = self.mind_map_manager.create_node(x, y, text=text)
        self.update_scene_rect()
        return node

    def delete_mind_map_selection(self):
        if self.mind_map_manager is None:
            return
        selected = [
            item
            for item in self.scene.selectedItems()
            if hasattr(item, "node_id")
        ]
        if not selected:
            return
        reply = QMessageBox.question(
            self,
            "Delete Nodes",
            "Delete {} selected node(s) and their children?".format(len(selected)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        targets = set()
        for item in selected:
            targets |= self.mind_map_manager.subtree_ids(item.node_id)
        payload = [
            node.to_dict()
            for node in self.mind_map_manager.nodes.values()
            if node.node_id in targets
        ]
        if payload:
            self._push_undo("nodes", payload)
        for item in list(selected):
            self.mind_map_manager.remove_subtree(item.node_id)
        self.update_scene_rect()

    def delete_all_mindmaps(self):
        """Delete every node of the current mind map (asks first, undoable)."""
        if self.mind_map_manager is None or not self.mind_map_manager.nodes:
            self.status_message.emit("There is no mind map to delete.")
            return
        count = self.mind_map_manager.count()
        reply = QMessageBox.question(
            self,
            "Delete Mind Map",
            "Delete the whole mind map ({} node(s)) and every connection?".format(count),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._push_undo(
            "nodes", [node.to_dict() for node in self.mind_map_manager.nodes.values()]
        )
        self.mind_map_manager.remove_all()

    # ==================================================================
    # persistence
    # ==================================================================
    def schedule_save(self):
        if self._saving_blocked:
            return
        self._save_timer.start()

    def flush(self):
        self._save_timer.stop()
        self.save_notes(silent=True)

    def save_notes(self, silent=False):
        if self._saving_blocked or not self.current_project_id:
            return
        payload = [note.to_dict() for note in self.notes.values()]
        ok = self.data_manager.save_notes(self.current_project_id, payload)
        self.data_manager.touch_project(self.current_project_id)
        if not silent:
            self.content_changed.emit()
            if not ok:
                self.status_message.emit("Failed to save notes.")

    def save_mindmaps(self):
        if self._saving_blocked or not self.current_project_id:
            return
        if self.mind_map_manager is None:
            return
        self.data_manager.save_mindmaps(self.current_project_id, self.mind_map_manager.to_dict())
        self.data_manager.touch_project(self.current_project_id)
        self.content_changed.emit()

    # ==================================================================
    # undo
    # ==================================================================
    def _push_undo(self, kind, payload):
        self._undo_stack.append((kind, payload))
        if len(self._undo_stack) > UNDO_STACK_LIMIT:
            self._undo_stack.pop(0)

    def can_undo(self):
        return bool(self._undo_stack)

    def undo(self):
        if not self._undo_stack:
            self.status_message.emit("Nothing to undo.")
            return
        kind, payload = self._undo_stack.pop()
        if kind == "note" and isinstance(payload, dict):
            payload = dict(payload)
            payload["id"] = new_id("note")
            self._create_note_from_dict(payload, persist=False)
            self.save_notes()
            self.update_scene_rect()
            self.status_message.emit("Restored a note")
        elif kind == "nodes" and isinstance(payload, list):
            if self.mind_map_manager is None:
                self.mind_map_manager = MindMapManager(self)
            manager = self.mind_map_manager
            pending = []
            for record in payload:
                record = dict(record)
                node = manager.create_node(
                    float(record.get("x", 0) or 0),
                    float(record.get("y", 0) or 0),
                    text=str(record.get("text", "")),
                    parent_id=None,
                    color=record.get("color"),
                    node_id=str(record.get("id")),
                    persist=False,
                )
                pending.append((node, record.get("parent_id")))
            # second pass: a child may come before its parent in the payload
            for node, parent_id in pending:
                manager._link(node, parent_id)
            self.save_mindmaps()
            self.update_scene_rect()
            self.status_message.emit("Restored {} node(s)".format(len(payload)))

    # ==================================================================
    # geometry / zoom
    # ==================================================================
    def update_scene_rect(self):
        rect = self.scene.itemsBoundingRect()
        if not rect.isEmpty():
            rect = rect.adjusted(-CANVAS_PADDING, -CANVAS_PADDING, CANVAS_PADDING, CANVAS_PADDING)
        baseline = QRectF(0, 0, CANVAS_MIN_SIZE, CANVAS_MIN_SIZE)
        rect = rect.united(baseline)
        self.scene.setSceneRect(rect)

    def zoom_factor(self):
        return float(self.transform().m11())

    def set_zoom(self, factor):
        factor = clamp(factor, ZOOM_MIN, ZOOM_MAX)
        self.resetTransform()
        self.scale(factor, factor)
        self.status_message.emit("Zoom {}%".format(int(factor * 100)))

    def zoom_in(self):
        self.set_zoom(self.zoom_factor() * ZOOM_STEP)

    def zoom_out(self):
        self.set_zoom(self.zoom_factor() / ZOOM_STEP)

    def reset_zoom(self):
        self.set_zoom(1.0)

    def fit_all(self):
        rect = self.scene.itemsBoundingRect()
        if rect.isEmpty():
            self.reset_zoom()
            return
        rect = rect.adjusted(-60, -60, 60, 60)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        factor = self.zoom_factor()
        if factor > ZOOM_MAX or factor < ZOOM_MIN:
            self.set_zoom(clamp(factor, ZOOM_MIN, ZOOM_MAX))

    def set_grid_visible(self, visible):
        self.scene.grid_visible = bool(visible)
        self.scene.update()

    def focus_note(self, note_id):
        note = self.notes.get(note_id)
        if not note:
            return False
        self.centerOn(note)
        note.setSelected(True)
        note.flash()
        return True

    def focus_node(self, node_id):
        if self.mind_map_manager is None:
            return False
        node = self.mind_map_manager.nodes.get(node_id)
        if not node:
            return False
        self.centerOn(node)
        node.setSelected(True)
        return True

    # ==================================================================
    # events
    # ==================================================================
    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta == 0:
                return
            factor = ZOOM_STEP if delta > 0 else 1.0 / ZOOM_STEP
            new_zoom = clamp(self.zoom_factor() * factor, ZOOM_MIN, ZOOM_MAX)
            if abs(new_zoom - self.zoom_factor()) < 1e-4:
                return
            self.set_zoom(new_zoom)
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and self._space_held
        ):
            self._panning = True
            self._pan_origin = event.position().toPoint()
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            current = event.position().toPoint()
            delta = current - self._pan_origin
            self._pan_origin = current
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning:
            self._panning = False
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.itemAt(event.position().toPoint()) is None:
                pos = self.mapToScene(event.position().toPoint())
                self.add_note(pos.x(), pos.y())
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Space:
            self._space_held = True
        if event.matches(Qt.Key.KeySequence(Qt.Key.Key_Unknown)):
            pass
        if key == Qt.Key.Key_Delete:
            self.delete_selection()
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            self.scene.clearSelection()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self._space_held = False
        super().keyReleaseEvent(event)

    def delete_selection(self):
        selected_notes = [item for item in self.scene.selectedItems() if isinstance(item, StickyNote)]
        if selected_notes:
            reply = QMessageBox.question(
                self,
                "Delete Notes",
                "Delete {} selected note(s)?".format(len(selected_notes)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            for note in selected_notes:
                self.delete_note(note.note_id)
            return
        self.delete_mind_map_selection()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        scene_pos = self.mapToScene(event.pos())

        menu.addAction(self._action("Add note", lambda: self.add_note(scene_pos.x(), scene_pos.y()), "Ctrl+N"))
        menu.addAction(
            self._action("Add mind map", lambda: self.add_mind_map(scene_pos.x(), scene_pos.y()), "Ctrl+M")
        )

        clipboard_text = QApplication.clipboard().text().strip()
        act_paste = self._action(
            "Paste as note", lambda: self.add_note(scene_pos.x(), scene_pos.y(), content=clipboard_text)
        )
        act_paste.setEnabled(bool(clipboard_text))
        menu.addAction(act_paste)

        selected_notes = [item for item in self.scene.selectedItems() if isinstance(item, StickyNote)]
        menu.addSeparator()
        act_dup = self._action(
            "Duplicate selected note",
            lambda: self.duplicate_note(selected_notes[0].note_id),
            "Ctrl+D",
        )
        act_dup.setEnabled(len(selected_notes) == 1)
        menu.addAction(act_dup)

        selected_nodes = [
            item for item in self.scene.selectedItems() if hasattr(item, "node_id")
        ]
        act_delete = self._action("Delete selected item(s)   (Del)", self.delete_selection)
        act_delete.setEnabled(bool(selected_notes or selected_nodes))
        menu.addAction(act_delete)

        act_delete_map = self._action("Delete entire mind map\u2026", self.delete_all_mindmaps)
        act_delete_map.setEnabled(
            bool(self.mind_map_manager and self.mind_map_manager.nodes)
        )
        menu.addAction(act_delete_map)

        act_undo = self._action("Undo delete", self.undo, "Ctrl+Shift+Z")
        act_undo.setEnabled(self.can_undo())
        menu.addAction(act_undo)

        menu.addSeparator()
        grid_action = QAction("Show grid", menu)
        grid_action.setCheckable(True)
        grid_action.setChecked(self.scene.grid_visible)
        grid_action.toggled.connect(self.set_grid_visible)
        menu.addAction(grid_action)

        menu.addAction(self._action("Arrange notes", self.arrange_notes))
        menu.addAction(self._action("Fit to content", self.fit_all, "Ctrl+0"))
        menu.addAction(self._action("Reset zoom", self.reset_zoom))
        menu.addAction(self._action("Zoom in", self.zoom_in, "Ctrl+="))
        menu.addAction(self._action("Zoom out", self.zoom_out, "Ctrl+-"))

        menu.exec(event.globalPos())

    @staticmethod
    def _action(text, slot, shortcut=None):
        action = QAction(text)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(shortcut)
        return action

    # ==================================================================
    # stats
    # ==================================================================
    def stats(self):
        notes = self.notes.values()
        return {
            "notes": len(self.notes),
            "nodes": self.mind_map_manager.count() if self.mind_map_manager else 0,
            "tags": len({tag for note in notes for tag in note.get_tags()}),
        }
