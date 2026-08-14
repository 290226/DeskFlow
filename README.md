# DeskFlow

> A desktop project manager inspired by the clean, muted aesthetic of scientific publications.

## Architecture

```
DeskFlow/
├── main.py              # Entry point (QApplication init)
├── config.py            # Nature-inspired color palette & constants
├── data_manager.py      # JSON persistence for projects/notes/config
├── note.py              # StickyNote + NoteTextEdit (drag, delete, pin)
├── canvas.py            # DesktopCanvas (QGraphicsView scene)
├── sidebar.py           # Hover-expandable sidebar (calendar, plans)
├── dev_tools.py         # DevToolButton + DevToolsDialog
├── main_window.py       # MainWindow (assembles all components)
└── data/                # Auto-created at runtime
    ├── projects.json
    └── projects/{id}/
        ├── notes.json
        └── config.json
```

## What is this?

DeskFlow is a desktop project management tool for developers who often stop mid-task, switch contexts, and forget where they left off.

The design philosophy draws from **Nature journal aesthetics**:
- **Muted, low-saturation colors** — easy on the eyes, publication-grade palettes
- **Generous whitespace** — warm off-white backgrounds, not harsh greys
- **Subtle borders** — 1px hairlines instead of heavy shadows
- **Nature red accent** (`#B83232`) — reserved for primary actions and pinned states
- **Serif + Sans-serif pairing** — Georgia for headings, Helvetica Neue for UI

## Quick Start

```bash
pip install -r requirements.txt
python main.py
```

## Usage

| Action | How |
|--------|-----|
| **Add note** | Click "+ Note" or right-click canvas |
| **Drag note** | Hold and drag near edges (18px margin) or top/bottom |
| **Pin note** | Click the red/grey pin on top |
| **Delete note** | Click the small **×** in bottom-right corner |
| **Open sidebar** | Hover mouse over left edge |
| **Launch IDE** | Click buttons in bottom bar |

## Features

- [x] Multi-project management
- [x] Sticky notes scattered on canvas with slight random rotation
- [x] Pin system (red = locked, grey = draggable)
- [x] Manual drag implementation (works reliably through QTextEdit proxy)
- [x] Delete button on each note (bottom-right ×)
- [x] Auto-save to JSON
- [x] Hover sidebar with calendar (Mon-Sun headers, no week numbers) and plans
- [x] Per-project dev tool quick launch
- [x] Custom tool configuration per project

## Color Palette

| Role | Hex | Usage |
|------|-----|-------|
| Background | `#F7F6F3` | Main window |
| Canvas | `#F0EEE9` | Note board (cream paper) |
| Card | `#FFFFFF` | Panels, popups |
| Primary Text | `#1A1A1A` | Headings, body |
| Secondary Text | `#5C5C5C` | Labels |
| Muted Text | `#8C8C8C` | Hints, version |
| Border | `#E2E0DB` | Dividers, outlines |
| Accent (Nature Red) | `#B83232` | Primary buttons, pinned pins |
| Tool Blue | `#3A5A7C` | Secondary actions |

## Tech Stack

- **GUI**: PySide6 (Qt for Python)
- **Graphics**: QGraphicsView / QGraphicsScene / Custom QGraphicsItem
- **Persistence**: JSON files
- **Typography**: Georgia (serif) + Helvetica Neue (sans-serif)

## License

MIT
