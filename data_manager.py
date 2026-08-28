"""Project data persistence."""

import json
import shutil
import platform
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
PROJECTS_FILE = DATA_DIR / "projects.json"


class DataManager:
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.projects = self._load_projects()

    def _load_projects(self):
        if PROJECTS_FILE.exists():
            with open(PROJECTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("projects", [])
        return []

    def _save_projects(self):
        with open(PROJECTS_FILE, "w", encoding="utf-8") as f:
            json.dump({"projects": self.projects}, f, ensure_ascii=False, indent=2)

    def create_project(self, name):
        proj_id = f"proj_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        project = {"id": proj_id, "name": name, "created_at": datetime.now().isoformat()}
        self.projects.append(project)
        self._save_projects()

        proj_dir = DATA_DIR / "projects" / proj_id
        proj_dir.mkdir(parents=True, exist_ok=True)
        with open(proj_dir / "notes.json", "w", encoding="utf-8") as f:
            json.dump({"notes": []}, f, ensure_ascii=False, indent=2)

        default_config = {
            "dev_tools": self._get_default_dev_tools(),
            "plans": []
        }
        with open(proj_dir / "config.json", "w", encoding="utf-8") as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)
        return project

    def _get_default_dev_tools(self):
        system = platform.system()
        if system == "Windows":
            return [
                {"name": "PyCharm", "command": "pycharm64.exe", "args": ["."]},
                {"name": "VSCode", "command": "code", "args": ["."]},
                {"name": "Terminal", "command": "cmd", "args": ["/k", "cd", "."]},
            ]
        elif system == "Darwin":
            return [
                {"name": "PyCharm", "command": "open", "args": ["-a", "PyCharm", "."]},
                {"name": "VSCode", "command": "code", "args": ["."]},
                {"name": "Terminal", "command": "open", "args": ["-a", "Terminal", "."]},
            ]
        else:
            return [
                {"name": "PyCharm", "command": "pycharm", "args": ["."]},
                {"name": "VSCode", "command": "code", "args": ["."]},
                {"name": "Terminal", "command": "gnome-terminal", "args": ["--working-directory=."]},
            ]

    def get_project_dir(self, proj_id):
        return DATA_DIR / "projects" / proj_id

    def load_notes(self, proj_id):
        path = self.get_project_dir(proj_id) / "notes.json"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f).get("notes", [])
        return []

    def save_notes(self, proj_id, notes):
        path = self.get_project_dir(proj_id) / "notes.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"notes": notes}, f, ensure_ascii=False, indent=2)

    def load_config(self, proj_id):
        path = self.get_project_dir(proj_id) / "config.json"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"dev_tools": [], "plans": []}

    def save_config(self, proj_id, config):
        path = self.get_project_dir(proj_id) / "config.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def load_mindmaps(self, proj_id):
        path = self.get_project_dir(proj_id) / "mindmaps.json"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"nodes": []}

    def save_mindmaps(self, proj_id, data):
        path = self.get_project_dir(proj_id) / "mindmaps.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def delete_project(self, proj_id):
        self.projects = [p for p in self.projects if p["id"] != proj_id]
        self._save_projects()
        proj_dir = self.get_project_dir(proj_id)
        if proj_dir.exists():
            shutil.rmtree(proj_dir)
