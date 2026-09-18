"""DeskFlow 0.2.0 — a quiet desktop board for sticky notes, mind maps and tasks.

Run
---
    python main.py

Requirements: Python 3.9+ and PySide6 (`pip install PySide6`).

Modules
-------
    main.py           entry point (QApplication + global style sheet)
    main_window.py    MainWindow: menus, toolbar, shortcuts, project/plan logic
    sidebar.py        hover-expandable drawer: project, calendar, plans, tags
    canvas.py         DesktopCanvas / CanvasScene: notes + mind map board
    note.py           StickyNote / NoteTextEdit graphics items
    mindmap.py        MindMapNode / MindMapEdge / MindMapManager
    editor.py         NoteEditorDialog (full note editor)
    data_manager.py   projects, notes, plans, settings, export
    storage.py        crash-safe JSON read/write
    config.py         colours, sizes, constants
    util.py           ids, dates, tags, text helpers

Data location
-------------
`<DeskFlow>/data` next to the code; falls back to `%APPDATA%/DeskFlow/data`
when the program folder is not writable, and can be overridden with
`python main.py --data-dir <folder>`. Deleted projects go to `data/.trash`
(10 most recent kept) and come back through File -> Restore deleted project.

First run
---------
Double-click `run.bat` (installs PySide6 when it is missing), or run
`pip install -r requirements.txt` followed by `python main.py`.

Highlights of 0.2.0
-------------------
* Fixed the v0.1.0 bug where filtering the plan list toggled the wrong task —
  every row now carries its plan id.
* Canvas: zoom (Ctrl+wheel), pan (middle drag / Space+drag), fit to content,
  toggleable grid, arrange notes, undo stack for deletions.
* Notes: colours, text size, tags with pills, resize grip, duplicate,
  flash-highlight when located from search, tag filter (dimming).
* Mind map: root/child nodes, smooth bezier edges, rename, per-node colour,
  delete subtree, auto node sizing.
* Sidebar: collapsible hover drawer with a pin, project quick-switch menu,
  calendar with due-date dots, task filters (all/today/week/open/done),
  priorities, inline edit, due dates.
* Search (Ctrl+F) across notes, tags and mind map nodes.
* Double-click an empty spot on the canvas to drop a new note there.
* Restore a deleted project from `.trash` (File ▸ Restore deleted project…),
  open the data folder from Help, or point the app elsewhere with
  `python main.py --data-dir <folder>` / check it with `--version`.
* Crash-safe saves with `.bak` fallback, debounced typing saves, autosave
  every 20 s, window geometry remembered.
* Export the whole project as JSON or Markdown.

Keyboard
--------
    Ctrl+N new note            Ctrl+M new mind map node
    Ctrl+E edit selected note  Ctrl+D duplicate note
    Ctrl+F find                Ctrl+Shift+Z undo last delete
    Ctrl+B sidebar             Ctrl+wheel zoom
    Ctrl+0 reset zoom          Ctrl+S save now
    Ctrl+Shift+E export Markdown
    Delete delete selection (asks first)
"""

__version__ = "0.2.0"
__all__ = ["config", "util", "storage", "data_manager", "note", "mindmap",
           "canvas", "sidebar", "editor", "main_window"]
