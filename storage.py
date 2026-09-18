"""Crash-safe JSON persistence helpers.

Every write goes to a temporary file first and is then atomically swapped in,
so a crash or a full disk can never leave a half-written document behind.
The previous good copy is kept next to the file as `<name>.json.bak`.
"""

import copy
import json
import os
from pathlib import Path


def _backup_path(path):
    path = Path(path)
    return path.with_name(path.name + ".bak")


def read_json(path, default):
    """Read JSON, falling back to the .bak copy and then to `default`."""
    path = Path(path)
    for candidate in (path, _backup_path(path)):
        if not candidate.exists():
            continue
        try:
            with open(candidate, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            continue
    return copy.deepcopy(default)


def write_json(path, data, backup=True):
    """Atomically write `data` as JSON. Returns True on success."""
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if backup and path.exists():
            try:
                with open(path, "rb") as src, open(_backup_path(path), "wb") as dst:
                    dst.write(src.read())
            except OSError:
                pass
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        return True
    except (OSError, TypeError, ValueError):
        return False


def read_text(path, default=""):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError):
        return default


def write_text(path, text):
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        return True
    except OSError:
        return False
