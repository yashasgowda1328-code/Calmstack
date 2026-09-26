"""
ReConstructAI - Sidebar Navigation

Grouped navigation with a strong active state, a subtle hover state and
readable labels. One entry per page, no dead links.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.components import COLORS, HealthChip, StatusDot
from app.ui.styles import HEALTH_PALETTE


class NavButton(QPushButton):
    """Navigation button. Checkable so the active page is unambiguous."""

    def __init__(self, text: str, glyph: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("navButton")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(34)
        self.setMaximumHeight(34)
        self.setText(f"{glyph}   {text}" if glyph else text)


class Sidebar(QWidget):
    """Left sidebar: brand, grouped navigation, component health."""

    navigation_changed = Signal(str)

    # (page_id, label, glyph, group)
    NAV_ITEMS = [
        ("dashboard", "Dashboard", "▦", "Workspace"),
        ("evidence", "Evidence", "▣", "Workspace"),
        ("recovery", "Recovery", "⬡", "Recovery"),
        ("deleted_recovery", "Deleted Data", "◫", "Recovery"),
        ("recovered", "Recovered", "◆", "Recovery"),
        ("reports", "Reports", "▤", "Analysis"),
        ("cases", "Cases", "◫", "Analysis"),
    ]

    #: Components shown in the sidebar health area.
    HEALTH_COMPONENTS = [
        ("engine", "Core Engine"),
        ("database", "Database"),
        ("recovery", "Recovery Engine"),
        ("storage", "Local Storage"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(236)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        self._buttons = {}
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        self._status_chips = {}
        self._status_dots = {}

        self._setup_ui()

    # ============================================================
    # Construction
    # ============================================================

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 18, 12, 14)
        layout.setSpacing(2)

        # Brand
        title = QLabel("ReConstructAI")
        title.setObjectName("brandTitle")
        layout.addWidget(title)
        layout.addSpacing(2)

        tagline = QLabel("Digital evidence workstation")
        tagline.setObjectName("pageSubtitle")
        layout.addWidget(tagline)
        layout.addSpacing(10)

        separator = QFrame()
        separator.setObjectName("navSeparator")
        separator.setFixedHeight(1)
        layout.addWidget(separator)

        # Grouped navigation
        current_group = None
        for page_id, label, glyph, group in self.NAV_ITEMS:
            if group != current_group:
                if current_group is not None:
                    layout.addSpacing(6)
                group_label = QLabel(group.upper())
                group_label.setObjectName("navGroupLabel")
                layout.addWidget(group_label)
                current_group = group

            button = NavButton(label, glyph)
            button.clicked.connect(lambda _checked, pid=page_id: self._on_nav_clicked(pid))
            self._button_group.addButton(button)
            self._buttons[page_id] = button
            layout.addWidget(button)

        layout.addStretch(1)

        # Component health
        health_title = QLabel("SYSTEM")
        health_title.setObjectName("navGroupLabel")
        layout.addWidget(health_title)

        health_frame = QFrame()
        health_frame.setObjectName("card")
        health_layout = QVBoxLayout(health_frame)
        health_layout.setContentsMargins(12, 10, 12, 10)
        health_layout.setSpacing(7)

        for key, label in self.HEALTH_COMPONENTS:
            row = QWidget()
            row_layout = QHBoxLayout()
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(7)

            name = QLabel(label)
            name.setObjectName("mutedLabel")
            name.setStyleSheet("font-size: 11px;")
            row_layout.addWidget(name, 1)

            dot = StatusDot(COLORS["warning"])
            row_layout.addWidget(dot)

            chip = HealthChip("Checking", "warning")
            row_layout.addWidget(chip)

            row.setLayout(row_layout)
            health_layout.addWidget(row)
            self._status_chips[key] = chip
            self._status_dots[key] = dot

        layout.addWidget(health_frame)

    # ============================================================
    # Navigation
    # ============================================================

    def _on_nav_clicked(self, page_id: str):
        self.navigation_changed.emit(page_id)

    def page_ids(self):
        return [item[0] for item in self.NAV_ITEMS]

    def set_page(self, page_id: str):
        """Programmatically set the active page."""
        button = self._buttons.get(page_id)
        if button is not None and not button.isChecked():
            button.setChecked(True)

    def current_page(self):
        checked = self._button_group.checkedButton()
        if checked is None:
            return None
        for page_id, button in self._buttons.items():
            if button is checked:
                return page_id
        return None

    # ============================================================
    # Component health
    # ============================================================

    def update_status(self, component: str, status: str, message: str = ""):
        """Update a component health indicator."""
        chip = self._status_chips.get(component)
        if chip is None:
            return
        label = message or status.capitalize()
        chip.set_state(label, status)
        color = HEALTH_PALETTE.get(status, HEALTH_PALETTE["warning"])[0]
        dot = self._status_dots.get(component)
        if dot is not None:
            dot.set_color(color)
