"""Hover-expandable sidebar with calendar and plans."""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QComboBox, QCalendarWidget, QListWidget, QLineEdit
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer, QEvent, QDate
from PySide6.QtGui import QCursor, QTextCharFormat, QColor, QFont

from config import (
    C_BG_MAIN, C_BG_CARD, C_BG_HOVER, C_TEXT_PRIMARY, C_TEXT_SECONDARY,
    C_TEXT_MUTED, C_BORDER, C_BORDER_DARK, C_TOOL_BLUE, C_TOOL_BG,
    C_SIDEBAR_BG, C_SIDEBAR_GRIP, C_ACCENT
)


class SidebarDrawer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded = False
        self._handle_w = 6
        self._content_w = 260
        self._full_w = self._handle_w + self._content_w
        self.setMaximumWidth(self._handle_w)
        self.setMinimumWidth(self._handle_w)
        self.setStyleSheet("background-color: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Grip
        self.handle = QWidget()
        self.handle.setFixedWidth(self._handle_w)
        self.handle.setStyleSheet(f"background-color: {C_SIDEBAR_GRIP}; border-right: 1px solid {C_BORDER};")
        layout.addWidget(self.handle)

        # Content
        self.content = QWidget()
        self.content.setFixedWidth(self._content_w)
        self.content.setStyleSheet(f"""
            QWidget {{ background-color: {C_SIDEBAR_BG}; color: {C_TEXT_PRIMARY}; border-right: 1px solid {C_BORDER}; }}
            QPushButton {{ background-color: {C_BG_MAIN}; color: {C_TEXT_PRIMARY}; border: 1px solid {C_BORDER}; border-radius: 4px; padding: 5px 10px; font-size: 12px; font-family: 'Helvetica Neue', Arial, sans-serif; }}
            QPushButton:hover {{ background-color: {C_BG_HOVER}; border-color: {C_BORDER_DARK}; }}
            QComboBox {{ background-color: {C_BG_CARD}; color: {C_TEXT_PRIMARY}; border: 1px solid {C_BORDER}; border-radius: 4px; padding: 5px; font-family: 'Helvetica Neue', Arial, sans-serif; }}
            QListWidget {{ background-color: {C_BG_CARD}; border: 1px solid {C_BORDER}; border-radius: 4px; color: {C_TEXT_PRIMARY}; padding: 3px; font-family: 'Helvetica Neue', Arial, sans-serif; }}
            QListWidget::item {{ padding: 6px; border-radius: 3px; }}
            QListWidget::item:selected {{ background-color: {C_TOOL_BG}; color: {C_TOOL_BLUE}; }}
            QCalendarWidget {{ background-color: {C_BG_CARD}; border: 1px solid {C_BORDER}; border-radius: 4px; }}
            QCalendarWidget QTableView {{ background-color: {C_BG_CARD}; color: {C_TEXT_PRIMARY}; selection-background-color: {C_TOOL_BG}; selection-color: {C_TOOL_BLUE}; font-family: 'Helvetica Neue', Arial, sans-serif; }}
            QLabel {{ color: {C_TEXT_SECONDARY}; font-size: 11px; font-family: 'Helvetica Neue', Arial, sans-serif; }}
            QLineEdit {{ background-color: {C_BG_CARD}; color: {C_TEXT_PRIMARY}; border: 1px solid {C_BORDER}; border-radius: 4px; padding: 5px; font-family: 'Helvetica Neue', Arial, sans-serif; }}
        """)
        cl = QVBoxLayout(self.content)
        cl.setContentsMargins(14, 16, 14, 16)
        cl.setSpacing(10)

        title = QLabel("DeskFlow")
        title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {C_TEXT_PRIMARY}; font-family: 'Georgia', serif;")
        cl.addWidget(title)

        div = QWidget()
        div.setFixedHeight(1)
        div.setStyleSheet(f"background-color: {C_BORDER};")
        cl.addWidget(div)

        cl.addWidget(QLabel("PROJECT"))
        self.project_combo = QComboBox()
        cl.addWidget(self.project_combo)

        h = QHBoxLayout()
        self.new_btn = QPushButton("New")
        self.del_btn = QPushButton("Delete")
        h.addWidget(self.new_btn)
        h.addWidget(self.del_btn)
        cl.addLayout(h)
        cl.addSpacing(6)

        # TAGS section
        cl.addWidget(QLabel("TAGS"))
        self.tag_list = QListWidget()
        self.tag_list.setMaximumHeight(100)
        self.tag_list.setStyleSheet(f"""
            QListWidget {{ background-color: {C_BG_CARD}; border: 1px solid {C_BORDER}; border-radius: 4px; color: {C_TEXT_PRIMARY}; padding: 3px; font-family: 'Helvetica Neue', Arial, sans-serif; }}
            QListWidget::item {{ padding: 5px 8px; border-radius: 3px; }}
            QListWidget::item:selected {{ background-color: {C_TOOL_BG}; color: {C_TOOL_BLUE}; }}
        """)
        cl.addWidget(self.tag_list)

        self.clear_tag_btn = QPushButton("Show All")
        self.clear_tag_btn.setStyleSheet(f"QPushButton {{ font-size: 11px; padding: 4px 8px; }}")
        cl.addWidget(self.clear_tag_btn)
        cl.addSpacing(6)

        cl.addWidget(QLabel("CALENDAR"))
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.setMaximumHeight(190)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.calendar.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.ShortDayNames)
        cl.addWidget(self.calendar)

        cl.addWidget(QLabel("PLANS"))
        self.plan_list = QListWidget()
        self.plan_list.setMaximumHeight(130)
        cl.addWidget(self.plan_list)

        # Plan input with date
        plan_input_row = QHBoxLayout()
        self.plan_input = QLineEdit()
        self.plan_input.setPlaceholderText("Type plan, press Enter...")
        plan_input_row.addWidget(self.plan_input)

        self.plan_date_btn = QPushButton("D")
        self.plan_date_btn.setFixedWidth(28)
        self.plan_date_btn.setToolTip("Select due date (default: today)")
        plan_input_row.addWidget(self.plan_date_btn)

        self.add_plan_btn = QPushButton("+")
        self.add_plan_btn.setFixedWidth(28)
        plan_input_row.addWidget(self.add_plan_btn)
        cl.addLayout(plan_input_row)

        self.plan_date = None  # stores selected QDate
        cl.addStretch()

        ver = QLabel("v0.1.0")
        ver.setStyleSheet(f"color: {C_TEXT_MUTED}; font-size: 10px;")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(ver)
        layout.addWidget(self.content)

        self.anim = QPropertyAnimation(self, b"maximumWidth")
        self.anim.setDuration(200)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Calendar click -> filter plans by date
        self.calendar.selectionChanged.connect(self._on_calendar_selection_changed)
        self._selected_plan_date = None

        self._install_filters(self)

    def _install_filters(self, widget):
        widget.installEventFilter(self)
        for child in widget.findChildren(QWidget):
            child.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Enter:
            if not self._expanded:
                self._expand()
        elif event.type() == QEvent.Type.Leave:
            QTimer.singleShot(250, self._check_collapse)
        return super().eventFilter(obj, event)

    def _check_collapse(self):
        pos = self.mapFromGlobal(QCursor.pos())
        if not self.rect().contains(pos):
            self._collapse()

    def _expand(self):
        self._expanded = True
        self.anim.stop()
        self.anim.setStartValue(self.maximumWidth())
        self.anim.setEndValue(self._full_w)
        self.anim.start()

    def _collapse(self):
        self._expanded = False
        self.anim.stop()
        self.anim.setStartValue(self.maximumWidth())
        self.anim.setEndValue(self._handle_w)
        self.anim.start()

    def _on_calendar_selection_changed(self):
        self._selected_plan_date = self.calendar.selectedDate()

    def get_selected_plan_date(self):
        return self._selected_plan_date or self.calendar.selectedDate()

    def highlight_calendar_dates(self, dates):
        """dates: list of QDate objects"""
        # Reset all
        self.calendar.setDateTextFormat(QDate(), QTextCharFormat())
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(C_ACCENT))
        fmt.setForeground(QColor("white"))
        fmt.setFontWeight(QFont.Weight.Bold)
        for d in dates:
            self.calendar.setDateTextFormat(d, fmt)

    def clear_calendar_highlight(self):
        self.calendar.setDateTextFormat(QDate(), QTextCharFormat())
