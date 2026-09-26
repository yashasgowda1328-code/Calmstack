"""
ReConstructAI - Visual Design System

Obsidian + Emerald + Warm Ivory theme.

The palette is intentionally narrow: no blue, no neon, minimal gradients.
Colour carries meaning only (status, warning, danger, active navigation).
"""

COLORS = {
    "bg_main": "#0D0D0D",
    "bg_sidebar": "#151515",
    "bg_card": "#1B1B1B",
    "bg_elevated": "#222222",
    "bg_hover": "#262626",
    "border": "#303030",
    "border_strong": "#3A3A3A",
    "accent_primary": "#22C55E",
    "accent_primary_hover": "#1EB050",
    "accent_primary_press": "#16A34A",
    "accent_secondary": "#14B8A6",
    "text_primary": "#F5F5F0",
    "text_secondary": "#A3A3A3",
    "text_muted": "#737373",
    "warning": "#F59E0B",
    "danger": "#EF4444",
}

# Translucent variants derived from the palette above (rgba strings).
ALPHA = {
    "accent_primary_10": "rgba(34, 197, 94, 0.10)",
    "accent_primary_15": "rgba(34, 197, 94, 0.15)",
    "accent_primary_30": "rgba(34, 197, 94, 0.30)",
    "accent_secondary_15": "rgba(20, 184, 166, 0.15)",
    "warning_15": "rgba(245, 158, 11, 0.15)",
    "warning_30": "rgba(245, 158, 11, 0.30)",
    "danger_15": "rgba(239, 68, 68, 0.15)",
    "danger_30": "rgba(239, 68, 68, 0.30)",
}

# Component health states (Core Engine, Database, Recovery Engine, Storage).
# Each value is a (text colour, chip background, chip border) triple, matching
# the shape the status chips and indicator dots consume.
HEALTH_PALETTE = {
    "ready": (COLORS["accent_primary"], ALPHA["accent_primary_15"], ALPHA["accent_primary_30"]),
    "warning": (COLORS["warning"], ALPHA["warning_15"], ALPHA["warning_30"]),
    "error": (COLORS["danger"], ALPHA["danger_15"], ALPHA["danger_30"]),
}

# Monospace stack for technical values (hashes, offsets, sizes).
MONO_FONT = "'Consolas', 'Cascadia Mono', 'DejaVu Sans Mono', monospace"


def build_stylesheet() -> str:
    """Build the application-wide Qt stylesheet from the palette."""

    c = COLORS
    a = ALPHA

    return f"""
/* ------------------------------------------------------------------ */
/* Base                                                                */
/* ------------------------------------------------------------------ */
QWidget {{
    background-color: {c['bg_main']};
    color: {c['text_primary']};
    font-family: "Segoe UI", "Inter", system-ui, sans-serif;
    font-size: 13px;
}}

QMainWindow, QDialog {{
    background-color: {c['bg_main']};
}}

QToolTip {{
    background-color: {c['bg_elevated']};
    color: {c['text_primary']};
    border: 1px solid {c['border_strong']};
    padding: 6px 8px;
    font-size: 12px;
}}

/* ------------------------------------------------------------------ */
/* Application shell                                                   */
/* ------------------------------------------------------------------ */
QWidget#sidebar {{
    background-color: {c['bg_sidebar']};
    border-right: 1px solid {c['border']};
}}

QWidget#contentArea {{
    background-color: {c['bg_main']};
}}

QWidget#pageRoot {{
    background-color: {c['bg_main']};
}}

QWidget#pageHeader {{
    background-color: transparent;
    border: none;
}}

QSplitter::handle {{
    background-color: {c['border']};
}}
QSplitter::handle:horizontal {{
    width: 1px;
}}
QSplitter::handle:vertical {{
    height: 1px;
}}
QSplitter::handle:hover {{
    background-color: {c['border_strong']};
}}

/* ------------------------------------------------------------------ */
/* Sidebar navigation                                                  */
/* ------------------------------------------------------------------ */
QLabel#brandTitle {{
    font-size: 17px;
    font-weight: 600;
    color: {c['text_primary']};
    letter-spacing: 0.2px;
}}

QLabel#navGroupLabel {{
    font-size: 10px;
    font-weight: 600;
    color: {c['text_muted']};
    letter-spacing: 1.0px;
    padding: 14px 10px 4px 10px;
    background: transparent;
}}

QPushButton#navButton {{
    background-color: transparent;
    color: {c['text_secondary']};
    border: none;
    border-left: 2px solid transparent;
    border-radius: 6px;
    padding: 9px 10px;
    text-align: left;
    font-size: 13px;
    font-weight: 500;
}}
QPushButton#navButton:hover {{
    background-color: {c['bg_hover']};
    color: {c['text_primary']};
    border-left: 2px solid {c['border_strong']};
}}
QPushButton#navButton:checked {{
    background-color: {c['bg_card']};
    color: {c['text_primary']};
    border-left: 2px solid {c['accent_primary']};
    font-weight: 600;
}}

QFrame#navSeparator {{
    background-color: {c['border']};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}

/* ------------------------------------------------------------------ */
/* Cards, panels, sections                                             */
/* ------------------------------------------------------------------ */
QFrame#card {{
    background-color: {c['bg_card']};
    border: 1px solid {c['border']};
    border-radius: 10px;
}}

QFrame#elevatedPanel {{
    background-color: {c['bg_elevated']};
    border: 1px solid {c['border']};
    border-radius: 8px;
}}

QFrame#toolbar {{
    background-color: {c['bg_card']};
    border: 1px solid {c['border']};
    border-radius: 10px;
}}

QFrame#detailRow {{
    background-color: transparent;
    border: none;
    border-bottom: 1px solid {c['border']};
}}

QFrame#statusStrip {{
    background-color: {c['bg_card']};
    border: 1px solid {c['border']};
    border-radius: 10px;
}}

/* ------------------------------------------------------------------ */
/* Typography                                                          */
/* ------------------------------------------------------------------ */
QLabel#pageTitle {{
    font-size: 21px;
    font-weight: 600;
    color: {c['text_primary']};
}}

QLabel#pageSubtitle {{
    font-size: 12px;
    font-weight: 400;
    color: {c['text_muted']};
}}

QLabel#sectionTitle {{
    font-size: 14px;
    font-weight: 600;
    color: {c['text_primary']};
}}

QLabel#sectionLabel {{
    font-size: 10px;
    font-weight: 600;
    color: {c['text_muted']};
    letter-spacing: 0.8px;
}}

QLabel#detailLabel {{
    font-size: 11px;
    font-weight: 600;
    color: {c['text_muted']};
    letter-spacing: 0.4px;
    background: transparent;
}}

QLabel#detailValue {{
    font-size: 12px;
    color: {c['text_primary']};
    background: transparent;
}}

QLabel#bodyLabel {{
    font-size: 13px;
    color: {c['text_secondary']};
    background: transparent;
}}

QLabel#mutedLabel {{
    font-size: 12px;
    color: {c['text_muted']};
    background: transparent;
}}

QLabel#monoValue {{
    font-family: {MONO_FONT};
    font-size: 12px;
    color: {c['text_primary']};
    background: transparent;
}}

QLabel#statValue {{
    font-size: 22px;
    font-weight: 600;
    color: {c['text_primary']};
    background: transparent;
}}

QLabel#statLabel {{
    font-size: 10px;
    font-weight: 600;
    color: {c['text_muted']};
    letter-spacing: 0.8px;
    background: transparent;
}}

QLabel#metricAccent {{
    background-color: {c['accent_primary']};
    border: none;
    max-width: 2px;
    min-width: 2px;
}}

/* Empty / loading / error states */
QLabel#emptyStateTitle {{
    font-size: 14px;
    font-weight: 600;
    color: {c['text_secondary']};
    background: transparent;
}}

QLabel#emptyStateHint {{
    font-size: 12px;
    color: {c['text_muted']};
    background: transparent;
}}

/* ------------------------------------------------------------------ */
/* Buttons                                                             */
/* ------------------------------------------------------------------ */
QPushButton {{
    background-color: {c['bg_elevated']};
    color: {c['text_primary']};
    border: 1px solid {c['border']};
    border-radius: 7px;
    padding: 7px 14px;
    font-size: 12px;
    font-weight: 500;
    min-height: 18px;
}}
QPushButton:hover {{
    background-color: {c['bg_hover']};
    border-color: {c['border_strong']};
}}
QPushButton:pressed {{
    background-color: {c['bg_card']};
}}
QPushButton:disabled {{
    background-color: {c['bg_card']};
    color: {c['text_muted']};
    border-color: {c['border']};
}}

QPushButton#primaryButton {{
    background-color: {c['accent_primary']};
    color: {c['bg_main']};
    border: 1px solid {c['accent_primary']};
    font-weight: 600;
}}
QPushButton#primaryButton:hover {{
    background-color: {c['accent_primary_hover']};
    border-color: {c['accent_primary_hover']};
}}
QPushButton#primaryButton:pressed {{
    background-color: {c['accent_primary_press']};
}}
QPushButton#primaryButton:disabled {{
    background-color: {c['bg_elevated']};
    color: {c['text_muted']};
    border-color: {c['border']};
}}

QPushButton#secondaryButton {{
    background-color: {c['bg_elevated']};
    color: {c['text_primary']};
    border: 1px solid {c['border']};
}}
QPushButton#secondaryButton:hover {{
    background-color: {c['bg_hover']};
    border-color: {c['border_strong']};
}}
QPushButton#secondaryButton:disabled {{
    background-color: {c['bg_card']};
    color: {c['text_muted']};
}}

QPushButton#ghostButton {{
    background-color: transparent;
    color: {c['accent_primary']};
    border: 1px solid transparent;
    font-weight: 500;
}}
QPushButton#ghostButton:hover {{
    background-color: {a['accent_primary_10']};
    border-color: {a['accent_primary_30']};
}}
QPushButton#ghostButton:disabled {{
    color: {c['text_muted']};
    background: transparent;
    border-color: transparent;
}}

QPushButton#dangerButton {{
    background-color: transparent;
    color: {c['danger']};
    border: 1px solid {a['danger_30']};
    font-weight: 500;
}}
QPushButton#dangerButton:hover {{
    background-color: {a['danger_15']};
}}

QPushButton#navButton:disabled {{
    color: {c['text_muted']};
}}

/* Dialog button boxes */
QDialogButtonBox QPushButton {{
    min-width: 88px;
    padding: 7px 16px;
}}

/* ------------------------------------------------------------------ */
/* Inputs                                                              */
/* ------------------------------------------------------------------ */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {c['bg_elevated']};
    color: {c['text_primary']};
    border: 1px solid {c['border']};
    border-radius: 7px;
    padding: 7px 10px;
    font-size: 12px;
    selection-background-color: {a['accent_primary_30']};
    selection-color: {c['text_primary']};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {c['accent_primary']};
}}
QLineEdit::placeholder {{
    color: {c['text_muted']};
}}
QLineEdit:disabled {{
    background-color: {c['bg_card']};
    color: {c['text_muted']};
}}

QComboBox {{
    background-color: {c['bg_elevated']};
    color: {c['text_primary']};
    border: 1px solid {c['border']};
    border-radius: 7px;
    padding: 6px 10px;
    font-size: 12px;
    min-height: 18px;
}}
QComboBox:hover {{
    border-color: {c['border_strong']};
}}
QComboBox:focus {{
    border-color: {c['accent_primary']};
}}
QComboBox:disabled {{
    background-color: {c['bg_card']};
    color: {c['text_muted']};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {c['text_secondary']};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {c['bg_card']};
    color: {c['text_primary']};
    border: 1px solid {c['border_strong']};
    selection-background-color: {a['accent_primary_15']};
    selection-color: {c['text_primary']};
    outline: none;
    padding: 4px;
}}

/* ------------------------------------------------------------------ */
/* Tables                                                              */
/* ------------------------------------------------------------------ */
QTableWidget, QTableView, QTreeWidget, QTreeView {{
    background-color: {c['bg_card']};
    alternate-background-color: {c['bg_card']};
    color: {c['text_primary']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    gridline-color: transparent;
    font-size: 12px;
    selection-background-color: {a['accent_primary_15']};
    selection-color: {c['text_primary']};
    outline: none;
}}
QTableWidget::item, QTreeWidget::item {{
    padding: 6px 8px;
    border: none;
    border-bottom: 1px solid {c['border']};
    color: {c['text_primary']};
}}
QTableWidget::item:hover, QTreeWidget::item:hover {{
    background-color: {c['bg_hover']};
}}
QTableWidget::item:selected, QTreeWidget::item:selected {{
    background-color: {a['accent_primary_15']};
    color: {c['text_primary']};
}}
QTableWidget::item:focus, QTreeWidget::item:focus {{
    outline: none;
}}

QHeaderView {{
    background-color: {c['bg_elevated']};
}}
QHeaderView::section {{
    background-color: {c['bg_elevated']};
    color: {c['text_secondary']};
    border: none;
    border-bottom: 1px solid {c['border']};
    border-right: 1px solid {c['border']};
    padding: 8px 8px;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.6px;
}}
QHeaderView::section:last {{
    border-right: none;
}}
QHeaderView::section:hover {{
    background-color: {c['bg_hover']};
}}
QTableCornerButton::section {{
    background-color: {c['bg_elevated']};
    border: none;
    border-bottom: 1px solid {c['border']};
}}

/* Compact tables carry slightly denser rows */
QTableWidget#compactTable::item {{
    padding: 5px 8px;
}}
QTableWidget#compactTable::item:selected {{
    background-color: {a['accent_primary_15']};
}}

/* ------------------------------------------------------------------ */
/* Scroll areas and scrollbars                                         */
/* ------------------------------------------------------------------ */
QScrollArea {{
    border: none;
    background-color: transparent;
}}
QScrollArea > QWidget > QWidget {{
    background-color: transparent;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {c['border']};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {c['border_strong']};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {c['border']};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {c['border_strong']};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0;
    height: 0;
    border: none;
    background: transparent;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* ------------------------------------------------------------------ */
/* Progress                                                            */
/* ------------------------------------------------------------------ */
QProgressBar {{
    background-color: {c['bg_elevated']};
    border: 1px solid {c['border']};
    border-radius: 6px;
    height: 8px;
    max-height: 8px;
    min-height: 8px;
    text-align: center;
    color: {c['text_secondary']};
    font-size: 10px;
}}
QProgressBar::chunk {{
    background-color: {c['accent_primary']};
    border-radius: 5px;
}}
QProgressBar#indeterminateBar {{
    border: none;
    background-color: {c['bg_elevated']};
    border-radius: 4px;
    height: 4px;
    max-height: 4px;
    min-height: 4px;
}}

/* ------------------------------------------------------------------ */
/* Status chips                                                        */
/* ------------------------------------------------------------------ */
QLabel#statusChip {{
    border-radius: 10px;
    padding: 3px 9px;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.3px;
    background: {c['bg_elevated']};
    color: {c['text_secondary']};
    border: 1px solid {c['border']};
}}

QLabel#statusDot {{
    border-radius: 4px;
    min-width: 8px;
    max-width: 8px;
    min-height: 8px;
    max-height: 8px;
    background: {c['text_muted']};
}}

/* ------------------------------------------------------------------ */
/* Group boxes / separators                                            */
/* ------------------------------------------------------------------ */
QGroupBox {{
    color: {c['text_primary']};
    font-size: 12px;
    font-weight: 600;
    border: 1px solid {c['border']};
    border-radius: 8px;
    margin-top: 14px;
    padding: 10px 12px 12px 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {c['text_muted']};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.8px;
}}

QFrame#separator {{
    background-color: {c['border']};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}
QFrame#vSeparator {{
    background-color: {c['border']};
    max-width: 1px;
    min-width: 1px;
    border: none;
}}

/* Checkbox / radio */
QCheckBox, QRadioButton {{
    color: {c['text_secondary']};
    font-size: 12px;
    spacing: 8px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {c['border_strong']};
    background: {c['bg_elevated']};
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {c['accent_primary']};
    border: 1px solid {c['accent_primary']};
}}

/* Menu (used for context actions) */
QMenu {{
    background-color: {c['bg_elevated']};
    border: 1px solid {c['border_strong']};
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 20px 6px 10px;
    color: {c['text_secondary']};
    font-size: 12px;
}}
QMenu::item:selected {{
    background-color: {a['accent_primary_15']};
    color: {c['text_primary']};
}}
QMenu::separator {{
    height: 1px;
    background: {c['border']};
    margin: 4px 6px;
}}
"""


STYLESHEET = build_stylesheet()


def apply_stylesheet(app):
    """Apply the global stylesheet to the application."""
    app.setStyleSheet(build_stylesheet())
