#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeskFlow - 桌面项目管理器
一个像散落在桌面的纸片一样的项目管理工具
支持便签、日历、开发工具快捷启动
"""

import sys
import os
import json
import random
import subprocess
import platform
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QTextEdit, QGraphicsView, QGraphicsScene,
    QGraphicsItem, QGraphicsObject, QGraphicsProxyWidget,
    QCalendarWidget, QListWidget, QListWidgetItem, QLineEdit, QDialog,
    QFormLayout, QMessageBox, QFileDialog, QMenu, QInputDialog
)
from PySide6.QtCore import (
    Qt, QRectF, QPointF, QPropertyAnimation, QEasingCurve, QTimer,
    Signal
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QFontDatabase, QPainterPath,
    QLinearGradient, QAction
)

# ============ 配置 ============
APP_NAME = "DeskFlow"
DATA_DIR = Path(__file__).parent / "data"
PROJECTS_FILE = DATA_DIR / "projects.json"

# 便签颜色（温暖柔和的色调）
NOTE_COLORS = [
    "#FFF9C4",  # 淡黄
    "#FFCCBC",  # 淡橙
    "#C8E6C9",  # 淡绿
    "#B3E5FC",  # 淡蓝
    "#E1BEE7",  # 淡紫
    "#F8BBD0",  # 淡粉
    "#FFE0B2",  # 杏色
    "#DCEDC8",  # 淡青柠
]

# ============ 数据管理 ============
class DataManager:
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.projects = self._load_projects()

    def _load_projects(self):
        if PROJECTS_FILE.exists():
            with open(PROJECTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("projects", [])
        return []

    def _save_projects(self):
        with open(PROJECTS_FILE, "w", encoding="utf-8") as f:
            json.dump({"projects": self.projects}, f, ensure_ascii=False, indent=2)

    def create_project(self, name):
        proj_id = f"proj_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        project = {
            "id": proj_id,
            "name": name,
            "created_at": datetime.now().isoformat()
        }
        self.projects.append(project)
        self._save_projects()

        proj_dir = DATA_DIR / "projects" / proj_id
        proj_dir.mkdir(parents=True, exist_ok=True)

        with open(proj_dir / "notes.json", "w", encoding="utf-8") as f:
            json.dump({"notes": []}, f, ensure_ascii=False, indent=2)

        default_config = {
            "dev_tools": self._get_default_dev_tools(),
            "last_opened_files": [],
            "plans": []
        }
        with open(proj_dir / "config.json", "w", encoding="utf-8") as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)

        return project

    def _get_default_dev_tools(self):
        system = platform.system()
        tools = []
        if system == "Windows":
            tools = [
                {"name": "PyCharm", "command": "pycharm64.exe", "args": ["."]},
                {"name": "VSCode", "command": "code", "args": ["."]},
                {"name": "Terminal", "command": "cmd", "args": ["/k", "cd", "."]}
            ]
        elif system == "Darwin":
            tools = [
                {"name": "PyCharm", "command": "open", "args": ["-a", "PyCharm", "."]},
                {"name": "VSCode", "command": "code", "args": ["."]},
                {"name": "Terminal", "command": "open", "args": ["-a", "Terminal", "."]}
            ]
        else:
            tools = [
                {"name": "PyCharm", "command": "pycharm", "args": ["."]},
                {"name": "VSCode", "command": "code", "args": ["."]},
                {"name": "Terminal", "command": "gnome-terminal", "args": ["--working-directory=."]}
            ]
        return tools

    def get_project_dir(self, proj_id):
        return DATA_DIR / "projects" / proj_id

    def load_notes(self, proj_id):
        notes_file = self.get_project_dir(proj_id) / "notes.json"
        if notes_file.exists():
            with open(notes_file, "r", encoding="utf-8") as f:
                return json.load(f).get("notes", [])
        return []

    def save_notes(self, proj_id, notes):
        notes_file = self.get_project_dir(proj_id) / "notes.json"
        with open(notes_file, "w", encoding="utf-8") as f:
            json.dump({"notes": notes}, f, ensure_ascii=False, indent=2)

    def load_config(self, proj_id):
        config_file = self.get_project_dir(proj_id) / "config.json"
        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"dev_tools": [], "last_opened_files": [], "plans": []}

    def save_config(self, proj_id, config):
        config_file = self.get_project_dir(proj_id) / "config.json"
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def delete_project(self, proj_id):
        self.projects = [p for p in self.projects if p["id"] != proj_id]
        self._save_projects()
        import shutil
        proj_dir = self.get_project_dir(proj_id)
        if proj_dir.exists():
            shutil.rmtree(proj_dir)


# ============ 便签纸片组件 ============
class StickyNote(QGraphicsObject):
    deleted = Signal(str)
    content_changed = Signal(str, str)
    moved = Signal(str, float, float)
    pin_changed = Signal(str, bool)

    def __init__(self, note_id, content="", x=100, y=100, width=220, height=180,
                 rotation=0, color="#FFF9C4", pinned=False, parent=None):
        super().__init__(parent)
        self.note_id = note_id
        self._content = content
        self._width = width
        self._height = height
        self._color = color
        self._pinned = pinned
        self._dragging = False
        self._drag_start_pos = None

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not pinned)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        self.setPos(x, y)
        self.setRotation(rotation)

        # 创建文本编辑框
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(content)
        self.text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: transparent;
                border: none;
                font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
                font-size: 14px;
                color: #333;
                padding: 8px;
                padding-top: 28px;
            }}
        """)
        self.text_edit.textChanged.connect(self._on_text_changed)

        self.proxy = QGraphicsProxyWidget(self)
        self.proxy.setWidget(self.text_edit)
        self.proxy.setPos(0, 0)
        self.proxy.setGeometry(QRectF(0, 0, width, height))

        self.text_edit.setFixedSize(int(width), int(height))

    def _on_text_changed(self):
        self._content = self.text_edit.toPlainText()
        self.content_changed.emit(self.note_id, self._content)

    def boundingRect(self):
        return QRectF(-5, -5, self._width + 10, self._height + 10)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 阴影效果
        shadow_rect = QRectF(4, 4, self._width, self._height)
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(shadow_rect, 8, 8)
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(8):
            alpha = 30 - i * 3
            painter.setBrush(QBrush(QColor(0, 0, 0, alpha)))
            offset_rect = QRectF(4 + i*0.5, 4 + i*0.5, self._width, self._height)
            offset_path = QPainterPath()
            offset_path.addRoundedRect(offset_rect, 8, 8)
            painter.drawPath(offset_path)

        # 便签主体
        rect = QRectF(0, 0, self._width, self._height)
        path = QPainterPath()
        path.addRoundedRect(rect, 8, 8)

        # 渐变背景
        gradient = QLinearGradient(0, 0, 0, self._height)
        base_color = QColor(self._color)
        gradient.setColorAt(0, base_color.lighter(105))
        gradient.setColorAt(1, base_color)
        painter.setBrush(QBrush(gradient))

        # 边框
        pen = QPen(QColor(0, 0, 0, 30))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawPath(path)

        # 纸张纹理效果（横线）
        painter.setPen(QPen(QColor(0, 0, 0, 8), 1))
        line_y = 35
        while line_y < self._height - 10:
            painter.drawLine(int(10), int(line_y), int(self._width - 10), int(line_y))
            line_y += 25

        # 图钉
        pin_x = self._width / 2
        pin_y = 12

        # 图钉阴影
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 40)))
        painter.drawEllipse(QPointF(pin_x + 1, pin_y + 1), 7, 7)

        # 图钉主体
        if self._pinned:
            painter.setBrush(QBrush(QColor("#E74C3C")))
        else:
            painter.setBrush(QBrush(QColor("#95A5A6")))
        painter.setPen(QPen(QColor(0, 0, 0, 50), 1))
        painter.drawEllipse(QPointF(pin_x, pin_y), 6, 6)

        # 图钉高光
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, 120)))
        painter.drawEllipse(QPointF(pin_x - 2, pin_y - 2), 3, 3)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.pos()
            pin_x = self._width / 2
            pin_y = 12
            dist = ((pos.x() - pin_x) ** 2 + (pos.y() - pin_y) ** 2) ** 0.5
            if dist < 12:
                self._pinned = not self._pinned
                self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not self._pinned)
                self.pin_changed.emit(self.note_id, self._pinned)
                self.update()
                return

            self._dragging = True
            self._drag_start_pos = self.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            if self._drag_start_pos != self.pos():
                self.moved.emit(self.note_id, self.pos().x(), self.pos().y())
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        reply = QMessageBox.question(
            None, "删除便签", "确定要删除这个便签吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.deleted.emit(self.note_id)
        super().mouseDoubleClickEvent(event)

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
            "pinned": self._pinned,
            "created_at": datetime.now().isoformat()
        }


# ============ 桌面画布 ============
class DesktopCanvas(QGraphicsView):
    note_deleted = Signal(str)
    note_updated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.setStyleSheet("""
            QGraphicsView {
                background-color: #F5F0E8;
                border: none;
            }
        """)

        self.scene.setSceneRect(0, 0, 1200, 800)

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

        notes_data = self.data_manager.load_notes(proj_id)
        for note_data in notes_data:
            self._add_note_from_data(note_data)

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
            rotation=data.get("rotation", random.uniform(-8, 8)),
            color=data.get("color", random.choice(NOTE_COLORS)),
            pinned=data.get("pinned", False)
        )
        note.deleted.connect(self._on_note_deleted)
        note.content_changed.connect(self._on_note_changed)
        note.moved.connect(self._on_note_moved)
        note.pin_changed.connect(self._on_pin_changed)
        self.scene.addItem(note)
        self.notes[note.note_id] = note

    def add_note(self, x=None, y=None):
        if x is None:
            x = random.randint(50, 600)
        if y is None:
            y = random.randint(50, 400)

        note_id = f"note_{datetime.now().strftime('%Y%m%d%H%M%S')}_{random.randint(1000,9999)}"
        color = random.choice(NOTE_COLORS)
        rotation = random.uniform(-6, 6)

        note = StickyNote(
            note_id=note_id,
            content="",
            x=x, y=y,
            width=220, height=180,
            rotation=rotation,
            color=color,
            pinned=False
        )
        note.deleted.connect(self._on_note_deleted)
        note.content_changed.connect(self._on_note_changed)
        note.moved.connect(self._on_note_moved)
        note.pin_changed.connect(self._on_pin_changed)
        self.scene.addItem(note)
        self.notes[note_id] = note

        self._save_notes()

        # 入场动画
        # 入场动画 - 使用透明度渐变代替（避免scale属性动画失效）
        note.setOpacity(0)
        from PySide6.QtCore import QPropertyAnimation
        anim = QPropertyAnimation(note, b"opacity")
        anim.setDuration(300)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        # 保持引用防止被垃圾回收
        self._animations = getattr(self, '_animations', [])
        self._animations.append(anim)

    def _on_note_deleted(self, note_id):
        if note_id in self.notes:
            note = self.notes[note_id]
            self.scene.removeItem(note)
            del self.notes[note_id]
            self._save_notes()
            self.note_deleted.emit(note_id)

    def _on_note_changed(self, note_id, content):
        self._save_notes()
        self.note_updated.emit()

    def _on_note_moved(self, note_id, x, y):
        self._save_notes()

    def _on_pin_changed(self, note_id, pinned):
        self._save_notes()

    def _save_notes(self):
        if self.data_manager and self.current_project:
            notes_data = [note.to_dict() for note in self.notes.values()]
            self.data_manager.save_notes(self.current_project, notes_data)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            menu = QMenu(self)
            add_action = QAction("添加便签", self)
            add_action.triggered.connect(lambda: self.add_note(
                self.mapToScene(event.pos()).x(),
                self.mapToScene(event.pos()).y()
            ))
            menu.addAction(add_action)
            menu.exec(self.mapToGlobal(event.pos()))
            return
        super().mousePressEvent(event)


# ============ 开发工具按钮 ============
class DevToolButton(QPushButton):
    def __init__(self, name, command, args, parent=None):
        super().__init__(parent)
        self.name = name
        self.command = command
        self.args = args

        self.setText(f"{name}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("""
            QPushButton {
                background-color: #4A90D9;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #357ABD;
            }
            QPushButton:pressed {
                background-color: #2A6299;
            }
        """)
        self.clicked.connect(self.launch)

    def launch(self):
        try:
            subprocess.Popen([self.command] + self.args, 
                           shell=False,
                           creationflags=subprocess.CREATE_NEW_CONSOLE if platform.system() == "Windows" else 0)
        except FileNotFoundError:
            QMessageBox.warning(self, "启动失败", 
                              f"找不到命令: {self.command}\n请检查该工具是否已安装并添加到系统PATH。")
        except Exception as e:
            QMessageBox.warning(self, "启动失败", str(e))


# ============ 开发工具管理对话框 ============
class DevToolsDialog(QDialog):
    def __init__(self, tools, parent=None):
        super().__init__(parent)
        self.setWindowTitle("开发工具配置")
        self.setMinimumWidth(500)
        self.tools = tools
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        self.list_widget = QListWidget()
        self.refresh_list()
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("添加工具")
        add_btn.clicked.connect(self.add_tool)
        del_btn = QPushButton("删除选中")
        del_btn.clicked.connect(self.delete_tool)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(del_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        layout.addWidget(ok_btn)

    def refresh_list(self):
        self.list_widget.clear()
        for tool in self.tools:
            item = QListWidgetItem(f"{tool['name']}: {tool['command']} {' '.join(tool['args'])}")
            self.list_widget.addItem(item)

    def add_tool(self):
        name, ok1 = QInputDialog.getText(self, "添加工具", "工具名称:")
        if not ok1 or not name:
            return
        command, ok2 = QInputDialog.getText(self, "添加工具", "启动命令:")
        if not ok2 or not command:
            return
        args_str, ok3 = QInputDialog.getText(self, "添加工具", "参数（用空格分隔）:")
        args = args_str.split() if args_str else []

        self.tools.append({"name": name, "command": command, "args": args})
        self.refresh_list()

    def delete_tool(self):
        idx = self.list_widget.currentRow()
        if idx >= 0:
            del self.tools[idx]
            self.refresh_list()

    def get_tools(self):
        return self.tools


# ============ 主窗口 ============
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DeskFlow - 桌面项目管理器")
        self.setMinimumSize(1200, 800)

        self.data_manager = DataManager()
        self.current_project_id = None

        self.setup_ui()
        self.load_projects()

        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.timeout.connect(self.auto_save)
        self.auto_save_timer.start(30000)

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ===== 左侧边栏 =====
        sidebar = QWidget()
        sidebar.setFixedWidth(260)
        sidebar.setStyleSheet("""
            QWidget {
                background-color: #2C3E50;
                color: #ECF0F1;
            }
            QPushButton {
                background-color: #34495E;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #4A6278;
            }
            QComboBox {
                background-color: #34495E;
                color: white;
                border: 1px solid #4A6278;
                border-radius: 4px;
                padding: 6px;
            }
            QListWidget {
                background-color: #34495E;
                border: 1px solid #4A6278;
                border-radius: 4px;
                color: white;
                padding: 4px;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background-color: #4A90D9;
            }
            QCalendarWidget {
                background-color: #34495E;
            }
            QCalendarWidget QTableView {
                background-color: #34495E;
                color: white;
                selection-background-color: #4A90D9;
            }
            QLabel {
                color: #BDC3C7;
                font-size: 12px;
            }
        """)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 12, 12, 12)
        sidebar_layout.setSpacing(10)

        # 标题
        title = QLabel("DeskFlow")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: white;")
        sidebar_layout.addWidget(title)

        # 项目选择
        sidebar_layout.addWidget(QLabel("选择项目:"))
        self.project_combo = QComboBox()
        self.project_combo.currentIndexChanged.connect(self.on_project_changed)
        sidebar_layout.addWidget(self.project_combo)

        # 项目操作按钮
        proj_btn_layout = QHBoxLayout()
        new_proj_btn = QPushButton("新建")
        new_proj_btn.clicked.connect(self.create_new_project)
        del_proj_btn = QPushButton("删除")
        del_proj_btn.clicked.connect(self.delete_current_project)
        proj_btn_layout.addWidget(new_proj_btn)
        proj_btn_layout.addWidget(del_proj_btn)
        sidebar_layout.addLayout(proj_btn_layout)

        sidebar_layout.addSpacing(10)

        # 日历
        sidebar_layout.addWidget(QLabel("日历"))
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.setMaximumHeight(220)
        sidebar_layout.addWidget(self.calendar)

        # 今日计划
        sidebar_layout.addWidget(QLabel("今日计划"))
        self.plan_list = QListWidget()
        self.plan_list.setMaximumHeight(150)
        sidebar_layout.addWidget(self.plan_list)

        # 添加计划
        plan_input_layout = QHBoxLayout()
        self.plan_input = QLineEdit()
        self.plan_input.setPlaceholderText("输入计划按回车...")
        self.plan_input.returnPressed.connect(self.add_plan)
        self.plan_input.setStyleSheet("""
            QLineEdit {
                background-color: #34495E;
                color: white;
                border: 1px solid #4A6278;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        plan_input_layout.addWidget(self.plan_input)
        add_plan_btn = QPushButton("+")
        add_plan_btn.setFixedWidth(30)
        add_plan_btn.clicked.connect(self.add_plan)
        plan_input_layout.addWidget(add_plan_btn)
        sidebar_layout.addLayout(plan_input_layout)

        sidebar_layout.addStretch()

        # 关于
        about = QLabel("DeskFlow v0.1.0")
        about.setStyleSheet("color: #7F8C8D; font-size: 11px;")
        about.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(about)

        main_layout.addWidget(sidebar)

        # ===== 右侧主区域 =====
        right_area = QWidget()
        right_layout = QVBoxLayout(right_area)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # 顶部工具栏
        toolbar = QWidget()
        toolbar.setFixedHeight(50)
        toolbar.setStyleSheet("""
            QWidget {
                background-color: #ECF0F1;
                border-bottom: 1px solid #BDC3C7;
            }
        """)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(15, 5, 15, 5)

        self.project_label = QLabel("未选择项目")
        self.project_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2C3E50;")
        toolbar_layout.addWidget(self.project_label)
        toolbar_layout.addStretch()

        add_note_btn = QPushButton("添加便签")
        add_note_btn.setStyleSheet("""
            QPushButton {
                background-color: #F39C12;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #E67E22;
            }
        """)
        add_note_btn.clicked.connect(self.add_note)
        toolbar_layout.addWidget(add_note_btn)

        config_btn = QPushButton("工具配置")
        config_btn.setStyleSheet("""
            QPushButton {
                background-color: #7F8C8D;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #616A6B;
            }
        """)
        config_btn.clicked.connect(self.open_dev_tools_config)
        toolbar_layout.addWidget(config_btn)

        right_layout.addWidget(toolbar)

        # 桌面画布
        self.canvas = DesktopCanvas()
        self.canvas.set_data_manager(self.data_manager)
        self.canvas.note_deleted.connect(self.on_note_deleted)
        right_layout.addWidget(self.canvas)

        # 底部开发工具栏
        dev_bar = QWidget()
        dev_bar.setFixedHeight(55)
        dev_bar.setStyleSheet("""
            QWidget {
                background-color: #34495E;
                border-top: 1px solid #2C3E50;
            }
        """)
        self.dev_bar_layout = QHBoxLayout(dev_bar)
        self.dev_bar_layout.setContentsMargins(15, 8, 15, 8)
        self.dev_bar_layout.setSpacing(10)

        dev_label = QLabel("快速启动:")
        dev_label.setStyleSheet("color: #BDC3C7; font-size: 13px;")
        self.dev_bar_layout.addWidget(dev_label)

        right_layout.addWidget(dev_bar)

        main_layout.addWidget(right_area)

    def load_projects(self):
        self.project_combo.clear()
        projects = self.data_manager.projects
        if not projects:
            self.data_manager.create_project("我的第一个项目")
            projects = self.data_manager.projects

        for proj in projects:
            self.project_combo.addItem(proj["name"], proj["id"])

        if projects:
            self.load_project(projects[0]["id"])

    def load_project(self, proj_id):
        self.current_project_id = proj_id
        proj = next((p for p in self.data_manager.projects if p["id"] == proj_id), None)
        if proj:
            self.project_label.setText(f"{proj['name']}")

        self.canvas.load_project(proj_id)
        self.load_dev_tools()
        self.load_plans()

    def on_project_changed(self, index):
        if index >= 0:
            proj_id = self.project_combo.itemData(index)
            if proj_id:
                self.load_project(proj_id)

    def create_new_project(self):
        name, ok = QInputDialog.getText(self, "新建项目", "项目名称:")
        if ok and name.strip():
            proj = self.data_manager.create_project(name.strip())
            self.project_combo.addItem(proj["name"], proj["id"])
            self.project_combo.setCurrentIndex(self.project_combo.count() - 1)

    def delete_current_project(self):
        if self.current_project_id:
            reply = QMessageBox.question(
                self, "删除项目", "确定要删除当前项目吗？所有便签和配置都将丢失！",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.data_manager.delete_project(self.current_project_id)
                self.load_projects()

    def add_note(self):
        if not self.current_project_id:
            QMessageBox.warning(self, "提示", "请先选择一个项目")
            return
        self.canvas.add_note()

    def on_note_deleted(self, note_id):
        pass

    def load_dev_tools(self):
        while self.dev_bar_layout.count() > 1:
            item = self.dev_bar_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()

        if not self.current_project_id:
            return

        config = self.data_manager.load_config(self.current_project_id)
        tools = config.get("dev_tools", [])

        for tool in tools:
            btn = DevToolButton(tool["name"], tool["command"], tool["args"])
            self.dev_bar_layout.addWidget(btn)

        self.dev_bar_layout.addStretch()

    def open_dev_tools_config(self):
        if not self.current_project_id:
            return
        config = self.data_manager.load_config(self.current_project_id)
        tools = config.get("dev_tools", [])

        dialog = DevToolsDialog(tools, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            config["dev_tools"] = dialog.get_tools()
            self.data_manager.save_config(self.current_project_id, config)
            self.load_dev_tools()

    def load_plans(self):
        self.plan_list.clear()
        if not self.current_project_id:
            return
        config = self.data_manager.load_config(self.current_project_id)
        plans = config.get("plans", [])
        for plan in plans:
            item = QListWidgetItem(plan.get("text", ""))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if plan.get("done") else Qt.CheckState.Unchecked)
            self.plan_list.addItem(item)

    def add_plan(self):
        text = self.plan_input.text().strip()
        if not text or not self.current_project_id:
            return

        config = self.data_manager.load_config(self.current_project_id)
        plans = config.get("plans", [])
        plans.append({"text": text, "done": False, "created_at": datetime.now().isoformat()})
        config["plans"] = plans
        self.data_manager.save_config(self.current_project_id, config)

        self.plan_input.clear()
        self.load_plans()

    def auto_save(self):
        pass

    def closeEvent(self, event):
        if self.canvas:
            self.canvas._save_notes()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    font = QFont("Microsoft YaHei", 10)
    if not QFontDatabase.hasFamily("Microsoft YaHei"):
        font = QFont("PingFang SC", 10)
    if not QFontDatabase.hasFamily("PingFang SC"):
        font = QFont("Arial", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
