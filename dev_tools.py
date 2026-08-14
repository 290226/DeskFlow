"""Dev tool launcher buttons and configuration dialog."""

import platform
import subprocess

from PySide6.QtCore import Qt
from config import C_TEXT_PRIMARY, C_BG_CARD, C_BG_MAIN, C_BG_HOVER, C_BORDER, C_TOOL_BLUE, C_TOOL_HOVER, C_TOOL_BG
from PySide6.QtWidgets import QPushButton, QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QInputDialog, QMessageBox

from config import C_TEXT_PRIMARY, C_BG_CARD, C_BG_MAIN, C_BG_HOVER, C_BORDER, C_TOOL_BLUE, C_TOOL_HOVER


class DevToolButton(QPushButton):
    def __init__(self, name, command, args, parent=None):
        super().__init__(parent)
        self.name = name
        self.command = command
        self.args = args
        self.setText(name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{ background-color: {C_TOOL_BG}; color: {C_TOOL_BLUE}; border: 1px solid {C_BORDER}; border-radius: 4px; padding: 6px 14px; font-size: 12px; font-weight: 600; font-family: 'Helvetica Neue', Arial, sans-serif; }}
            QPushButton:hover {{ background-color: {C_TOOL_BLUE}; color: white; border-color: {C_TOOL_BLUE}; }}
            QPushButton:pressed {{ background-color: {C_TOOL_HOVER}; }}
        """)
        self.clicked.connect(self._launch)

    def _launch(self):
        try:
            flags = subprocess.CREATE_NEW_CONSOLE if platform.system() == "Windows" else 0
            subprocess.Popen([self.command] + self.args, shell=False, creationflags=flags)
        except FileNotFoundError:
            QMessageBox.warning(self, "Launch Failed", f"Command not found: {self.command}\nPlease ensure it is installed and in PATH.")
        except Exception as e:
            QMessageBox.warning(self, "Launch Failed", str(e))


class DevToolsDialog(QDialog):
    def __init__(self, tools, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tool Configuration")
        self.setMinimumWidth(480)
        self.tools = list(tools)
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(f"""
            QDialog {{ background-color: {C_BG_MAIN}; }}
            QPushButton {{ background-color: {C_BG_CARD}; color: {C_TEXT_PRIMARY}; border: 1px solid {C_BORDER}; border-radius: 4px; padding: 6px 12px; font-family: 'Helvetica Neue', Arial, sans-serif; }}
            QPushButton:hover {{ background-color: {C_BG_HOVER}; }}
            QListWidget {{ background-color: {C_BG_CARD}; border: 1px solid {C_BORDER}; border-radius: 4px; color: {C_TEXT_PRIMARY}; padding: 4px; font-family: 'Helvetica Neue', Arial, sans-serif; }}
            QListWidget::item {{ padding: 8px; border-radius: 3px; }}
            QListWidget::item:selected {{ background-color: {C_TOOL_BG}; color: {C_TOOL_BLUE}; }}
        """)
        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        self._refresh()
        layout.addWidget(self.list_widget)
        h = QHBoxLayout()
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add)
        del_btn = QPushButton("Remove")
        del_btn.clicked.connect(self._delete)
        h.addWidget(add_btn)
        h.addWidget(del_btn)
        h.addStretch()
        layout.addLayout(h)
        ok_btn = QPushButton("Done")
        ok_btn.setStyleSheet(f"QPushButton {{ background-color: {C_TOOL_BLUE}; color: white; border: none; border-radius: 4px; padding: 8px 20px; font-weight: bold; }} QPushButton:hover {{ background-color: {C_TOOL_HOVER}; }}")
        ok_btn.clicked.connect(self.accept)
        layout.addWidget(ok_btn)

    def _refresh(self):
        self.list_widget.clear()
        for t in self.tools:
            self.list_widget.addItem(f"{t['name']}: {t['command']} {' '.join(t['args'])}")

    def _add(self):
        name, ok = QInputDialog.getText(self, "Add Tool", "Name:")
        if not ok or not name: return
        cmd, ok = QInputDialog.getText(self, "Add Tool", "Command:")
        if not ok or not cmd: return
        args_str, ok = QInputDialog.getText(self, "Add Tool", "Arguments (space-separated):")
        args = args_str.split() if args_str else []
        self.tools.append({"name": name, "command": cmd, "args": args})
        self._refresh()

    def _delete(self):
        idx = self.list_widget.currentRow()
        if idx >= 0:
            del self.tools[idx]
            self._refresh()

    def get_tools(self):
        return self.tools
