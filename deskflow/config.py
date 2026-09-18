"""DeskFlow - palette, dimensions and application constants.

Single source of truth for colors, sizes and tunable values.
Keep this module dependency-free so every other module can import it safely.
"""

APP_NAME = "DeskFlow"
APP_VERSION = "0.2.0"
APP_TAGLINE = "Desktop project board"

# --------------------------------------------------------------------- Colors
# Backgrounds
C_BG_MAIN = "#F7F6F3"
C_BG_CANVAS = "#F0EEE9"
C_BG_CARD = "#FFFFFF"
C_BG_HOVER = "#F5F3EF"

# Text
C_TEXT_PRIMARY = "#1A1A1A"
C_TEXT_SECONDARY = "#5C5C5C"
C_TEXT_MUTED = "#8C8C8C"

# Borders
C_BORDER = "#E2E0DB"
C_BORDER_DARK = "#D0CEC9"

# Accent (Nature red)
C_ACCENT = "#B83232"
C_ACCENT_HOVER = "#9E2A2A"

# Tools / secondary actions
C_TOOL_BLUE = "#3A5A7C"
C_TOOL_HOVER = "#2D4A6A"
C_TOOL_BG = "#E8EDF2"

# Sidebar
C_SIDEBAR_BG = "#FFFFFF"
C_SIDEBAR_GRIP = "#D8D6D1"

# Canvas grid
C_GRID = "#E7E4DE"
C_GRID_STRONG = "#DCD8D0"

# Selection / highlight
C_HIGHLIGHT = "#F2D9A0"

# --------------------------------------------------------------------- Fonts
FONT_UI = "'Helvetica Neue', 'Segoe UI', Arial, sans-serif"
FONT_SERIF = "'Georgia', 'Times New Roman', serif"

# --------------------------------------------------------------------- Notes
# Muted, publication-grade sticky note colors.
NOTE_COLORS = [
    "#E8DED0", "#D0DDE8", "#D0E4D0", "#E4D0D8",
    "#E8E0D0", "#D0D8E4", "#E4D8D0", "#D0E0D8",
]

NOTE_FONT_SIZES = {"small": 11, "medium": 13, "large": 16}
NOTE_SIZES = {"small": (180, 140), "medium": (220, 180), "large": (280, 220)}
NOTE_DEFAULT_WIDTH = 220
NOTE_DEFAULT_HEIGHT = 180
NOTE_MIN_WIDTH = 150
NOTE_MIN_HEIGHT = 110
NOTE_MAX_WIDTH = 900
NOTE_MAX_HEIGHT = 700

# Reserved strip at the bottom-right corner of a note used as a resize grip.
NOTE_GRIP_SIZE = 16

# Vertical space reserved at the top of a note for tag pills.
NOTE_TAG_BAR = 26

# --------------------------------------------------------------------- Tags
TAG_COLORS = {
    "bug": "#C44B4B",
    "feature": "#4B7C4B",
    "idea": "#4B6B8C",
    "todo": "#8C6B4B",
    "done": "#6B6B6B",
    "urgent": "#B83232",
    "review": "#7C4B8C",
    "docs": "#4B8C7C",
}
TAG_COLOR_DEFAULT = "#8C8C8C"

# --------------------------------------------------------------------- Plans
PRIORITY_ORDER = ["low", "normal", "high"]
PRIORITY_COLORS = {
    "low": "#4B8C7C",
    "normal": "#8C8C8C",
    "high": "#C44B4B",
}
PRIORITY_LABELS = {
    "low": "Low",
    "normal": "Normal",
    "high": "High",
}

# --------------------------------------------------------------------- Canvas
ZOOM_MIN = 0.4
ZOOM_MAX = 2.5
ZOOM_STEP = 1.15
CANVAS_MIN_SIZE = 2400
CANVAS_PADDING = 240

# --------------------------------------------------------------------- Z order
# Notes and mind map nodes live in separate bands, so a note can never cover a
# mind map node no matter how often it is raised to the front.
Z_NOTE_BASE = 0.0
Z_NOTE_MAX = 999.0
Z_MINDMAP_BASE = 1000.0
Z_MINDMAP_MAX = 1999.0
Z_MINDMAP_GHOST = 2000.0

# --------------------------------------------------------------------- Misc
AUTOSAVE_INTERVAL_MS = 20000
UNDO_STACK_LIMIT = 30
