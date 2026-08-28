"""Main application window."""

from datetime import datetime
from config import (
    C_BG_MAIN, C_BG_CARD, C_BG_HOVER, C_BORDER, C_BORDER_DARK,
    C_TEXT_PRIMARY, C_TEXT_MUTED, C_ACCENT, C_ACCENT_HOVER
)
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QMessageBox, QInputDialog, QListWidgetItem, QDialog
)
from PySide6.QtCore import Qt, QTimer


from data_manager import DataManager
from sidebar import SidebarDrawer
from canvas import DesktopCanvas
from dev_tools import DevToolButton, DevToolsDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DeskFlow")
        self.setMinimumSize(1000, 700)
        self.resize(1200, 800)
        self.data_manager = DataManager()
        self.current_project_id = None
        self._setup_ui()
        self._load_projects()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._auto_save)
        self._timer.start(30000)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Top bar
        toolbar = QWidget()
        toolbar.setFixedHeight(46)
        toolbar.setStyleSheet(f"""
            QWidget {{ background-color: {C_BG_CARD}; border-bottom: 1px solid {C_BORDER}; }}
            QPushButton {{ background-color: {C_BG_MAIN}; color: {C_TEXT_PRIMARY}; border: 1px solid {C_BORDER}; border-radius: 4px; padding: 5px 12px; font-size: 12px; font-family: 'Helvetica Neue', Arial, sans-serif; }}
            QPushButton:hover {{ background-color: {C_BG_HOVER}; border-color: {C_BORDER_DARK}; }}
            QLabel {{ color: {C_TEXT_PRIMARY}; font-size: 15px; font-weight: bold; font-family: 'Georgia', serif; }}
        """)
        tl = QHBoxLayout(toolbar)
        tl.setContentsMargins(18, 6, 18, 6)
        self.project_label = QLabel("No project selected")
        self.project_label.setStyleSheet(f"color: {C_TEXT_MUTED}; font-style: italic;")
        tl.addWidget(self.project_label)
        tl.addStretch()
        add_btn = QPushButton("+ Note")
        add_btn.setStyleSheet(f"QPushButton {{ background-color: {C_ACCENT}; color: white; border: none; border-radius: 4px; padding: 5px 16px; font-weight: bold; font-family: 'Helvetica Neue', Arial, sans-serif; }} QPushButton:hover {{ background-color: {C_ACCENT_HOVER}; }}")
        add_btn.clicked.connect(self._add_note)
        tl.addWidget(add_btn)
        cfg_btn = QPushButton("Tools")
        cfg_btn.clicked.connect(self._open_tool_config)
        tl.addWidget(cfg_btn)
        mm_btn = QPushButton("Mind Map")
        mm_btn.setStyleSheet(f"QPushButton {{ background-color: #3A5A7C; color: white; border: none; border-radius: 4px; padding: 5px 16px; font-weight: bold; font-family: 'Helvetica Neue', Arial, sans-serif; }} QPushButton:hover {{ background-color: #2D4A6A; }}")
        mm_btn.clicked.connect(self._add_mindmap)
        tl.addWidget(mm_btn)
        main_layout.addWidget(toolbar)

        # Middle: sidebar + canvas
        mid = QWidget()
        mid.setStyleSheet(f"background-color: {C_BG_MAIN};")
        mid_layout = QHBoxLayout(mid)
        mid_layout.setContentsMargins(0, 0, 0, 0)
        mid_layout.setSpacing(0)
        self.drawer = SidebarDrawer()
        self.drawer.new_btn.clicked.connect(self._create_project)
        self.drawer.del_btn.clicked.connect(self._delete_project)
        self.drawer.project_combo.currentIndexChanged.connect(self._on_project_changed)
        self.drawer.plan_input.returnPressed.connect(self._add_plan)
        self.drawer.add_plan_btn.clicked.connect(self._add_plan)
        self.drawer.plan_date_btn.clicked.connect(self._pick_plan_date)
        self.drawer.tag_list.itemClicked.connect(self._on_tag_selected)
        self.drawer.clear_tag_btn.clicked.connect(self._on_clear_tag_filter)
        self.drawer.calendar.selectionChanged.connect(self._on_calendar_date_changed)
        # Plan list signals (connected once here, not in _load_plans)
        self.drawer.plan_list.itemChanged.connect(self._on_plan_changed)
        self.drawer.plan_list.itemDoubleClicked.connect(self._on_plan_double_clicked)
        mid_layout.addWidget(self.drawer)
        self.canvas = DesktopCanvas()
        self.canvas.set_data_manager(self.data_manager)
        self.canvas.note_deleted.connect(self._on_note_deleted)
        mid_layout.addWidget(self.canvas, 1)
        main_layout.addWidget(mid, 1)

        # Bottom bar
        dev_bar = QWidget()
        dev_bar.setFixedHeight(48)
        dev_bar.setStyleSheet(f"QWidget {{ background-color: {C_BG_CARD}; border-top: 1px solid {C_BORDER}; }} QLabel {{ color: {C_TEXT_MUTED}; font-size: 12px; font-family: 'Helvetica Neue', Arial, sans-serif; }}")
        self.dev_layout = QHBoxLayout(dev_bar)
        self.dev_layout.setContentsMargins(18, 8, 18, 8)
        self.dev_layout.setSpacing(10)
        dl = QLabel("Quick Launch")
        self.dev_layout.addWidget(dl)
        main_layout.addWidget(dev_bar)

    def _load_projects(self):
        self.drawer.project_combo.clear()
        projects = self.data_manager.projects
        if not projects:
            self.data_manager.create_project("My First Project")
            projects = self.data_manager.projects
        for p in projects:
            self.drawer.project_combo.addItem(p["name"], p["id"])
        if projects:
            self._load_project(projects[0]["id"])

    def _load_project(self, proj_id):
        self.current_project_id = proj_id
        proj = next((p for p in self.data_manager.projects if p["id"] == proj_id), None)
        if proj:
            self.project_label.setText(proj["name"])
            self.project_label.setStyleSheet(f"color: {C_TEXT_PRIMARY}; font-style: normal;")
        self.canvas.load_project(proj_id)
        self._load_tools()
        self._load_plans()
        self._refresh_tag_list()
        self._highlight_plan_dates()

    def _on_project_changed(self, idx):
        if idx >= 0:
            pid = self.drawer.project_combo.itemData(idx)
            if pid:
                self._load_project(pid)

    def _create_project(self):
        name, ok = QInputDialog.getText(self, "New Project", "Project name:")
        if ok and name.strip():
            proj = self.data_manager.create_project(name.strip())
            self.drawer.project_combo.addItem(proj["name"], proj["id"])
            self.drawer.project_combo.setCurrentIndex(self.drawer.project_combo.count() - 1)

    def _delete_project(self):
        if not self.current_project_id:
            return
        reply = QMessageBox.question(self, "Delete Project", "Delete current project? All data will be lost.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.data_manager.delete_project(self.current_project_id)
            self._load_projects()

    def _add_note(self):
        if not self.current_project_id:
            QMessageBox.warning(self, "Notice", "Please select or create a project first.")
            return
        self.canvas.add_note()

    def _on_note_deleted(self, note_id):
        pass

    def _pick_plan_date(self):
        from PySide6.QtWidgets import QCalendarWidget, QDialog, QVBoxLayout
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Due Date")
        dialog.setFixedSize(320, 280)
        layout = QVBoxLayout(dialog)
        cal = QCalendarWidget()
        cal.setSelectedDate(self.drawer.get_selected_plan_date())
        layout.addWidget(cal)
        ok_btn = QPushButton("Select")
        ok_btn.clicked.connect(dialog.accept)
        layout.addWidget(ok_btn)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.drawer.plan_date = cal.selectedDate()
            self.drawer.plan_date_btn.setStyleSheet(
                f"QPushButton {{ background-color: {C_ACCENT}; color: white; border-radius: 4px; font-size: 12px; }}"
            )

    def _refresh_tag_list(self):
        self.drawer.tag_list.clear()
        tags = self.canvas.get_all_tags()
        for tag in tags:
            item = QListWidgetItem(f"  {tag}")
            item.setData(Qt.ItemDataRole.UserRole, tag)
            self.drawer.tag_list.addItem(item)

    def _on_tag_selected(self, item):
        tag = item.data(Qt.ItemDataRole.UserRole)
        if tag:
            self.canvas.filter_by_tag(tag)

    def _on_clear_tag_filter(self):
        self.canvas.clear_tag_filter()
        self.drawer.tag_list.clearSelection()

    def _on_calendar_date_changed(self):
        self._load_plans()

    def _load_tools(self):
        while self.dev_layout.count() > 1:
            item = self.dev_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()
        if not self.current_project_id:
            return
        config = self.data_manager.load_config(self.current_project_id)
        for tool in config.get("dev_tools", []):
            self.dev_layout.addWidget(DevToolButton(tool["name"], tool["command"], tool["args"]))
        self.dev_layout.addStretch()

    def _open_tool_config(self):
        if not self.current_project_id:
            return
        config = self.data_manager.load_config(self.current_project_id)
        dialog = DevToolsDialog(config.get("dev_tools", []), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            config["dev_tools"] = dialog.get_tools()
            self.data_manager.save_config(self.current_project_id, config)
            self._load_tools()

    def _load_plans(self):
        self.drawer.plan_list.clear()
        if not self.current_project_id:
            return
        config = self.data_manager.load_config(self.current_project_id)
        plans = config.get("plans", [])
        filter_date = self.drawer.get_selected_plan_date().toString("yyyy-MM-dd")
        for plan in plans:
            due = plan.get("due_date")
            # If a date is selected in calendar, filter to that date
            if self.drawer._selected_plan_date and due != filter_date:
                continue
            display = plan.get("text", "")
            if due:
                display = f"[{due}] {display}"
            item = QListWidgetItem(display)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if plan.get("done") else Qt.CheckState.Unchecked)
            # Store raw text for editing
            item.setData(Qt.ItemDataRole.UserRole, plan.get("text", ""))
            self.drawer.plan_list.addItem(item)

    def _add_plan(self):
        text = self.drawer.plan_input.text().strip()
        if not text or not self.current_project_id:
            return
        config = self.data_manager.load_config(self.current_project_id)
        plans = config.get("plans", [])
        due_date = None
        if self.drawer.plan_date:
            due_date = self.drawer.plan_date.toString("yyyy-MM-dd")
        plans.append({
            "text": text,
            "done": False,
            "created_at": datetime.now().isoformat(),
            "due_date": due_date,
        })
        config["plans"] = plans
        self.data_manager.save_config(self.current_project_id, config)
        self.drawer.plan_input.clear()
        self.drawer.plan_date = None
        self.drawer.plan_date_btn.setStyleSheet("")
        self._load_plans()
        self._highlight_plan_dates()

    def _on_plan_changed(self, item):
        """Save checkbox state when toggled."""
        if not self.current_project_id:
            return
        config = self.data_manager.load_config(self.current_project_id)
        plans = config.get("plans", [])
        idx = self.drawer.plan_list.row(item)
        if 0 <= idx < len(plans):
            plans[idx]["done"] = item.checkState() == Qt.CheckState.Checked
            self.data_manager.save_config(self.current_project_id, config)

    def _on_plan_double_clicked(self, item):
        """Double-click to delete plan."""
        if not self.current_project_id:
            return
        reply = QMessageBox.question(
            self, "Delete Plan", f'Delete plan: "{item.data(Qt.ItemDataRole.UserRole)}"?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            config = self.data_manager.load_config(self.current_project_id)
            plans = config.get("plans", [])
            idx = self.drawer.plan_list.row(item)
            if 0 <= idx < len(plans):
                del plans[idx]
                self.data_manager.save_config(self.current_project_id, config)
                self._load_plans()
                self._highlight_plan_dates()

    def _highlight_plan_dates(self):
        if not self.current_project_id:
            self.drawer.clear_calendar_highlight()
            return
        config = self.data_manager.load_config(self.current_project_id)
        plans = config.get("plans", [])
        from PySide6.QtCore import QDate
        dates = []
        for plan in plans:
            due = plan.get("due_date")
            if due:
                d = QDate.fromString(due, "yyyy-MM-dd")
                if d.isValid():
                    dates.append(d)
        self.drawer.highlight_calendar_dates(dates)

    def _auto_save(self):
        if self.canvas:
            self.canvas._save_notes()

    def _add_mindmap(self):
        if not self.current_project_id:
            QMessageBox.warning(self, "Notice", "Please select or create a project first.")
            return
        self.canvas.add_mindmap()

    def closeEvent(self, event):
        if self.canvas:
            self.canvas._save_notes()
        event.accept()
