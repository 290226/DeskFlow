"""Right-docked hover drawer: projects, calendar, plans and tag filter.

The drawer lives at the **far right** of the window.  While collapsed it is a
12 px grip; hovering the grip slides the panel out of the window's right edge,
and the Pin button keeps it open.

Note on the animation (bug fix)
-------------------------------
The widget is laid out with a ``Fixed`` size policy, so animating
``maximumWidth`` alone leaves it clamped at ``minimumWidth``: Qt had nothing
that told it to grow, so the drawer stayed 12 px wide and its content was never
visible.  Both ``minimumWidth`` and ``maximumWidth`` are now driven by a
``QParallelAnimationGroup``, so the measured width really follows the animation.

The sidebar only *displays* state and emits requests; the main window performs
the actual data changes and pushes fresh state back in via ``set_plans()`` /
``set_projects()`` / ``set_tags()``.

Every plan row carries its plan id in ``Qt.ItemDataRole.UserRole``, so filtering
the list can never make a checkbox toggle the wrong record.
"""

from PySide6.QtCore import (
    QDate,
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QLinearGradient,
    QPainter,
    QTextCharFormat,
)
from PySide6.QtWidgets import (
    QApplication,
    QCalendarWidget,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config import (
    APP_NAME,
    APP_VERSION,
    C_ACCENT,
    C_BG_HOVER,
    C_BG_MAIN,
    C_BORDER,
    C_BORDER_DARK,
    C_SIDEBAR_BG,
    C_SIDEBAR_GRIP,
    C_TEXT_MUTED,
    C_TEXT_PRIMARY,
    C_TEXT_SECONDARY,
    C_TOOL_BG,
    C_TOOL_BLUE,
    FONT_SERIF,
    FONT_UI,
    PRIORITY_COLORS,
    PRIORITY_LABELS,
    TAG_COLOR_DEFAULT,
    TAG_COLORS,
)
from util import human_date, parse_date, summarize, week_bounds

COLLAPSED_WIDTH = 12
EXPANDED_WIDTH = 326
ANIM_MS = 200

FILTER_MODES = [
    ("all", "All tasks"),
    ("today", "Due today"),
    ("week", "Due this week"),
    ("pending", "Open"),
    ("done", "Completed"),
]


class DotCalendar(QCalendarWidget):
    """Month view that paints a small due-date dot under every day with open tasks."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dot_colors = {}
        self._selection_text = QColor("#FFFFFF")

    def set_dot_dates(self, mapping):
        """mapping: {QDate: QColor} - a filled dot is painted for each of these days."""
        self._dot_colors = dict(mapping or {})
        self.update()

    def set_selection_text_color(self, color):
        """Dot colour used on the selected cell so it stays visible on the highlight."""
        self._selection_text = QColor(color)
        self.update()

    def paintCell(self, painter, rect, date):
        super().paintCell(painter, rect, date)
        color = self._dot_colors.get(date)
        if color is None:
            return
        if date == self.selectedDate():
            color = self._selection_text
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QPointF(rect.center().x(), rect.bottom() - 4.5), 2.4, 2.4)
        painter.restore()


class GripHandle(QWidget):
    """Thin sliver docked to the window's right edge that reveals the drawer."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("deskflowGrip")
        self.setFixedWidth(COLLAPSED_WIDTH)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip("Hover to open the sidebar · click to toggle")
        self._hot = False

    def enterEvent(self, event):
        self._hot = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hot = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            self.clicked.emit()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        painter.fillRect(rect, QColor(C_BG_MAIN if not self._hot else C_TOOL_BG))

        bar_w, bar_h = 4.0, 56.0
        x = rect.center().x() - bar_w / 2.0
        y = rect.center().y() - bar_h / 2.0
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(C_ACCENT if self._hot else C_SIDEBAR_GRIP))
        painter.drawRoundedRect(QRectF(x, y, bar_w, bar_h), bar_w / 2.0, bar_w / 2.0)


class DrawerFrame(QFrame):
    """The panel itself: fills the sidebar and paints a soft edge on its left."""

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        gradient = QLinearGradient(0.0, 0.0, 14.0, 0.0)
        gradient.setColorAt(0.0, QColor(0, 0, 0, 16))
        gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(QRectF(0.0, 0.0, 14.0, float(self.height())), gradient)


class Sidebar(QWidget):
    project_selected = Signal(str)
    project_create_requested = Signal()
    project_rename_requested = Signal()
    project_delete_requested = Signal()
    project_export_requested = Signal()

    plan_add_requested = Signal(str)
    plan_toggle_requested = Signal(str, bool)
    plan_text_changed = Signal(str, str)
    plan_date_changed = Signal(str, object)
    plan_priority_changed = Signal(str, str)
    plan_delete_requested = Signal(str)
    plan_clear_done_requested = Signal()

    tag_filter_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._plans = []
        self._updating = False
        self._expanded = False
        self._pinned = False
        self._filter_date = None

        self.setObjectName("deskflowSidebar")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setMinimumWidth(COLLAPSED_WIDTH)
        self.setMaximumWidth(COLLAPSED_WIDTH)
        self.setStyleSheet(self._style_sheet())

        self.grip = GripHandle(self)
        self.grip.clicked.connect(self.toggle)

        self.drawer = DrawerFrame(self)
        self.drawer.setObjectName("deskflowDrawer")
        self._build_drawer()
        self.drawer.raise_()

        # minimum + maximum width move together: that is what makes the
        # expansion visible for a Fixed-size widget.
        self._anim = QParallelAnimationGroup(self)
        for prop in (b"minimumWidth", b"maximumWidth"):
            animation = QPropertyAnimation(self, prop, self)
            animation.setDuration(ANIM_MS)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._anim.addAnimation(animation)

        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(140)
        self._hover_timer.timeout.connect(self._check_hover)
        self._hover_timer.start()

    # ==================================================================
    # construction
    # ==================================================================
    def _style_sheet(self):
        return """
        #deskflowSidebar {{ font-family: {font}; }}
        #deskflowGrip {{ border: none; }}
        #deskflowDrawer {{
            background-color: {page};
            border-left: 1px solid {border};
            border-top-left-radius: 10px;
            border-bottom-left-radius: 10px;
        }}
        #deskflowDrawerHeader {{ background: transparent; }}
        #deskflowTitle {{ font-family: {serif}; font-size: 17px; font-weight: bold; color: {text}; }}
        #deskflowVersion {{ color: {muted}; font-size: 10px; }}
        #deskflowCard {{
            background-color: {card};
            border: 1px solid {border};
            border-radius: 10px;
        }}
        QLabel#deskflowSection {{
            color: {muted}; font-size: 10px; font-weight: bold; letter-spacing: 1.2px;
        }}
        QLabel#deskflowHint {{ color: {muted}; font-size: 10px; }}
        QLabel#deskflowStats {{ color: {secondary}; font-size: 10px; }}
        QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
        QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px 2px 2px 0; }}
        QScrollBar::handle:vertical {{
            background: {grip}; border-radius: 4px; min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {border_dark}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        QComboBox {{
            background-color: {hover}; border: 1px solid {border}; border-radius: 8px;
            padding: 4px 8px; font-size: 12px; color: {text}; min-height: 16px;
        }}
        QComboBox:hover {{ border-color: {border_dark}; background-color: #FFFFFF; }}
        QComboBox::drop-down {{ border: none; width: 18px; }}
        QComboBox QAbstractItemView {{
            background: #FFFFFF; border: 1px solid {border}; border-radius: 8px;
            padding: 3px; outline: none;
            selection-background-color: {tool_bg}; selection-color: {tool};
        }}
        QLineEdit {{
            background-color: {hover}; border: 1px solid {border}; border-radius: 8px;
            padding: 5px 8px; font-size: 12px; color: {text};
        }}
        QLineEdit:focus {{ border: 1px solid {tool}; background: #FFFFFF; }}
        QToolButton#deskflowToolButton {{
            background-color: {hover}; border: 1px solid {border}; border-radius: 8px;
            padding: 4px 9px; color: {secondary}; font-size: 12px;
        }}
        QToolButton#deskflowToolButton:hover {{
            background-color: #FFFFFF; border-color: {tool}; color: {tool};
        }}
        QToolButton#deskflowPinButton {{
            background-color: #FFFFFF; border: 1px solid {border}; border-radius: 9px;
            padding: 2px 10px; color: {muted}; font-size: 10px;
        }}
        QToolButton#deskflowPinButton:hover {{ background-color: {hover}; color: {secondary}; }}
        QToolButton#deskflowPinButton:checked {{
            background-color: {tool_bg}; border-color: {tool}; color: {tool}; font-weight: bold;
        }}
        QListWidget {{ background: transparent; border: none; outline: none; font-size: 12px; }}
        QListWidget::item {{ color: {text}; padding: 5px 7px; border-radius: 6px; }}
        QListWidget::item:hover {{ background-color: {hover}; }}
        QListWidget::item:selected {{ background-color: {tool_bg}; color: {tool}; }}
        """.format(
            font=FONT_UI,
            serif=FONT_SERIF,
            page=C_BG_MAIN,
            card=C_SIDEBAR_BG,
            border=C_BORDER,
            border_dark=C_BORDER_DARK,
            hover=C_BG_HOVER,
            grip=C_SIDEBAR_GRIP,
            text=C_TEXT_PRIMARY,
            secondary=C_TEXT_SECONDARY,
            muted=C_TEXT_MUTED,
            tool=C_TOOL_BLUE,
            tool_bg=C_TOOL_BG,
        )

    def _build_drawer(self):
        outer = QVBoxLayout(self.drawer)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ------------------------------------------------ header
        header = QWidget()
        header.setObjectName("deskflowDrawerHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 12, 10)
        header_layout.setSpacing(8)

        title = QLabel(APP_NAME)
        title.setObjectName("deskflowTitle")
        version = QLabel("v{}".format(APP_VERSION))
        version.setObjectName("deskflowVersion")

        self.pin_btn = QToolButton()
        self.pin_btn.setObjectName("deskflowPinButton")
        self.pin_btn.setText("Pin")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.pin_btn.setToolTip("Keep the sidebar open")
        self.pin_btn.toggled.connect(self._on_pin_toggled)

        self.collapse_btn = QToolButton()
        self.collapse_btn.setObjectName("deskflowPinButton")
        self.collapse_btn.setText("»")
        self.collapse_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.collapse_btn.setToolTip("Collapse the sidebar")
        self.collapse_btn.clicked.connect(self._collapse_clicked)

        header_layout.addWidget(title)
        header_layout.addWidget(version)
        header_layout.addStretch(1)
        header_layout.addWidget(self.pin_btn)
        header_layout.addWidget(self.collapse_btn)
        outer.addWidget(header)

        # ------------------------------------------------ scrollable body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("deskflowDrawerBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(12, 2, 12, 14)
        body_layout.setSpacing(12)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        body_layout.addWidget(self._build_project_card())
        body_layout.addWidget(self._build_calendar_card())
        body_layout.addWidget(self._build_plans_card())
        body_layout.addWidget(self._build_tags_card())

        footer = QLabel("Ctrl+B toggles this panel · Pin keeps it open")
        footer.setObjectName("deskflowHint")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body_layout.addWidget(footer)
        body_layout.addStretch(1)

    @staticmethod
    def _card():
        card = QFrame()
        card.setObjectName("deskflowCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        return card, layout

    @staticmethod
    def _section_label(text):
        label = QLabel(text)
        label.setObjectName("deskflowSection")
        return label

    @staticmethod
    def _tool_button(text, tooltip):
        button = QToolButton()
        button.setObjectName("deskflowToolButton")
        button.setText(text)
        button.setToolTip(tooltip)
        button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        return button

    def _build_project_card(self):
        card, layout = self._card()
        layout.addWidget(self._section_label("PROJECT"))

        row = QHBoxLayout()
        row.setSpacing(6)
        self.project_combo = QComboBox()
        self.project_combo.setMinimumWidth(60)
        self.project_combo.setToolTip("Switch project")
        self.project_combo.currentIndexChanged.connect(self._on_project_index_changed)

        self.project_menu_btn = self._tool_button("…", "Project actions")
        self.project_menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        project_menu = QMenu(self.project_menu_btn)
        project_menu.addAction("New project", self.project_create_requested.emit)
        project_menu.addAction("Rename project", self.project_rename_requested.emit)
        project_menu.addAction("Export project", self.project_export_requested.emit)
        project_menu.addSeparator()
        project_menu.addAction("Delete project", self.project_delete_requested.emit)
        self.project_menu_btn.setMenu(project_menu)

        row.addWidget(self.project_combo, 1)
        row.addWidget(self.project_menu_btn)
        layout.addLayout(row)
        return card

    def _build_calendar_card(self):
        card, layout = self._card()
        layout.addWidget(self._section_label("CALENDAR"))

        self.calendar = DotCalendar()
        self.calendar.setObjectName("deskflowCalendar")
        self.calendar.setGridVisible(False)
        self.calendar.setVerticalHeaderFormat(
            QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader
        )
        self.calendar.setHorizontalHeaderFormat(
            QCalendarWidget.HorizontalHeaderFormat.ShortDayNames
        )
        self.calendar.setFixedHeight(188)
        self.calendar.setStyleSheet(
            """
            QCalendarWidget QWidget {{
                background-color: {card}; color: {text}; font-size: 11px;
            }}
            QCalendarWidget QWidget#qt_calendar_navigationbar {{
                background-color: {card}; border-bottom: 1px solid {border};
            }}
            QCalendarWidget QToolButton {{
                background: transparent; border: none; border-radius: 6px;
                color: {text}; font-size: 11px; padding: 3px 6px; margin: 1px;
            }}
            QCalendarWidget QToolButton:hover {{ background-color: {hover}; }}
            QCalendarWidget QMenu {{ background-color: #FFFFFF; }}
            QCalendarWidget QSpinBox {{
                background-color: #FFFFFF; border: 1px solid {border};
                border-radius: 6px; color: {text};
            }}
            QCalendarWidget QAbstractItemView:enabled {{
                background-color: {card}; color: {text}; outline: none;
                selection-background-color: {tool}; selection-color: white;
            }}
            QCalendarWidget QAbstractItemView:disabled {{ color: {muted}; }}
            """.format(
                card=C_SIDEBAR_BG,
                text=C_TEXT_PRIMARY,
                border=C_BORDER,
                hover=C_BG_HOVER,
                muted=C_TEXT_MUTED,
                tool=C_TOOL_BLUE,
            )
        )
        self.calendar.set_selection_text_color("#FFFFFF")
        self.calendar.clicked.connect(self._on_calendar_clicked)
        self.calendar.selectionChanged.connect(self._on_calendar_selection)
        layout.addWidget(self.calendar)
        return card

    def _build_plans_card(self):
        card, layout = self._card()

        header = QHBoxLayout()
        header.setSpacing(6)
        header.addWidget(self._section_label("TASKS"))
        header.addStretch(1)
        self.plan_stats = QLabel("0/0")
        self.plan_stats.setObjectName("deskflowStats")
        header.addWidget(self.plan_stats)
        layout.addLayout(header)

        self.filter_combo = QComboBox()
        for key, label in FILTER_MODES:
            self.filter_combo.addItem(label, key)
        self.filter_combo.setToolTip("Filter the task list")
        self.filter_combo.currentIndexChanged.connect(lambda _=0: self._refresh_plan_list())
        layout.addWidget(self.filter_combo)

        add_row = QHBoxLayout()
        add_row.setSpacing(6)
        self.plan_input = QLineEdit()
        self.plan_input.setPlaceholderText("Add a task, press Enter")
        self.plan_input.returnPressed.connect(self._on_plan_add)
        add_btn = self._tool_button("+", "Add task")
        add_btn.clicked.connect(self._on_plan_add)
        add_row.addWidget(self.plan_input, 1)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

        self.plan_list = QListWidget()
        self.plan_list.setMinimumHeight(150)
        self.plan_list.setMaximumHeight(250)
        self.plan_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.plan_list.customContextMenuRequested.connect(self._on_plan_menu)
        self.plan_list.itemChanged.connect(self._on_plan_item_changed)
        self.plan_list.itemDoubleClicked.connect(self._on_plan_double_clicked)
        layout.addWidget(self.plan_list)

        hint = QLabel("Right-click a task for priority & due date")
        hint.setObjectName("deskflowHint")
        layout.addWidget(hint)
        return card

    def _build_tags_card(self):
        card, layout = self._card()
        layout.addWidget(self._section_label("TAGS"))

        self.tag_list = QListWidget()
        self.tag_list.setMaximumHeight(140)
        self.tag_list.itemClicked.connect(self._on_tag_clicked)
        layout.addWidget(self.tag_list)
        return card

    # ==================================================================
    # geometry
    # ==================================================================
    def resizeEvent(self, event):
        width = max(self.width(), COLLAPSED_WIDTH)
        self.grip.setGeometry(width - COLLAPSED_WIDTH, 0, COLLAPSED_WIDTH, self.height())
        self.drawer.setGeometry(0, 0, width, self.height())
        super().resizeEvent(event)

    def is_expanded(self):
        return self._expanded

    def expand(self):
        if self._expanded:
            return
        self._expanded = True
        self.grip.setVisible(False)
        self._animate(EXPANDED_WIDTH)

    def collapse(self):
        if not self._expanded:
            return
        self._expanded = False
        self.grip.setVisible(True)
        self._animate(COLLAPSED_WIDTH)

    def toggle(self):
        self.collapse() if self._expanded else self.expand()

    def _animate(self, target):
        target = int(target)
        if self._anim.state() == QParallelAnimationGroup.State.Running:
            self._anim.stop()
        start = int(self.maximumWidth())
        # PySide6 exposes animationAt()/animationCount(), not animations()
        for index in range(self._anim.animationCount()):
            animation = self._anim.animationAt(index)
            animation.setStartValue(start)
            animation.setEndValue(target)
        self._anim.start()

    def _on_pin_toggled(self, checked):
        self._pinned = bool(checked)
        self.pin_btn.setText("Pinned" if self._pinned else "Pin")
        if self._pinned:
            self.expand()

    def _collapse_clicked(self):
        self.pin_btn.setChecked(False)
        self.collapse()

    def _check_hover(self):
        if self._pinned:
            return
        window = self.window()
        if window is not None and not window.isActiveWindow():
            return
        if QApplication.activePopupWidget() is not None:
            return
        if QApplication.activeModalWidget() is not None:
            return
        inside = self.rect().contains(self.mapFromGlobal(QCursor.pos()))
        if inside and not self._expanded:
            self.expand()
        elif not inside and self._expanded:
            self.collapse()

    # ==================================================================
    # projects
    # ==================================================================
    def set_projects(self, projects, current_id=None):
        self._updating = True
        self.project_combo.clear()
        for project in projects:
            self.project_combo.addItem(project.get("name", "Untitled"), project.get("id"))
        if current_id:
            index = self.project_combo.findData(current_id)
            if index >= 0:
                self.project_combo.setCurrentIndex(index)
        self._updating = False

    def _on_project_index_changed(self, index):
        if self._updating or index < 0:
            return
        proj_id = self.project_combo.itemData(index)
        if proj_id:
            self.project_selected.emit(proj_id)

    # ==================================================================
    # plans
    # ==================================================================
    def set_plans(self, plans):
        self._plans = list(plans or [])
        self._highlight_calendar()
        self._refresh_plan_list()

    def _filter_mode(self):
        data = self.filter_combo.currentData()
        return data or "all"

    def _visible_plans(self):
        mode = self._filter_mode()
        plans = self._plans
        if mode == "today":
            target = QDate.currentDate().toString("yyyy-MM-dd")
            plans = [p for p in plans if p.get("due_date") == target and not p["done"]]
        elif mode == "week":
            start, end = week_bounds()
            plans = [
                p
                for p in plans
                if p.get("due_date")
                and start <= parse_date(p["due_date"]) <= end
                and not p["done"]
            ]
        elif mode == "pending":
            plans = [p for p in plans if not p["done"]]
        elif mode == "done":
            plans = [p for p in plans if p["done"]]
        if self._filter_date:
            plans = [p for p in plans if p.get("due_date") == self._filter_date]
        return plans

    def _refresh_plan_list(self):
        self._updating = True
        self.plan_list.clear()
        for plan in self._visible_plans():
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, plan["id"])
            item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            item.setCheckState(
                Qt.CheckState.Checked if plan["done"] else Qt.CheckState.Unchecked
            )
            label = summarize(plan["text"], 40)
            due = plan.get("due_date")
            if due:
                label = "{}  ·  {}".format(label, human_date(due))
            if plan.get("priority") and plan["priority"] != "normal":
                label = "{}  [{}]".format(label, PRIORITY_LABELS.get(plan["priority"], ""))
            item.setText(label)
            color = QColor(PRIORITY_COLORS.get(plan.get("priority", "normal"), C_TEXT_SECONDARY))
            if plan["done"]:
                color = QColor(C_TEXT_MUTED)
                font = QFont()
                font.setStrikeOut(True)
                item.setFont(font)
            item.setForeground(color)
            item.setToolTip(plan["text"])
            self.plan_list.addItem(item)
        self._updating = False

        total = len(self._plans)
        done = sum(1 for p in self._plans if p["done"])
        self.plan_stats.setText("{}/{} done".format(done, total))

    def _plan_id_at(self, item):
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_plan_add(self):
        text = self.plan_input.text().strip()
        if not text:
            return
        self.plan_input.clear()
        self.plan_add_requested.emit(text)

    def _on_plan_item_changed(self, item):
        if self._updating:
            return
        plan_id = self._plan_id_at(item)
        if not plan_id:
            return
        done = item.checkState() == Qt.CheckState.Checked
        self.plan_toggle_requested.emit(plan_id, done)

    def _on_plan_double_clicked(self, item):
        plan_id = self._plan_id_at(item)
        plan = next((p for p in self._plans if p["id"] == plan_id), None)
        if not plan:
            return
        text, ok = QInputDialog.getText(self, "Edit Task", "Task:", text=plan["text"])
        if ok and text.strip():
            self.plan_text_changed.emit(plan_id, text.strip())

    def _on_plan_menu(self, pos: QPoint):
        item = self.plan_list.itemAt(pos)
        if not item:
            return
        plan_id = self._plan_id_at(item)
        plan = next((p for p in self._plans if p["id"] == plan_id), None)
        if not plan:
            return

        menu = QMenu(self)
        menu.addAction("Edit text…", lambda: self._on_plan_double_clicked(item))
        date_menu = menu.addMenu("Due date")
        date_menu.addAction(
            "Today",
            lambda: self.plan_date_changed.emit(
                plan_id, QDate.currentDate().toString("yyyy-MM-dd")
            ),
        )
        date_menu.addAction(
            "Tomorrow",
            lambda: self.plan_date_changed.emit(
                plan_id, QDate.currentDate().addDays(1).toString("yyyy-MM-dd")
            ),
        )
        date_menu.addAction("Clear", lambda: self.plan_date_changed.emit(plan_id, None))
        priority_menu = menu.addMenu("Priority")
        for key in ("low", "normal", "high"):
            priority_menu.addAction(
                PRIORITY_LABELS[key],
                lambda _=False, k=key: self.plan_priority_changed.emit(plan_id, k),
            )
        menu.addSeparator()
        done_label = "Mark as open" if plan["done"] else "Mark as done"
        menu.addAction(
            done_label, lambda: self.plan_toggle_requested.emit(plan_id, not plan["done"])
        )
        menu.addSeparator()
        menu.addAction("Delete task", lambda: self.plan_delete_requested.emit(plan_id))
        menu.addAction("Clear completed", self.plan_clear_done_requested.emit)
        menu.exec(self.plan_list.mapToGlobal(pos))

    # ==================================================================
    # calendar
    # ==================================================================
    def _on_calendar_selection(self):
        selected = self.calendar.selectedDate().toString("yyyy-MM-dd")
        if self._filter_date and self._filter_date != selected:
            return
        self._highlight_calendar()

    def _on_calendar_clicked(self, date: QDate):
        value = date.toString("yyyy-MM-dd")
        if self._filter_date == value:
            self._filter_date = None
        else:
            self._filter_date = value
        self._refresh_plan_list()

    def _highlight_calendar(self):
        default = QTextCharFormat()
        self.calendar.setDateTextFormat(QDate(), default)
        pending = {}
        for plan in self._plans:
            due = plan.get("due_date")
            if not due or plan["done"]:
                continue
            pending[due] = pending.get(due, 0) + 1
        dots = {}
        for text, count in pending.items():
            date = QDate.fromString(text, "yyyy-MM-dd")
            if not date.isValid():
                continue
            color = QColor(C_ACCENT if count > 1 else C_TOOL_BLUE)
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            fmt.setFontWeight(QFont.Weight.Bold)
            self.calendar.setDateTextFormat(date, fmt)
            dots[date] = color
        self.calendar.set_dot_dates(dots)

    def selected_plan_date(self):
        return self._filter_date

    def clear_date_filter(self):
        self._filter_date = None
        self._refresh_plan_list()

    # ==================================================================
    # tags
    # ==================================================================
    def set_tags(self, tags, active=None):
        self._updating = True
        self.tag_list.clear()
        all_item = QListWidgetItem("All notes")
        all_item.setData(Qt.ItemDataRole.UserRole, "")
        self.tag_list.addItem(all_item)
        counts = {}
        for tag, count in tags:
            counts[tag] = count
        for tag in sorted(counts):
            item = QListWidgetItem("#{}  ({})".format(tag, counts[tag]))
            item.setData(Qt.ItemDataRole.UserRole, tag)
            item.setForeground(QColor(TAG_COLORS.get(tag, TAG_COLOR_DEFAULT)))
            self.tag_list.addItem(item)
        selected = 0 if not active else 1
        if self.tag_list.count() > selected:
            self.tag_list.setCurrentRow(selected)
        self._updating = False

    def _on_tag_clicked(self, item):
        if self._updating:
            return
        tag = item.data(Qt.ItemDataRole.UserRole) or ""
        self.tag_filter_changed.emit(tag)
