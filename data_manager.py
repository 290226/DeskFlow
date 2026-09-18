"""Project data persistence: projects index, notes, plans, mind maps.

Layout (created at runtime):

    data/
      projects.json            index of every project
      settings.json            window geometry and UI preferences
      .trash/                  deleted projects, kept for recovery
      projects/<proj_id>/
        notes.json
        config.json            dev tools + plans + project folder
        mindmaps.json

The data root defaults to `<DeskFlow>/data` so the app stays portable; if that
folder is not writable (e.g. installed under Program Files) it falls back to
`%APPDATA%/DeskFlow/data`.
"""

import os
import platform
import shutil
from datetime import datetime
from pathlib import Path

from config import APP_VERSION, PRIORITY_ORDER
from storage import read_json, write_json
from util import new_id, normalize_plan, normalize_plans, now_iso, safe_filename


def _probe_writable(path):
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def resolve_data_root():
    """Pick a writable location for the data directory."""
    local = Path(__file__).resolve().parent / "data"
    if _probe_writable(local):
        return local
    bases = [
        os.environ.get("APPDATA"),
        os.environ.get("LOCALAPPDATA"),
        os.path.expanduser("~"),
    ]
    for base in bases:
        if not base:
            continue
        candidate = Path(base) / "DeskFlow" / "data"
        if _probe_writable(candidate):
            return candidate
    return local


DEFAULT_DATA_ROOT = resolve_data_root()

DEFAULT_SETTINGS = {
    "geometry": None,
    "grid_visible": True,
    "last_project": None,
    "zoom": 1.0,
}


class DataManager:
    """Reads and writes every persisted artefact of the application."""

    def __init__(self, data_root=None):
        self.data_root = Path(data_root) if data_root else DEFAULT_DATA_ROOT
        self.projects_dir = self.data_root / "projects"
        self.trash_dir = self.data_root / ".trash"
        self.projects_file = self.data_root / "projects.json"
        self.settings_file = self.data_root / "settings.json"
        try:
            self.data_root.mkdir(parents=True, exist_ok=True)
            self.projects_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        self.projects = self._load_projects()

    # ------------------------------------------------------------------ index
    def _load_projects(self):
        raw = read_json(self.projects_file, {"projects": []})
        if isinstance(raw, dict):
            items = raw.get("projects", [])
        elif isinstance(raw, list):
            items = raw
        else:
            items = []
        projects = []
        for item in items:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            projects.append(
                {
                    "id": str(item["id"]),
                    "name": str(item.get("name") or "Untitled"),
                    "created_at": item.get("created_at") or now_iso(),
                    "updated_at": item.get("updated_at") or item.get("created_at") or now_iso(),
                    "path": item.get("path") or "",
                }
            )
        return projects

    def _save_projects(self):
        return write_json(self.projects_file, {"projects": self.projects})

    def get_project(self, proj_id):
        return next((p for p in self.projects if p["id"] == proj_id), None)

    def get_project_dir(self, proj_id):
        return self.projects_dir / proj_id

    def touch_project(self, proj_id):
        project = self.get_project(proj_id)
        if project:
            project["updated_at"] = now_iso()
            self._save_projects()

    def create_project(self, name, path=""):
        proj_id = new_id("proj")
        while self.get_project(proj_id):
            proj_id = new_id("proj")
        project = {
            "id": proj_id,
            "name": str(name or "Untitled").strip() or "Untitled",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "path": path or "",
        }
        self.projects.append(project)
        self._save_projects()
        self.ensure_project(proj_id)
        return project

    def rename_project(self, proj_id, name):
        project = self.get_project(proj_id)
        if not project:
            return False
        clean = str(name or "").strip()
        if not clean:
            return False
        project["name"] = clean
        project["updated_at"] = now_iso()
        self._save_projects()
        return True

    def set_project_path(self, proj_id, path):
        project = self.get_project(proj_id)
        if not project:
            return False
        project["path"] = path or ""
        project["updated_at"] = now_iso()
        self._save_projects()
        config = self.load_config(proj_id)
        config["project_path"] = path or ""
        self.save_config(proj_id, config)
        return True

    def delete_project(self, proj_id, keep_copy=True):
        """Remove a project. Its folder is moved to .trash when possible."""
        self.projects = [p for p in self.projects if p["id"] != proj_id]
        self._save_projects()
        folder = self.get_project_dir(proj_id)
        if not folder.exists():
            return True
        if keep_copy:
            try:
                self.trash_dir.mkdir(parents=True, exist_ok=True)
                target = self.trash_dir / "{}_{}".format(
                    proj_id, datetime.now().strftime("%Y%m%d%H%M%S")
                )
                shutil.move(str(folder), str(target))
                self._prune_trash()
                return True
            except (OSError, shutil.Error):
                pass
        shutil.rmtree(folder, ignore_errors=True)
        return True

    # ------------------------------------------------------------------ trash
    def list_trash(self):
        """Restorable projects, newest first: {trash, proj_id, deleted_at}."""
        entries = []
        if not self.trash_dir.exists():
            return entries
        for path in self.trash_dir.iterdir():
            if not path.is_dir():
                continue
            proj_id, _, stamp = path.name.rpartition("_")
            if not proj_id:
                proj_id, stamp = path.name, ""
            try:
                deleted_at = datetime.strptime(stamp, "%Y%m%d%H%M%S").strftime(
                    "%Y-%m-%d %H:%M"
                )
            except ValueError:
                deleted_at = stamp or "unknown"
            entries.append(
                {"trash": path.name, "proj_id": proj_id, "deleted_at": deleted_at}
            )
        entries.sort(key=lambda item: item["deleted_at"], reverse=True)
        return entries

    def restore_project(self, trash_name):
        """Move a trashed project folder back into place and register it again."""
        src = self.trash_dir / trash_name
        if not src.is_dir():
            return None
        base = trash_name.rpartition("_")[0] or trash_name
        proj_id = base
        while self.get_project(proj_id) or self.get_project_dir(proj_id).exists():
            proj_id = "{}_{}".format(base, new_id("r"))
        target = self.get_project_dir(proj_id)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(target))
        except (OSError, shutil.Error):
            return None
        self.projects.append(
            {
                "id": proj_id,
                "name": "Restored {}".format(proj_id),
                "created_at": now_iso(),
                "updated_at": now_iso(),
                "path": "",
            }
        )
        self._save_projects()
        return proj_id

    def _prune_trash(self, keep=10):
        try:
            entries = sorted(
                [p for p in self.trash_dir.iterdir() if p.is_dir()],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return
        for stale in entries[keep:]:
            shutil.rmtree(stale, ignore_errors=True)

    # ------------------------------------------------------------- bootstrap
    def ensure_project(self, proj_id):
        folder = self.get_project_dir(proj_id)
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            return folder
        defaults = (
            ("notes.json", {"notes": []}),
            ("mindmaps.json", {"nodes": []}),
            (
                "config.json",
                {
                    "dev_tools": self.default_dev_tools(),
                    "plans": [],
                    "project_path": "",
                },
            ),
        )
        for filename, payload in defaults:
            target = folder / filename
            if not target.exists():
                write_json(target, payload, backup=False)
        return folder

    # ----------------------------------------------------------------- notes
    def load_notes(self, proj_id):
        self.ensure_project(proj_id)
        raw = read_json(self.get_project_dir(proj_id) / "notes.json", {"notes": []})
        notes = raw.get("notes", []) if isinstance(raw, dict) else []
        if not isinstance(notes, list):
            return []
        return [n for n in notes if isinstance(n, dict) and n.get("id")]

    def save_notes(self, proj_id, notes):
        self.ensure_project(proj_id)
        return write_json(
            self.get_project_dir(proj_id) / "notes.json", {"notes": list(notes)}
        )

    # -------------------------------------------------------------- mindmaps
    def load_mindmaps(self, proj_id):
        self.ensure_project(proj_id)
        raw = read_json(self.get_project_dir(proj_id) / "mindmaps.json", {"nodes": []})
        nodes = raw.get("nodes", []) if isinstance(raw, dict) else []
        if not isinstance(nodes, list):
            return {"nodes": []}
        return {"nodes": [n for n in nodes if isinstance(n, dict) and n.get("id")]}

    def save_mindmaps(self, proj_id, data):
        self.ensure_project(proj_id)
        payload = data if isinstance(data, dict) else {"nodes": []}
        payload.setdefault("nodes", [])
        return write_json(self.get_project_dir(proj_id) / "mindmaps.json", payload)

    # ---------------------------------------------------------------- config
    def load_config(self, proj_id):
        self.ensure_project(proj_id)
        raw = read_json(self.get_project_dir(proj_id) / "config.json", {})
        config = raw if isinstance(raw, dict) else {}
        config.setdefault("dev_tools", self.default_dev_tools())
        config.setdefault("plans", [])
        config.setdefault("project_path", "")
        return config

    def save_config(self, proj_id, config):
        self.ensure_project(proj_id)
        payload = dict(config or {})
        payload["plans"] = normalize_plans(payload.get("plans", []))
        return write_json(self.get_project_dir(proj_id) / "config.json", payload)

    def default_dev_tools(self):
        system = platform.system()
        if system == "Windows":
            return [
                {"name": "PyCharm", "command": "pycharm64.exe", "args": ["."]},
                {"name": "VSCode", "command": "code", "args": ["."]},
                {"name": "Terminal", "command": "cmd", "args": ["/k", "cd", "/d", "."]},
                {"name": "Files", "command": "explorer", "args": ["."]},
            ]
        if system == "Darwin":
            return [
                {"name": "PyCharm", "command": "open", "args": ["-a", "PyCharm", "."]},
                {"name": "VSCode", "command": "code", "args": ["."]},
                {"name": "Terminal", "command": "open", "args": ["-a", "Terminal", "."]},
                {"name": "Finder", "command": "open", "args": ["."]},
            ]
        return [
            {"name": "PyCharm", "command": "pycharm", "args": ["."]},
            {"name": "VSCode", "command": "code", "args": ["."]},
            {"name": "Terminal", "command": "gnome-terminal", "args": ["--working-directory=."]},
            {"name": "Files", "command": "xdg-open", "args": ["."]},
        ]

    # ----------------------------------------------------------------- plans
    def get_plans(self, proj_id):
        config = self.load_config(proj_id)
        return normalize_plans(config.get("plans", []))

    def save_plans(self, proj_id, plans):
        config = self.load_config(proj_id)
        config["plans"] = normalize_plans(plans)
        return self.save_config(proj_id, config)

    def add_plan(self, proj_id, text, due_date=None, priority="normal"):
        plan = normalize_plan(
            {
                "text": text,
                "due_date": due_date,
                "priority": priority,
                "created_at": now_iso(),
            }
        )
        if not plan:
            return None
        plans = self.get_plans(proj_id)
        plans.append(plan)
        self.save_plans(proj_id, plans)
        self.touch_project(proj_id)
        return plan

    def update_plan(self, proj_id, plan_id, **changes):
        plans = self.get_plans(proj_id)
        updated = None
        for plan in plans:
            if plan["id"] != plan_id:
                continue
            if "text" in changes and changes["text"] is not None:
                text = str(changes["text"]).strip()
                if text:
                    plan["text"] = text
            if "done" in changes and changes["done"] is not None:
                plan["done"] = bool(changes["done"])
                plan["done_at"] = now_iso() if plan["done"] else None
            if "due_date" in changes:
                plan["due_date"] = changes["due_date"]
            if "priority" in changes:
                priority = str(changes["priority"] or "normal").lower()
                plan["priority"] = priority if priority in PRIORITY_ORDER else "normal"
            updated = plan
            break
        if updated is not None:
            self.save_plans(proj_id, plans)
            self.touch_project(proj_id)
        return updated

    def delete_plan(self, proj_id, plan_id):
        plans = self.get_plans(proj_id)
        remaining = [p for p in plans if p["id"] != plan_id]
        if len(remaining) == len(plans):
            return False
        self.save_plans(proj_id, remaining)
        self.touch_project(proj_id)
        return True

    def clear_completed_plans(self, proj_id):
        plans = self.get_plans(proj_id)
        remaining = [p for p in plans if not p["done"]]
        removed = len(plans) - len(remaining)
        if removed:
            self.save_plans(proj_id, remaining)
            self.touch_project(proj_id)
        return removed

    # -------------------------------------------------------------- settings
    def load_settings(self):
        raw = read_json(self.settings_file, dict(DEFAULT_SETTINGS))
        settings = dict(DEFAULT_SETTINGS)
        if isinstance(raw, dict):
            settings.update({k: v for k, v in raw.items() if k in DEFAULT_SETTINGS})
        return settings

    def save_settings(self, settings):
        merged = dict(DEFAULT_SETTINGS)
        if isinstance(settings, dict):
            merged.update({k: v for k, v in settings.items() if k in DEFAULT_SETTINGS})
        return write_json(self.settings_file, merged)

    # ---------------------------------------------------------------- export
    def project_bundle(self, proj_id):
        project = self.get_project(proj_id) or {"id": proj_id, "name": "Untitled"}
        return {
            "app": "DeskFlow",
            "app_version": APP_VERSION,
            "exported_at": now_iso(),
            "project": project,
            "notes": self.load_notes(proj_id),
            "plans": self.get_plans(proj_id),
            "mindmaps": self.load_mindmaps(proj_id),
            "config": self.load_config(proj_id),
        }

    def export_json(self, proj_id, out_path):
        return write_json(out_path, self.project_bundle(proj_id), backup=False)

    def export_markdown(self, proj_id, out_path):
        project = self.get_project(proj_id) or {"name": "Untitled"}
        notes = self.load_notes(proj_id)
        plans = self.get_plans(proj_id)
        nodes = self.load_mindmaps(proj_id).get("nodes", [])

        lines = [
            "# {}".format(project.get("name", "Untitled")),
            "",
            "> Exported from DeskFlow {} on {}".format(APP_VERSION, now_iso()),
            "",
            "## Summary",
            "",
            "- Sticky notes: {}".format(len(notes)),
            "- Plans: {} ({} done)".format(len(plans), sum(1 for p in plans if p["done"])),
            "- Mind map nodes: {}".format(len(nodes)),
            "",
            "## Plans",
            "",
        ]
        if plans:
            for plan in sorted(plans, key=lambda p: (p["done"], p.get("due_date") or "~")):
                box = "x" if plan["done"] else " "
                due = " (due {})".format(plan["due_date"]) if plan.get("due_date") else ""
                prio = "" if plan["priority"] == "normal" else " [{}]".format(plan["priority"])
                lines.append("- [{}] {}{}{}".format(box, plan["text"], due, prio))
        else:
            lines.append("_No plans._")
        lines += ["", "## Sticky notes", ""]
        if notes:
            for note in sorted(notes, key=lambda n: (n.get("y", 0), n.get("x", 0))):
                tags = note.get("tags") or []
                header = "- **{}**".format(safe_filename(note.get("id", "note")))
                if tags:
                    header += " _[{}]_".format(", ".join(tags))
                lines.append(header)
                content = str(note.get("content", "")).strip()
                if content:
                    for row in content.splitlines():
                        lines.append("  > {}".format(row))
                else:
                    lines.append("  > _(empty)_")
        else:
            lines.append("_No notes._")

        lines += ["", "## Mind map", ""]
        if nodes:
            lines.extend(self._mindmap_lines(nodes))
        else:
            lines.append("_No mind map nodes._")
        lines.append("")

        try:
            with open(out_path, "w", encoding="utf-8") as handle:
                handle.write("\n".join(lines))
            return True
        except OSError:
            return False

    def _mindmap_lines(self, nodes):
        by_parent = {}
        for node in nodes:
            by_parent.setdefault(node.get("parent_id"), []).append(node)
        lines = []

        def walk(parent_id, depth):
            for node in by_parent.get(parent_id, []):
                text = str(node.get("text", "")).replace("\n", " ").strip() or "(empty)"
                lines.append("{}- {}".format("  " * depth, text))
                walk(node.get("id"), depth + 1)

        roots = by_parent.get(None, [])
        for root in roots:
            text = str(root.get("text", "")).replace("\n", " ").strip() or "(empty)"
            lines.append("- **{}**".format(text))
            walk(root.get("id"), 1)
        if not roots:
            for node in nodes:
                lines.append("- {}".format(node.get("text", "")))
        return lines
