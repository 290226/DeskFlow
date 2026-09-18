"""Rich note editor dialog (used to edit an existing sticky note in depth)."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config import (
    C_ACCENT,
    C_BORDER,
    C_TEXT_MUTED,
    C_TEXT_PRIMARY,
    NOTE_COLORS,
    NOTE_FONT_SIZES,
)
from util import clean_tags

FONT_CHOICES = [("Small", NOTE_FONT_SIZES["small"]),
                ("Medium", NOTE_FONT_SIZES["medium"]),
                ("Large", NOTE_FONT_SIZES["large"])]


class NoteEditorDialog(QDialog):
    """Standalone editor: plain text, tags, colour and text size."""

    def __init__(self, payload=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Note Editor")
        self.resize(560, 480)
        payload = payload or {}
        self._color = payload.get("color") if payload.get("color") in NOTE_COLORS else NOTE_COLORS[0]
        self._color_buttons = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlainText(payload.get("content", ""))
        self.text_edit.setStyleSheet(
            "QPlainTextEdit { background: #FFFFFF; border: 1px solid %s; border-radius: 4px; "
            "padding: 8px; font-size: 13px; color: %s; }" % (C_BORDER, C_TEXT_PRIMARY)
        )
        self.text_edit.textChanged.connect(self._update_counter)
        layout.addWidget(self.text_edit, 1)

        self.counter = QLabel("0 characters")
        self.counter.setStyleSheet("color: %s; font-size: 11px;" % C_TEXT_MUTED)
        layout.addWidget(self.counter)

        tag_row = QHBoxLayout()
        tag_row.addWidget(QLabel("Tags"))
        self.tag_input = QLineEdit(", ".join(payload.get("tags") or []))
        self.tag_input.setPlaceholderText("comma separated, e.g. idea, urgent")
        self.tag_input.setStyleSheet(
            "QLineEdit { border: 1px solid %s; border-radius: 4px; padding: 5px; font-size: 12px; }"
            % C_BORDER
        )
        tag_row.addWidget(self.tag_input, 1)
        layout.addLayout(tag_row)

        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("Color"))
        for color in NOTE_COLORS:
            button = QToolButton()
            button.setFixedSize(24, 24)
            button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            button.setCheckable(True)
            button.setChecked(color == self._color)
            button.setStyleSheet(
                "QToolButton { background-color: %s; border: 1px solid %s; border-radius: 12px; }"
                "QToolButton:checked { border: 2px solid %s; }" % (color, C_BORDER, C_ACCENT)
            )
            button.clicked.connect(lambda _=False, c=color: self._pick_color(c))
            self._color_buttons.append(button)
            color_row.addWidget(button)
        color_row.addStretch()
        color_row.addWidget(QLabel("Size"))
        self.size_combo = QComboBox()
        for label, size in FONT_CHOICES:
            self.size_combo.addItem(label, size)
        index = self.size_combo.findData(payload.get("font_size") or NOTE_FONT_SIZES["medium"])
        if index >= 0:
            self.size_combo.setCurrentIndex(index)
        color_row.addWidget(self.size_combo)
        layout.addLayout(color_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._update_counter()

    # ------------------------------------------------------------------
    def _pick_color(self, color):
        self._color = color
        for button, candidate in zip(self._color_buttons, NOTE_COLORS):
            button.setChecked(candidate == color)

    def _update_counter(self):
        text = self.text_edit.toPlainText()
        self.counter.setText(
            "{} characters · {} lines".format(len(text), text.count("\n") + 1)
        )

    def payload(self):
        return {
            "content": self.text_edit.toPlainText(),
            "tags": clean_tags(self.tag_input.text()),
            "color": self._color,
            "font_size": self.size_combo.currentData() or NOTE_FONT_SIZES["medium"],
        }
