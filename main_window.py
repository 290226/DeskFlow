"""Main window: sidebar + canvas, menus, shortcuts and persistence wiring."""

from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTextEdit,
    QToolBar,
    QWidget,
)

from canvas import DesktopCanvas
from config import APP_NAME, APP_TAGLINE, APP_VERSION, AUTOSAVE_INTERVAL_MS, C_TEXT_MUTED
from editor import NoteEditorDialog
from sidebar import Sidebar
from util import safe_filename


class MainWindow(QMainWindow):
    def __init__(self, data_manager):
        super().__init__()
        self.data_manager = data_manager
        self.current_proj_id = None
        self.plans = []
        self._active_tag = ""
        self._last_search = ""
        self._search_hits = []
        self._search_index = -1

        self.setWindowTitle(APP_NAME)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # the drawer is docked to the window's far right edge
        self.sidebar = Sidebar()
        self.canvas = DesktopCanvas(data_manager)
        layout.addWidget(self.canvas, 1)
        layout.addWidget(self.sidebar)
        self.setCentralWidget(central)

        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_statusbar()
        self._connect_signals()
        self._restore_settings()

        self._autosave = QTimer(self)
        self._autosave.setInterval(AUTOSAVE_INTERVAL_MS)
        self._autosave.timeout.connect(self.save_all)
        self._autosave.start()

        self.bootstrap()

    # ==================================================================
    # construction
    # ==================================================================
    def _build_actions(self):
        self.act_new_note = QAction("New note", self)
        self.act_new_note.setShortcut(QKeySequence("Ctrl+N"))
        self.act_new_note.triggered.connect(self.new_note)

        self.act_new_node = QAction("New mind map node", self)
        self.act_new_node.setShortcut(QKeySequence("Ctrl+M"))
        self.act_new_node.triggered.connect(self.new_mind_map)

        self.act_edit_note = QAction("Edit selected note…", self)
        self.act_edit_note.setShortcut(QKeySequence("Ctrl+E"))
        self.act_edit_note.triggered.connect(self.edit_selected_note)

        self.act_duplicate = QAction("Duplicate selected note", self)
        self.act_duplicate.setShortcut(QKeySequence("Ctrl+D"))
        self.act_duplicate.triggered.connect(self.duplicate_selected_note)

        self.act_delete = QAction("Delete selection", self)
        self.act_delete.triggered.connect(self.canvas.delete_selection)

        self.act_delete_map = QAction("Delete entire mind map…", self)
        self.act_delete_map.triggered.connect(self.canvas.delete_all_mindmaps)

        self.act_undo_delete = QAction("Undo last delete", self)
        self.act_undo_delete.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        self.act_undo_delete.triggered.connect(self.canvas.undo)

        self.act_find = QAction("Find…", self)
        self.act_find.setShortcut(QKeySequence("Ctrl+F"))
        self.act_find.triggered.connect(self.find_next)

        self.act_save = QAction("Save now", self)
        self.act_save.setShortcut(QKeySequence("Ctrl+S"))
        self.act_save.triggered.connect(self.save_all)

        self.act_new_project = QAction("New project…", self)
        self.act_new_project.setShortcut(QKeySequence("Ctrl+Shift+N"))
        self.act_new_project.triggered.connect(self.create_project)

        self.act_rename_project = QAction("Rename project…", self)
        self.act_rename_project.setShortcut(QKeySequence("F2"))
        self.act_rename_project.triggered.connect(self.rename_project)

        self.act_delete_project = QAction("Delete project…", self)
        self.act_delete_project.triggered.connect(self.delete_project)

        self.act_restore_project = QAction("Restore deleted project…", self)
        self.act_restore_project.triggered.connect(self.restore_project)

        self.act_export_json = QAction("Export as JSON…", self)
        self.act_export_json.triggered.connect(lambda: self.export_project("json"))

        self.act_export_md = QAction("Export as Markdown…", self)
        self.act_export_md.setShortcut(QKeySequence("Ctrl+Shift+E"))
        self.act_export_md.triggered.connect(lambda: self.export_project("markdown"))

        self.act_quit = QAction("Quit", self)
        self.act_quit.setShortcut(QKeySequence("Ctrl+Q"))
        self.act_quit.triggered.connect(self.close)

        self.act_toggle_sidebar = QAction("Show sidebar", self)
        self.act_toggle_sidebar.setShortcut(QKeySequence("Ctrl+B"))
        self.act_toggle_sidebar.setCheckable(True)
        self.act_toggle_sidebar.setChecked(False)
        self.act_toggle_sidebar.toggled.connect(
            lambda on: self.sidebar.expand() if on else self.sidebar.collapse()
        )

        self.act_grid = QAction("Show grid", self)
        self.act_grid.setCheckable(True)
        self.act_grid.setChecked(True)
        self.act_grid.toggled.connect(self.canvas.set_grid_visible)

        self.act_zoom_in = QAction("Zoom in", self)
        self.act_zoom_in.setShortcut(QKeySequence("Ctrl+="))
        self.act_zoom_in.triggered.connect(self.canvas.zoom_in)

        self.act_zoom_out = QAction("Zoom out", self)
        self.act_zoom_out.setShortcut(QKeySequence("Ctrl+-"))
        self.act_zoom_out.triggered.connect(self.canvas.zoom_out)

        self.act_zoom_reset = QAction("Reset zoom", self)
        self.act_zoom_reset.setShortcut(QKeySequence("Ctrl+0"))
        self.act_zoom_reset.triggered.connect(self.canvas.reset_zoom)

        self.act_fit = QAction("Fit to content", self)
        self.act_fit.triggered.connect(self.canvas.fit_all)

        self.act_arrange = QAction("Arrange notes", self)
        self.act_arrange.triggered.connect(self.canvas.arrange_notes)

        self.act_clear_filter = QAction("Clear tag filter", self)
        self.act_clear_filter.triggered.connect(lambda: self.apply_tag_filter(""))

        self.act_shortcuts = QAction("Keyboard shortcuts", self)
        self.act_shortcuts.triggered.connect(self.show_shortcuts)

        self.act_about = QAction("About {}".format(APP_NAME), self)
        self.act_about.triggered.connect(self.show_about)

        self.act_data_folder = QAction("Open data folder", self)
        self.act_data_folder.triggered.connect(self.open_data_folder)

    def _build_menus(self):
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.act_new_project)
        file_menu.addAction(self.act_rename_project)
        file_menu.addAction(self.act_delete_project)
        file_menu.addAction(self.act_restore_project)
        file_menu.addSeparator()
        file_menu.addAction(self.act_export_json)
        file_menu.addAction(self.act_export_md)
        file_menu.addSeparator()
        file_menu.addAction(self.act_save)
        file_menu.addSeparator()
        file_menu.addAction(self.act_quit)

        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addAction(self.act_new_note)
        edit_menu.addAction(self.act_new_node)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_edit_note)
        edit_menu.addAction(self.act_duplicate)
        edit_menu.addAction(self.act_delete)
        edit_menu.addAction(self.act_delete_map)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_undo_delete)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_find)
        edit_menu.addAction(self.act_clear_filter)

        view_menu = self.menuBar().addMenu("&View")
        view_menu.addAction(self.act_toggle_sidebar)
        view_menu.addAction(self.act_grid)
        view_menu.addSeparator()
        view_menu.addAction(self.act_zoom_in)
        view_menu.addAction(self.act_zoom_out)
        view_menu.addAction(self.act_zoom_reset)
        view_menu.addAction(self.act_fit)
        view_menu.addSeparator()
        view_menu.addAction(self.act_arrange)

        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction(self.act_shortcuts)
        help_menu.addAction(self.act_data_folder)
        help_menu.addSeparator()
        help_menu.addAction(self.act_about)

    def _build_toolbar(self):
        toolbar = QToolBar("Main", self)
        toolbar.setMovable(False)
        toolbar.setStyleSheet("QToolBar { spacing: 6px; padding: 4px; }")
        self.addToolBar(toolbar)
        for action in (
            self.act_new_note,
            self.act_new_node,
            self.act_edit_note,
            self.act_find,
            self.act_arrange,
            self.act_fit,
            self.act_grid,
            self.act_export_md,
        ):
            toolbar.addAction(action)

    def _build_statusbar(self):
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: {}; font-size: 11px;".format(C_TEXT_MUTED))
        self.statusBar().addPermanentWidget(self.stats_label)
        self.statusBar().showMessage(
            "Move the mouse to the far-right edge to open the sidebar · Ctrl+N for a new note"
        )

    def _connect_signals(self):
        self.canvas.content_changed.connect(self._on_canvas_changed)
        self.canvas.status_message.connect(lambda msg: self.statusBar().showMessage(msg, 3000))

        self.sidebar.project_selected.connect(self.open_project)
        self.sidebar.project_create_requested.connect(self.create_project)
        self.sidebar.project_rename_requested.connect(self.rename_project)
        self.sidebar.project_delete_requested.connect(self.delete_project)
        self.sidebar.project_export_requested.connect(lambda: self.export_project("json"))

        self.sidebar.plan_add_requested.connect(self.add_plan)
        self.sidebar.plan_toggle_requested.connect(self.toggle_plan)
        self.sidebar.plan_text_changed.connect(self.update_plan_text)
        self.sidebar.plan_date_changed.connect(self.update_plan_date)
        self.sidebar.plan_priority_changed.connect(self.update_plan_priority)
        self.sidebar.plan_delete_requested.connect(self.delete_plan)
        self.sidebar.plan_clear_done_requested.connect(self.clear_completed_plans)
        self.sidebar.tag_filter_changed.connect(self.apply_tag_filter)

    # ==================================================================
    # bootstrap / projects
    # ==================================================================
    def bootstrap(self):
        settings = self.data_manager.load_settings()
        projects = list(self.data_manager.projects)
        if not projects:
            project = self.data_manager.create_project("My First Project")
            projects = [project]
        target = None
        last = settings.get("last_project")
        if last:
            target = next((p for p in projects if p["id"] == last), None)
        if target is None:
            target = projects[0]
        self.open_project(target["id"])

    def reload_projects(self, select_id=None):
        self.sidebar.set_projects(self.data_manager.projects, select_id or self.current_proj_id)

    def open_project(self, proj_id):
        if not proj_id:
            return
        project = self.data_manager.get_project(proj_id)
        if project is None:
            return
        self.save_all()
        self.current_proj_id = proj_id
        self._active_tag = ""
        self.canvas.load_project(proj_id)
        self.plans = self.data_manager.get_plans(proj_id)
        self.reload_projects(proj_id)
        self.sidebar.set_plans(self.plans)
        self.refresh_tags()
        self.update_title()
        self.update_stats()

        settings = self.data_manager.load_settings()
        settings["last_project"] = proj_id
        self.data_manager.save_settings(settings)
        self.statusBar().showMessage("Opened “{}”".format(project["name"]), 3000)

    def create_project(self):
        name, ok = QInputDialog.getText(self, "New Project", "Project name:")
        if not ok or not name.strip():
            return
        project = self.data_manager.create_project(name.strip())
        self.reload_projects(project["id"])
        self.open_project(project["id"])

    def rename_project(self):
        project = self.data_manager.get_project(self.current_proj_id)
        if not project:
            return
        name, ok = QInputDialog.getText(
            self, "Rename Project", "Project name:", text=project["name"]
        )
        if not ok or not name.strip():
            return
        if self.data_manager.rename_project(self.current_proj_id, name.strip()):
            self.reload_projects()
            self.update_title()
            self.statusBar().showMessage("Project renamed", 3000)

    def restore_project(self):
        entries = self.data_manager.list_trash()
        if not entries:
            QMessageBox.information(
                self, "Restore Project", "Nothing to restore - the .trash folder is empty."
            )
            return
        labels = [
            "{}   (deleted {})".format(item["proj_id"], item["deleted_at"])
            for item in entries
        ]
        choice, ok = QInputDialog.getItem(
            self, "Restore Project", "Deleted project:", labels, 0, False
        )
        if not ok or not choice:
            return
        proj_id = self.data_manager.restore_project(entries[labels.index(choice)]["trash"])
        if not proj_id:
            QMessageBox.warning(
                self, "Restore Project", "That project folder could not be restored."
            )
            return
        self.reload_projects(proj_id)
        self.open_project(proj_id)
        self.statusBar().showMessage("Project restored", 3000)

    def delete_project(self):
        project = self.data_manager.get_project(self.current_proj_id)
        if not project:
            return
        reply = QMessageBox.question(
            self,
            "Delete Project",
            "Delete “{}”?\n\nThe project folder is moved to the app's .trash folder "
            "(last 10 are kept), so it can be restored from File ▸ Restore deleted project.".format(project["name"]),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.data_manager.delete_project(self.current_proj_id)
        remaining = list(self.data_manager.projects)
        if not remaining:
            remaining = [self.data_manager.create_project("My First Project")]
        self.open_project(remaining[0]["id"])
        self.statusBar().showMessage("Project deleted", 3000)

    def export_project(self, kind):
        project = self.data_manager.get_project(self.current_proj_id)
        if not project:
            return
        self.save_all()
        if kind == "markdown":
            extension, file_filter = ".md", "Markdown (*.md)"
        else:
            extension, file_filter = ".json", "JSON (*.json)"
        default_dir = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DesktopLocation
        ) or str(Path.home())
        default_path = str(Path(default_dir) / (safe_filename(project["name"]) + extension))
        out_path, _ = QFileDialog.getSaveFileName(self, "Export project", default_path, file_filter)
        if not out_path:
            return
        if kind == "markdown":
            ok = self.data_manager.export_markdown(self.current_proj_id, out_path)
        else:
            ok = self.data_manager.export_json(self.current_proj_id, out_path)
        if ok:
            QMessageBox.information(self, "Export complete", "Saved to:\n{}".format(out_path))
            self.statusBar().showMessage("Exported to {}".format(out_path), 5000)
        else:
            QMessageBox.warning(self, "Export failed", "Could not write:\n{}".format(out_path))

    # ==================================================================
    # notes / mind map
    # ==================================================================
    def new_note(self):
        note = self.canvas.add_note()
        if note is not None:
            self.update_stats()
            self.statusBar().showMessage("Note added · drag its bottom-right corner to resize", 3000)

    def new_mind_map(self):
        node = self.canvas.add_mind_map()
        if node is not None:
            self.update_stats()
            self.statusBar().showMessage("Mind map node added · hover it to reveal the dashed + slots", 3000)

    def selected_notes(self):
        return [item for item in self.canvas.scene.selectedItems() if hasattr(item, "note_id")]

    def edit_selected_note(self):
        notes = self.selected_notes()
        if not notes:
            self.statusBar().showMessage("Select a note first", 3000)
            return
        note = notes[0]
        dialog = NoteEditorDialog(note.to_dict(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.payload()
            note.set_content(data["content"], silent=True)
            note.set_tags(data["tags"])
            note.set_color(data["color"])
            note.set_font_size(data["font_size"])
            self.canvas.save_notes()
            self.refresh_tags()
            self.update_stats()

    def duplicate_selected_note(self):
        notes = self.selected_notes()
        if not notes:
            self.statusBar().showMessage("Select a note first", 3000)
            return
        self.canvas.duplicate_note(notes[0].note_id)
        self.update_stats()

    # ==================================================================
    # plans
    # ==================================================================
    def reload_plans(self):
        if not self.current_proj_id:
            return
        self.plans = self.data_manager.get_plans(self.current_proj_id)
        self.sidebar.set_plans(self.plans)
        self.update_stats()

    def add_plan(self, text):
        if not self.current_proj_id:
            return
        due = self.sidebar.selected_plan_date()
        self.data_manager.add_plan(self.current_proj_id, text, due_date=due)
        self.reload_plans()

    def toggle_plan(self, plan_id, done):
        self.data_manager.update_plan(self.current_proj_id, plan_id, done=done)
        self.reload_plans()

    def update_plan_text(self, plan_id, text):
        self.data_manager.update_plan(self.current_proj_id, plan_id, text=text)
        self.reload_plans()

    def update_plan_date(self, plan_id, due_date):
        self.data_manager.update_plan(self.current_proj_id, plan_id, due_date=due_date)
        self.reload_plans()

    def update_plan_priority(self, plan_id, priority):
        self.data_manager.update_plan(self.current_proj_id, plan_id, priority=priority)
        self.reload_plans()

    def delete_plan(self, plan_id):
        self.data_manager.delete_plan(self.current_proj_id, plan_id)
        self.reload_plans()

    def clear_completed_plans(self):
        reply = QMessageBox.question(
            self,
            "Clear completed",
            "Remove every completed task from this project?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        removed = self.data_manager.clear_completed_plans(self.current_proj_id)
        self.reload_plans()
        self.statusBar().showMessage("Removed {} completed task(s)".format(removed), 3000)

    # ==================================================================
    # tags / search
    # ==================================================================
    def refresh_tags(self):
        counts = {}
        for note in self.canvas.notes.values():
            for tag in note.get_tags():
                counts[tag] = counts.get(tag, 0) + 1
        self.sidebar.set_tags(sorted(counts.items()), self._active_tag)

    def apply_tag_filter(self, tag):
        tag = (tag or "").strip().lower()
        if tag and tag == self._active_tag:
            tag = ""
        self._active_tag = tag
        self.canvas.filter_by_tag(tag)
        self.refresh_tags()
        self.statusBar().showMessage(
            "Filtering notes by #{}".format(tag) if tag else "Tag filter cleared", 3000
        )

    def _collect_search_hits(self, keyword):
        low = keyword.lower()
        hits = []
        for note in self.canvas.notes.values():
            content = note.get_content()
            if low in content.lower() or any(low in tag for tag in note.get_tags()):
                hits.append(("note", note.note_id, content))
        if self.canvas.mind_map_manager is not None:
            for node in self.canvas.mind_map_manager.all_nodes():
                if low in node.get_text().lower():
                    hits.append(("node", node.node_id, node.get_text()))
        return hits

    def find_next(self):
        keyword, ok = QInputDialog.getText(
            self, "Find", "Search notes and mind map:", text=self._last_search
        )
        if not ok:
            return
        keyword = keyword.strip()
        if not keyword:
            return
        if keyword != self._last_search:
            self._last_search = keyword
            self._search_hits = self._collect_search_hits(keyword)
            self._search_index = -1
        if not self._search_hits:
            QMessageBox.information(self, "Find", "No match for “{}”.".format(keyword))
            return
        self._search_index = (self._search_index + 1) % len(self._search_hits)
        kind, item_id, snippet = self._search_hits[self._search_index]
        if kind == "note":
            self.canvas.focus_note(item_id)
        else:
            self.canvas.focus_node(item_id)
        self.statusBar().showMessage(
            "Match {}/{} · {}".format(
                self._search_index + 1, len(self._search_hits), snippet.strip().splitlines()[0][:60]
            ),
            5000,
        )

    # ==================================================================
    # housekeeping
    # ==================================================================
    def _on_canvas_changed(self):
        self.update_stats()
        self.refresh_tags()

    def update_title(self):
        project = self.data_manager.get_project(self.current_proj_id)
        name = project["name"] if project else "No project"
        self.setWindowTitle("{} — {}".format(APP_NAME, name))

    def update_stats(self):
        stats = self.canvas.stats()
        pending = sum(1 for plan in self.plans if not plan["done"])
        self.stats_label.setText(
            "Notes {} · Nodes {} · Tags {} · Open tasks {}".format(
                stats["notes"], stats["nodes"], stats["tags"], pending
            )
        )

    def save_all(self):
        if self.current_proj_id:
            self.canvas.flush()
            self.canvas.save_notes(silent=True)
            self.canvas.save_mindmaps()
        self._save_settings()

    def _save_settings(self):
        settings = self.data_manager.load_settings()
        settings["geometry"] = bytes(self.saveGeometry().toBase64()).decode("ascii")
        settings["grid_visible"] = bool(self.act_grid.isChecked())
        settings["zoom"] = self.canvas.zoom_factor()
        settings["last_project"] = self.current_proj_id
        self.data_manager.save_settings(settings)

    def _restore_settings(self):
        settings = self.data_manager.load_settings()
        geometry = settings.get("geometry")
        if geometry:
            try:
                from PySide6.QtCore import QByteArray

                self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii")))
            except (TypeError, ValueError):
                pass
        else:
            self.resize(1180, 760)
        grid = settings.get("grid_visible", True)
        self.act_grid.setChecked(bool(grid))
        self.canvas.set_grid_visible(bool(grid))

    def show_shortcuts(self):
        QMessageBox.information(
            self,
            "Keyboard shortcuts",
            "Ctrl+N          new note\n"
            "Ctrl+M          new mind map node\n"
            "Ctrl+E          edit selected note\n"
            "Ctrl+D          duplicate selected note\n"
            "Ctrl+F          find in notes and mind map\n"
            "Ctrl+Shift+Z    undo last delete\n"
            "Ctrl+B          show / hide sidebar (far-right drawer)\n"
            "Hover node      reveal dashed + slots, click one to add a child\n"
            "Ctrl+wheel      zoom in / out\n"
            "Ctrl+0          reset zoom\n"
            "Ctrl+S          save now\n"
            "Ctrl+Shift+E    export as Markdown\n"
            "Middle-drag / Space+drag   pan the canvas\n"
            "Delete          delete selection (asks first)",
        )

    def show_about(self):
        QMessageBox.about(
            self,
            "About {}".format(APP_NAME),
            "<b>{} {}</b><br>{}<br><br>"
            "A quiet desktop board for sticky notes, mind maps and tasks.<br>"
            "Data lives in:<br><code>{}</code>".format(
                APP_NAME, APP_VERSION, APP_TAGLINE, self.data_manager.data_root
            ),
        )

    def open_data_folder(self):
        root = Path(self.data_manager.data_root)
        root.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(root)))
        self.statusBar().showMessage("Data folder: {}".format(root), 5000)

    def closeEvent(self, event):
        self._autosave.stop()
        self.save_all()
        mind_map = getattr(self.canvas, "mind_map_manager", None)
        if mind_map is not None:
            mind_map.shutdown()
        super().closeEvent(event)


def launch(argv=None):
    app = QApplication(argv or [])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    from data_manager import DataManager

    window = MainWindow(DataManager())
    window.show()
    return app.exec()
