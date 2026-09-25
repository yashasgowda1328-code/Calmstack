"""
ReConstructAI - Shared UI Components

Reusable building blocks so every page shares one visual language:
status chips, buttons, page headers, section cards, empty states,
metric blocks and label/value detail rows.

No page should hand-roll its own badge or empty state.
"""

from typing import Any, Callable, Dict, Iterable, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.ui.styles import ALPHA, COLORS, MONO_FONT


# ====================================================================
# Constants and small helpers
# ====================================================================

#: Value shown whenever information is genuinely unavailable.
NOT_AVAILABLE = "Not available"

#: Textual state used when a value has not been measured at all.
NOT_MEASURED = "Not measured"

#: Column semantics shared by every forensic table.
COLUMN_ALIGN = {
    "name": Qt.AlignLeft | Qt.AlignVCenter,
    "text": Qt.AlignLeft | Qt.AlignVCenter,
    "mono": Qt.AlignLeft | Qt.AlignVCenter,
    "size": Qt.AlignRight | Qt.AlignVCenter,
    "number": Qt.AlignRight | Qt.AlignVCenter,
    "center": Qt.AlignCenter,
}


def format_size(size: Any) -> str:
    """Format a byte count for display. Non-numeric input reads as unavailable."""
    if size is None:
        return NOT_AVAILABLE
    try:
        value = float(size)
    except (TypeError, ValueError):
        return NOT_AVAILABLE
    if value < 0:
        return NOT_AVAILABLE
    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    while value >= 1024 and index < len(units) - 1:
        value /= 1024.0
        index += 1
    if index == 0:
        return f"{int(value)} {units[index]}"
    return f"{value:.1f} {units[index]}"


def format_bytes_exact(size: Any) -> str:
    """Format a byte count keeping the exact value alongside the unit."""
    formatted = format_size(size)
    if formatted == NOT_AVAILABLE:
        return formatted
    return f"{formatted} ({int(size):,} bytes)"


def format_offset(offset: Any) -> str:
    """Format a byte offset in hex plus decimal, as investigators expect."""
    if offset is None:
        return NOT_AVAILABLE
    try:
        value = int(offset)
    except (TypeError, ValueError):
        return NOT_AVAILABLE
    return f"0x{value:X} ({value:,})"


def format_score(value: Any, digits: int = 3) -> str:
    """Format a 0..1 score."""
    if value is None:
        return NOT_AVAILABLE
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return NOT_AVAILABLE


def format_entropy(value: Any, digits: int = 4) -> str:
    """Format an entropy measurement."""
    return format_score(value, digits)


def format_datetime(value: Any) -> str:
    """Format an ISO-ish timestamp, tolerating SQLite's naive strings."""
    if not value:
        return NOT_AVAILABLE
    from datetime import datetime

    text = str(value)
    try:
        cleaned = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return text[:16] if len(text) >= 16 else text


def shorten_hash(value: Any, head: int = 12, tail: int = 8) -> str:
    """Shorten a hash for table display while keeping both ends recognisable."""
    if not value:
        return NOT_AVAILABLE
    text = str(value)
    if len(text) <= head + tail + 1:
        return text
    return f"{text[:head]}...{text[-tail:]}"


def or_none(value: Any) -> Optional[str]:
    """Return a trimmed string, or None when there is nothing to show."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def as_text(value: Any) -> str:
    """Render any stored value as label text without losing the value."""
    if value is None:
        return NOT_AVAILABLE
    if isinstance(value, str):
        return value or NOT_AVAILABLE
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value) or NOT_AVAILABLE
    if isinstance(value, dict):
        return ", ".join(f"{key}={item}" for key, item in value.items()) or NOT_AVAILABLE
    return str(value)


# ====================================================================
# Status colours
# ====================================================================

#: status token -> (text colour, chip background, chip border)
STATUS_PALETTE: Dict[str, tuple] = {
    "UNANALYZED": (COLORS["text_muted"], COLORS["bg_elevated"], COLORS["border"]),
    "ANALYZING": (COLORS["warning"], ALPHA["warning_15"], ALPHA["warning_30"]),
    "HEALTHY": (COLORS["accent_primary"], ALPHA["accent_primary_15"], ALPHA["accent_primary_30"]),
    "SUSPICIOUS": (COLORS["warning"], ALPHA["warning_15"], ALPHA["warning_30"]),
    "CORRUPTED": (COLORS["danger"], ALPHA["danger_15"], ALPHA["danger_30"]),
    "ANALYSIS_FAILED": (COLORS["danger"], ALPHA["danger_15"], ALPHA["danger_30"]),
    "FRAGMENTED": (COLORS["accent_secondary"], ALPHA["accent_secondary_15"], ALPHA["accent_secondary_15"]),
    "PARTIALLY_RECOVERABLE": (COLORS["accent_primary"], ALPHA["accent_primary_15"], ALPHA["accent_primary_30"]),
    "RECOVERED": (COLORS["accent_primary"], ALPHA["accent_primary_15"], ALPHA["accent_primary_30"]),
    "PARTIALLY_RECONSTRUCTED": (COLORS["warning"], ALPHA["warning_15"], ALPHA["warning_30"]),
    "RECONSTRUCTED": (COLORS["accent_primary"], ALPHA["accent_primary_15"], ALPHA["accent_primary_30"]),
    "COMPLETED": (COLORS["accent_primary"], ALPHA["accent_primary_15"], ALPHA["accent_primary_30"]),
    "PENDING": (COLORS["text_secondary"], COLORS["bg_elevated"], COLORS["border"]),
    "PROCESSING": (COLORS["warning"], ALPHA["warning_15"], ALPHA["warning_30"]),
    "FAILED": (COLORS["danger"], ALPHA["danger_15"], ALPHA["danger_30"]),
    "EXTRACTED": (COLORS["accent_primary"], ALPHA["accent_primary_15"], ALPHA["accent_primary_30"]),
    "EXTRACTION_FAILED": (COLORS["danger"], ALPHA["danger_15"], ALPHA["danger_30"]),
    "DELETED_CANDIDATE": (COLORS["warning"], ALPHA["warning_15"], ALPHA["warning_30"]),
    "RECOVERABLE": (COLORS["accent_primary"], ALPHA["accent_primary_15"], ALPHA["accent_primary_30"]),
    "PARTIAL": (COLORS["warning"], ALPHA["warning_15"], ALPHA["warning_30"]),
    "DATA_UNAVAILABLE": (COLORS["danger"], ALPHA["danger_15"], ALPHA["danger_30"]),
    "REUSED_METADATA": (COLORS["warning"], ALPHA["warning_15"], ALPHA["warning_30"]),
    "READY": (COLORS["text_secondary"], COLORS["bg_elevated"], COLORS["border"]),
    "SCANNING": (COLORS["warning"], ALPHA["warning_15"], ALPHA["warning_30"]),
    "CANDIDATES_FOUND": (COLORS["accent_primary"], ALPHA["accent_primary_15"], ALPHA["accent_primary_30"]),
    "NO_CANDIDATES": (COLORS["text_secondary"], COLORS["bg_elevated"], COLORS["border"]),
    "CANDIDATE": (COLORS["text_secondary"], COLORS["bg_elevated"], COLORS["border"]),
    "READY_STATE": (COLORS["text_secondary"], COLORS["bg_elevated"], COLORS["border"]),
    "ERROR": (COLORS["danger"], ALPHA["danger_15"], ALPHA["danger_30"]),
}

#: Generic component health (Core Engine, Database, Recovery Engine, Storage).
HEALTH_PALETTE: Dict[str, tuple] = {
    "ready": (COLORS["accent_primary"], ALPHA["accent_primary_15"], ALPHA["accent_primary_30"]),
    "warning": (COLORS["warning"], ALPHA["warning_15"], ALPHA["warning_30"]),
    "error": (COLORS["danger"], ALPHA["danger_15"], ALPHA["danger_30"]),
}

#: AI relevance class -> colour.
RELEVANCE_PALETTE: Dict[str, str] = {
    "HIGH_RELEVANCE": COLORS["accent_primary"],
    "UNCERTAIN": COLORS["warning"],
    "LOW_RELEVANCE": COLORS["text_muted"],
}


def status_display(status: Any) -> str:
    """Human-readable form of an internal status token."""
    if not status:
        return NOT_AVAILABLE
    return str(status).replace("_", " ").title() if str(status).isupper() else str(status)


def status_palette(status: Any) -> tuple:
    """Look up the (text, background, border) triple for a status token."""
    if not status:
        return STATUS_PALETTE["UNANALYZED"]
    return STATUS_PALETTE.get(str(status), STATUS_PALETTE["UNANALYZED"])


# ====================================================================
# Chips and indicators
# ====================================================================

class StatusChip(QLabel):
    """Small pill used for statuses, health and AI classifications."""

    def __init__(self, text: str = "", status: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("statusChip")
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self._status = status
        self.setText(text or NOT_AVAILABLE)
        self._apply(status)

    def _apply(self, status: str):
        text_color, background, border = status_palette(status)
        self.setStyleSheet(
            "QLabel#statusChip {"
            f"background-color: {background};"
            f"color: {text_color};"
            f"border: 1px solid {border};"
            "border-radius: 10px;"
            "padding: 3px 9px;"
            "font-size: 10px;"
            "font-weight: 600;"
            "}"
        )

    def set_status(self, text: str, status: str = ""):
        self.setText(text or NOT_AVAILABLE)
        if status:
            self._status = status
        self._apply(self._status)


class HealthChip(QLabel):
    """Status chip for component health (ready / warning / error)."""

    def __init__(self, text: str = "Checking...", state: str = "warning", parent=None):
        super().__init__(parent)
        self.setObjectName("statusChip")
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.set_state(text, state)

    def set_state(self, text: str, state: str = "ready"):
        text_color, background, border = HEALTH_PALETTE.get(state, HEALTH_PALETTE["warning"])
        self.setText(text)
        self.setStyleSheet(
            "QLabel#statusChip {"
            f"background-color: {background};"
            f"color: {text_color};"
            f"border: 1px solid {border};"
            "border-radius: 10px;"
            "padding: 3px 9px;"
            "font-size: 10px;"
            "font-weight: 600;"
            "}"
        )


class StatusDot(QWidget):
    """Tiny coloured dot, used next to status text in tables."""

    def __init__(self, color: str = COLORS["text_muted"], parent=None):
        super().__init__(parent)
        self.setFixedSize(8, 8)
        self.set_color(color)

    def set_color(self, color: str):
        self.setStyleSheet(f"background-color: {color}; border-radius: 4px;")


# ====================================================================
# Buttons
# ====================================================================

def make_button(
    text: str,
    on_click: Optional[Callable] = None,
    variant: str = "secondary",
    tooltip: str = "",
    minimum_width: int = 0,
) -> QPushButton:
    """Create a consistently styled button.

    variant: primary | secondary | ghost | danger
    """
    button = QPushButton(text)
    button.setObjectName({
        "primary": "primaryButton",
        "secondary": "secondaryButton",
        "ghost": "ghostButton",
        "danger": "dangerButton",
    }.get(variant, "secondaryButton"))
    button.setCursor(Qt.PointingHandCursor)
    if tooltip:
        button.setToolTip(tooltip)
    if minimum_width:
        button.setMinimumWidth(minimum_width)
    if on_click is not None:
        button.clicked.connect(on_click)
    return button


# ====================================================================
# Layout scaffolding
# ====================================================================

class Page(QWidget):
    """Base page: vertical stack with consistent page margins and spacing.

    Provides three zones so every page shares the same shell:
    header (title + contextual info + actions), body, and optional footer.
    """

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        parent=None,
        margin: int = 24,
        spacing: int = 14,
    ):
        super().__init__(parent)
        self.setObjectName("pageRoot")

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(margin, margin, margin, margin)
        self._root.setSpacing(spacing)

        self.header = PageHeader(title, subtitle)
        self._root.addWidget(self.header)

        self._body = QVBoxLayout()
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.setSpacing(spacing)
        self._root.addLayout(self._body, 1)

    def add_header_widget(self, widget: QWidget):
        """Append a widget to the header's action area."""
        self.header.add_action(widget)

    def set_subtitle(self, text: str):
        self.header.set_subtitle(text)

    def add_widget(self, widget: QWidget, stretch: int = 0):
        self._body.addWidget(widget, stretch)

    def add_layout(self, layout, stretch: int = 0):
        self._body.addLayout(layout, stretch)

    def body_layout(self) -> QVBoxLayout:
        return self._body

    def show_page(self):
        """Called by the shell each time the page becomes visible."""
        self.refresh()

    def refresh(self):
        """Override in subclasses. Called on every page switch."""


class PageHeader(QWidget):
    """Page title, contextual subtitle, and right-aligned action row."""

    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("pageHeader")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(3)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("pageTitle")
        text_column.addWidget(self.title_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("pageSubtitle")
        self.subtitle_label.setWordWrap(False)
        self.subtitle_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        if not subtitle:
            self.subtitle_label.hide()
        text_column.addWidget(self.subtitle_label)

        layout.addLayout(text_column, 1)

        self._actions = QHBoxLayout()
        self._actions.setContentsMargins(0, 0, 0, 0)
        self._actions.setSpacing(8)
        layout.addLayout(self._actions, 0)

    def set_title(self, text: str):
        self.title_label.setText(text)

    def set_subtitle(self, text: str):
        self.subtitle_label.setText(text or "")
        self.subtitle_label.setVisible(bool(text))

    def add_action(self, widget: QWidget):
        self._actions.addWidget(widget)


class Toolbar(QFrame):
    """Horizontal toolbar strip used above tables on most pages."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("toolbar")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(12, 9, 12, 9)
        self._layout.setSpacing(8)

    def add_widget(self, widget: QWidget, stretch: int = 0):
        self._layout.addWidget(widget, stretch)

    def add_layout(self, layout, stretch: int = 0):
        self._layout.addLayout(layout, stretch)

    def add_spacer(self):
        self._layout.addStretch(1)

    def layout_(self) -> QHBoxLayout:
        return self._layout


class SectionCard(QFrame):
    """Titled card. One visual unit instead of nested unrelated cards."""

    def __init__(self, title: str = "", parent=None, padding: int = 16, spacing: int = 12):
        super().__init__(parent)
        self.setObjectName("card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(padding, padding - 2, padding, padding)
        self._layout.setSpacing(spacing)

        self.title_label = None
        if title:
            self.title_label = QLabel(title)
            self.title_label.setObjectName("sectionTitle")
            self._layout.addWidget(self.title_label)

    def set_title(self, title: str):
        if self.title_label is None:
            self.title_label = QLabel(title)
            self.title_label.setObjectName("sectionTitle")
            self._layout.insertWidget(0, self.title_label)
        else:
            self.title_label.setText(title)

    def add_widget(self, widget: QWidget, stretch: int = 0):
        self._layout.addWidget(widget, stretch)

    def add_layout(self, layout, stretch: int = 0):
        self._layout.addLayout(layout, stretch)

    def body_layout(self) -> QVBoxLayout:
        return self._layout


class EmptyState(QWidget):
    """Deliberate empty/loading/failure state. Never leave a page blank."""

    def __init__(self, title: str, hint: str = "", parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 48, 32, 48)
        layout.setSpacing(6)
        layout.addStretch(1)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("emptyStateTitle")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("emptyStateHint")
        self.hint_label.setAlignment(Qt.AlignCenter)
        self.hint_label.setWordWrap(True)
        if hint:
            layout.addWidget(self.hint_label)
        else:
            self.hint_label.hide()

        layout.addStretch(1)

    def set_state(self, title: str, hint: str = ""):
        self.title_label.setText(title)
        self.hint_label.setText(hint or "")
        self.hint_label.setVisible(bool(hint))


class MetricBlock(QFrame):
    """Compact metric: value plus small uppercase caption."""

    def __init__(self, label: str, value: str = "0", hint: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("elevatedPanel")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(64)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        accent = QFrame()
        accent.setObjectName("metricAccent")
        accent.setFixedWidth(2)
        layout.addWidget(accent)

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(1)

        self.value_label = QLabel(value)
        self.value_label.setObjectName("statValue")
        column.addWidget(self.value_label)

        self.label_label = QLabel(label.upper())
        self.label_label.setObjectName("statLabel")
        self.label_label.setWordWrap(False)
        column.addWidget(self.label_label)

        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("pageSubtitle")
        self.hint_label.setVisible(bool(hint))
        column.addWidget(self.hint_label)

        layout.addLayout(column, 1)

    def set_value(self, value, hint: str = ""):
        self.value_label.setText("Not available" if value is None else str(value))
        if hint:
            self.hint_label.setText(hint)
            self.hint_label.setVisible(True)
        else:
            self.hint_label.setVisible(False)

    def set_accent(self, color: str):
        for child in self.findChildren(QFrame):
            if child.objectName() == "metricAccent":
                child.setStyleSheet(f"background-color: {color};")


class StatusStrip(QFrame):
    """Compact horizontal strip of component health indicators."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statusStrip")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(16, 12, 16, 12)
        self._layout.setSpacing(10)
        self._chips: Dict[str, HealthChip] = {}
        self._titles: Dict[str, QLabel] = {}
        self._states: Dict[str, tuple] = {}

    def add_component(self, key: str, title: str):
        container = QWidget()
        column = QVBoxLayout(container)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(3)

        title_label = QLabel(title.upper())
        title_label.setObjectName("statLabel")
        column.addWidget(title_label)

        chip = HealthChip("Checking...", "warning")
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        dot = StatusDot(COLORS["warning"])
        row.addWidget(dot)
        row.addWidget(chip)
        row.addStretch(1)
        column.addLayout(row)

        self._chips[key] = chip
        self._titles[key] = title_label
        chip._dot = dot  # keep a handle so state changes recolour the dot
        self._layout.addWidget(container, 1)

    def set_state(self, key: str, state: str, message: str = ""):
        chip = self._chips.get(key)
        if not chip:
            return
        label = message or state.capitalize()
        chip.set_state(label, state)
        self._states[key] = (state, label)
        color = HEALTH_PALETTE.get(state, HEALTH_PALETTE["warning"])[0]
        dot = getattr(chip, "_dot", None)
        if dot is not None:
            dot.set_color(color)

    def state_for(self, key: str) -> Optional[tuple]:
        """The (state, message) last reported for a component."""
        return self._states.get(key)

    def set_message(self, key: str, message: str):
        chip = self._chips.get(key)
        if chip:
            chip.setText(message)


# ====================================================================
# Detail rows
# ====================================================================

class DetailRow(QFrame):
    """One label/value line. Technical values use the monospace stack."""

    def __init__(
        self,
        label: str,
        value: str = NOT_AVAILABLE,
        mono: bool = False,
        color: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("detailRow")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 7, 0, 7)
        layout.setSpacing(12)

        self.label_label = QLabel(label)
        self.label_label.setObjectName("detailLabel")
        self.label_label.setFixedWidth(120)
        self.label_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        layout.addWidget(self.label_label, 0)

        self.value_label = QLabel(as_text(value))
        self.value_label.setObjectName("monoValue" if mono else "detailValue")
        self.value_label.setWordWrap(True)
        self.value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.value_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.value_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        if color:
            self.value_label.setStyleSheet(f"color: {color}; font-weight: 600;")
        layout.addWidget(self.value_label, 1)

    def set_value(self, value, color: str = ""):
        text = as_text(value)
        self.value_label.setText(text)
        base = f"font-family: {MONO_FONT}; " if self.value_label.objectName() == "monoValue" else ""
        if color:
            self.value_label.setStyleSheet(
                f"{base}color: {color}; font-weight: 600; font-size: 12px;"
            )
        else:
            self.value_label.setStyleSheet(f"{base}color: {COLORS['text_primary']}; font-size: 12px;")

    def set_hidden(self, hidden: bool):
        self.setVisible(not hidden)


class DetailSection(QWidget):
    """Grouped detail rows under a small section label."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)

        if title:
            label = QLabel(title.upper())
            label.setObjectName("sectionLabel")
            self._layout.addSpacing(6)
            self._layout.addWidget(label)
            self._layout.addSpacing(2)

    def add_row(
        self,
        label: str,
        value: str = NOT_AVAILABLE,
        mono: bool = False,
        color: str = "",
    ) -> DetailRow:
        row = DetailRow(label, value, mono=mono, color=color)
        self._layout.addWidget(row)
        return row


class DetailsPanel(QWidget):
    """Scrollable right-hand panel with titled detail sections."""

    def __init__(self, title: str = "Details", parent=None, min_width: int = 300, max_width: int = 420):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.setMinimumWidth(min_width)
        self.setMaximumWidth(max_width)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QFrame()
        header.setObjectName("card")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 11, 14, 11)
        header_layout.setSpacing(8)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("sectionTitle")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch(1)

        self._header_actions = QHBoxLayout()
        self._header_actions.setContentsMargins(0, 0, 0, 0)
        self._header_actions.setSpacing(6)
        header_layout.addLayout(self._header_actions)
        outer.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(14, 12, 14, 14)
        self.content_layout.setSpacing(2)
        scroll.setWidget(self.content)
        outer.addWidget(scroll, 1)

        self._sections: Dict[str, DetailSection] = {}
        self._empty_hint = QLabel("No selection")
        self._empty_hint.setObjectName("emptyStateHint")
        self._empty_hint.setWordWrap(True)
        self.content_layout.addWidget(self._empty_hint)
        self.content_layout.addStretch(1)

    def set_title(self, title: str):
        self.title_label.setText(title)

    def hide_empty_hint(self):
        self._empty_hint.setVisible(False)

    def add_header_action(self, widget: QWidget):
        self._header_actions.addWidget(widget)

    def clear(self, hint: str = "No selection"):
        """Hide every section and show the empty hint.

        Sections are kept (not destroyed) so panels can re-populate the same
        rows without rebuilding widgets on every selection change.
        """
        for section in self._sections.values():
            section.setVisible(False)
        self._empty_hint.setText(hint)
        self._empty_hint.setVisible(True)

    def section(self, name: str, title: str = "") -> DetailSection:
        """Get or create a named section, making it visible."""
        if name in self._sections:
            section = self._sections[name]
            section.setVisible(True)
            return section
        section = DetailSection(title)
        self._sections[name] = section
        # Insert before the trailing stretch so sections stack from the top.
        self.content_layout.insertWidget(self.content_layout.count() - 1, section)
        self._empty_hint.setVisible(False)
        return section

    def hide_section(self, name: str):
        section = self._sections.get(name)
        if section is not None:
            section.setVisible(False)

    def show_section(self, name: str):
        section = self._sections.get(name)
        if section is not None:
            section.setVisible(True)


# ====================================================================
# Tables
# ====================================================================

class ForensicTable(QTableWidget):
    """Standardised table: readable header, hover, selection, no clipping.

    Columns are declared as dicts:
        {"key", "label", "width", "align", "mono", "stretch", "tooltip"}
    """

    ROLE = Qt.UserRole + 1
    RECORD_ROLE = Qt.UserRole + 2

    def __init__(self, columns: List[Dict[str, Any]], parent=None, object_name: str = "dataTable"):
        super().__init__(parent)
        self.setObjectName(object_name)
        self._columns = columns
        self._records: List[Any] = []

        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels([col["label"] for col in columns])

        header = self.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setMinimumSectionSize(60)
        for index, column in enumerate(columns):
            if column.get("stretch"):
                header.setSectionResizeMode(index, QHeaderView.Stretch)
            elif column.get("width"):
                header.setSectionResizeMode(index, QHeaderView.Interactive)
                self.setColumnWidth(index, column["width"])
            else:
                header.setSectionResizeMode(index, QHeaderView.ResizeToContents)

        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(30)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(False)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideMiddle)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)

    # -- data ---------------------------------------------------------
    def set_records(self, records: List[Any]):
        self._records = list(records)
        self.setUpdatesEnabled(False)
        try:
            self.setRowCount(len(self._records))
            for row, record in enumerate(self._records):
                self._populate_row(row, record)
        finally:
            self.setUpdatesEnabled(True)

    def records(self) -> List[Any]:
        return list(self._records)

    def _populate_row(self, row: int, record: Any):
        for index, column in enumerate(self._columns):
            key = column["key"]
            value, kind = self._cell_value(record, column)
            item = QTableWidgetItem("" if value is None else str(value))
            item.setData(self.RECORD_ROLE, record)
            item.setData(self.ROLE, key)
            align = column.get("align") or COLUMN_ALIGN.get(kind, COLUMN_ALIGN["text"])
            item.setTextAlignment(align)
            if column.get("mono") or kind == "mono":
                font = QFont("Consolas")
                font.setPointSize(9)
                item.setFont(font)
            color = self._cell_color(record, column)
            if color:
                item.setForeground(QColor(color))
            tooltip = column.get("tooltip")
            if callable(tooltip):
                tooltip = tooltip(record)
            item.setToolTip(tooltip or ("" if value is None else str(value)))
            self.setItem(row, index, item)

    def _cell_value(self, record: Any, column: Dict[str, Any]) -> tuple:
        getter = column.get("value")
        if callable(getter):
            value, kind = getter(record)
        else:
            value, kind = record.get(column["key"]), column.get("kind", "text")
        if value is None or value == "":
            return NOT_AVAILABLE, kind
        return value, kind

    def _cell_color(self, record: Any, column: Dict[str, Any]) -> str:
        color = column.get("color")
        if callable(color):
            return color(record) or ""
        if column["key"] == "status":
            return status_palette(record.get("status"))[0]
        return color or ""

    # -- selection ----------------------------------------------------
    def current_record(self):
        row = self.currentRow()
        if row < 0 or row >= len(self._records):
            return None
        return self._records[row]

    def select_first(self):
        if self.rowCount() > 0:
            self.selectRow(0)

    def apply_filter(self, predicate: Callable[[Any], bool]):
        """Hide rows that do not satisfy the predicate."""
        for row, record in enumerate(self._records):
            self.setRowHidden(row, not predicate(record))

    def search_text(self, record: Any) -> str:
        parts = []
        for value in record.values():
            if isinstance(value, (str, int, float)):
                parts.append(str(value))
        return " ".join(parts).lower()

    def apply_search(self, text: str):
        needle = (text or "").strip().lower()
        for row, record in enumerate(self._records):
            self.setRowHidden(row, bool(needle) and needle not in self.search_text(record))
