"""Desktop canvas for sticky notes."""

import random
from datetime import datetime

from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QMenu
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QAction

from config import C_BG_CANVAS, C_BG_CARD, C_BORDER, C_TEXT_PRIMARY, C_BG_HOVER
from note import StickyNote


class DesktopCanvas(QGraphicsView):
    note_deleted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setStyleSheet(f"QGraphicsView {{ background-color: {C_BG_CANVAS}; border: none; }}")
        self.scene.setSceneRect(0, 0, 2000, 1500)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.notes = {}
        self.data_manager = None
        self.current_project = None

    def set_data_manager(self, dm):
        self.data_manager = dm

    def load_project(self, proj_id):
        self.current_project = proj_id
        self.clear_notes()
        for data in self.data_manager.load_notes(proj_id):
            self._add_note_from_data(data)

    def clear_notes(self):
        for note in list(self.notes.values()):
            self.scene.removeItem(note)
        self.notes.clear()

    def _add_note_from_data(self, data):
        note = StickyNote(
            note_id=data["id"],
            content=data.get("content", ""),
            x=data.get("x", 100),
            y=data.get("y", 100),
            width=data.get("width", 220),
            height=data.get("height", 180),
            rotation=data.get("rotation", random.uniform(-5, 5)),
            color=data.get("color"),

        )
        note.deleted.connect(self._on_note_deleted)
        note.content_changed.connect(self._on_note_changed)
        note.moved.connect(self._on_note_moved)

        self.scene.addItem(note)
        self.notes[note.note_id] = note

    def add_note(self, x=None, y=None):
        if not self.current_project:
            return
        if x is None:
            x = random.randint(80, 500)
        if y is None:
            y = random.randint(80, 400)
        note_id = f"note_{datetime.now().strftime('%Y%m%d%H%M%S')}_{random.randint(1000,9999)}"
        note = StickyNote(
            note_id=note_id, content="",
            x=x, y=y, width=220, height=180,
            rotation=random.uniform(-4, 4),
        )
        note.deleted.connect(self._on_note_deleted)
        note.content_changed.connect(self._on_note_changed)
        note.moved.connect(self._on_note_moved)
        self.scene.addItem(note)
        self.notes[note_id] = note
        self._save_notes()

    def _on_note_deleted(self, note_id):
        if note_id in self.notes:
            self.scene.removeItem(self.notes[note_id])
            del self.notes[note_id]
            self._save_notes()
            self.note_deleted.emit(note_id)

    def _on_note_changed(self, *args):
        self._save_notes()

    def _on_note_moved(self, note_id, x, y):
        self._save_notes()

    def _save_notes(self):
        if self.data_manager and self.current_project:
            self.data_manager.save_notes(
                self.current_project,
                [n.to_dict() for n in self.notes.values()]
            )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            menu = QMenu(self)
            menu.setStyleSheet(f"""
                QMenu {{ background-color: {C_BG_CARD}; border: 1px solid {C_BORDER}; border-radius: 4px; padding: 4px; }}
                QMenu::item {{ padding: 6px 20px; color: {C_TEXT_PRIMARY}; border-radius: 3px; }}
                QMenu::item:selected {{ background-color: {C_BG_HOVER}; }}
            """)
            act = QAction("Add Note", self)
            act.triggered.connect(lambda: self.add_note(
                self.mapToScene(event.position().toPoint()).x(),
                self.mapToScene(event.position().toPoint()).y()
            ))
            menu.addAction(act)
            menu.exec(self.mapToGlobal(event.position().toPoint()))
            return
        super().mousePressEvent(event)
