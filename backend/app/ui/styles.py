"""
ReConstructAI - Visual Design System
Obsidian + Emerald + Warm Ivory Theme
"""

COLORS = {
    "bg_main": "#0D0D0D",
    "bg_sidebar": "#151515",
    "bg_card": "#1B1B1B",
    "bg_elevated": "#222222",
    "border": "#303030",
    "accent_primary": "#22C55E",
    "accent_secondary": "#14B8A6",
    "text_primary": "#F5F5F0",
    "text_secondary": "#A3A3A3",
    "text_muted": "#737373",
    "warning": "#F59E0B",
    "danger": "#EF4444",
}

STYLESHEET = f"""
/* Main Window */
QMainWindow {{
    background-color: {COLORS["bg_main"]};
    color: {COLORS["text_primary"]};
    font-family: "Segoe UI", "Inter", system-ui, sans-serif;
    font-size: 13px;
}}

/* Sidebar */
QWidget#sidebar {{
    background-color: {COLORS["bg_sidebar"]};
    border-right: 1px solid {COLORS["border"]};
}}

/* Navigation Buttons */
QPushButton#navButton {{
    background-color: transparent;
    color: {COLORS["text_secondary"]};
    border: none;
    border-radius: 8px;
    padding: 12px 16px;
    text-align: left;
    font-size: 13px;
    font-weight: 500;
}}
QPushButton#navButton:hover {{
    background-color: {COLORS["bg_elevated"]};
    color: {COLORS["text_primary"]};
}}
QPushButton#navButton:checked {{
    background-color: {COLORS["bg_card"]};
    color: {COLORS["accent_primary"]};
    border-left: 3px solid {COLORS["accent_primary"]};
}}

/* Content Area */
QWidget#contentArea {{
    background-color: {COLORS["bg_main"]};
}}

/* Cards */
QFrame#card {{
    background-color: {COLORS["bg_card"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 12px;
}}
QFrame#card:hover {{
    border-color: #3A3A3A;
}}

/* Elevated Panels */
QFrame#elevatedPanel {{
    background-color: {COLORS["bg_elevated"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 10px;
}}

/* Labels */
QLabel#titleLabel {{
    font-size: 28px;
    font-weight: 600;
    color: {COLORS["text_primary"]};
    letter-spacing: -0.5px;
}}
QLabel#subtitleLabel {{
    font-size: 15px;
    font-weight: 400;
    color: {COLORS["text_secondary"]};
}}
QLabel#sectionTitle {{
    font-size: 16px;
    font-weight: 600;
    color: {COLORS["text_primary"]};
}}
QLabel#bodyLabel {{
    font-size: 13px;
    color: {COLORS["text_secondary"]};
}}
QLabel#mutedLabel {{
    font-size: 12px;
    color: {COLORS["text_muted"]};
}}
QLabel#statValue {{
    font-size: 24px;
    font-weight: 600;
    color: {COLORS["text_primary"]};
}}
QLabel#statLabel {{
    font-size: 12px;
    color: {COLORS["text_muted"]};
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

/* Buttons */
QPushButton#primaryButton {{
    background-color: {COLORS["accent_primary"]};
    color: {COLORS["bg_main"]};
    border: none;
    border-radius: 8px;
    padding: 10px 20px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#primaryButton:hover {{
    background-color: #1EB050;
}}
QPushButton#primaryButton:pressed {{
    background-color: #16A34A;
}}
QPushButton#primaryButton:disabled {{
    background-color: {COLORS["border"]};
    color: {COLORS["text_muted"]};
}}

QPushButton#secondaryButton {{
    background-color: {COLORS["bg_elevated"]};
    color: {COLORS["text_primary"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    padding: 10px 20px;
    font-size: 13px;
    font-weight: 500;
}}
QPushButton#secondaryButton:hover {{
    background-color: {COLORS["bg_card"]};
    border-color: #3A3A3A;
}}

QPushButton#ghostButton {{
    background-color: transparent;
    color: {COLORS["accent_primary"]};
    border: none;
    border-radius: 8px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
}}
QPushButton#ghostButton:hover {{
    background-color: rgba(34, 197, 94, 0.1);
}}

/* Line Edit */
QLineEdit {{
    background-color: {COLORS["bg_elevated"]};
    color: {COLORS["text_primary"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 13px;
    selection-background-color: {COLORS["accent_primary"]};
}}
QLineEdit:focus {{
    border-color: {COLORS["accent_primary"]};
}}
QLineEdit::placeholder {{
    color: {COLORS["text_muted"]};
}}

/* Text Edit */
QTextEdit {{
    background-color: {COLORS["bg_elevated"]};
    color: {COLORS["text_primary"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 13px;
}}
QTextEdit:focus {{
    border-color: {COLORS["accent_primary"]};
}}

/* Table */
QTableWidget {{
    background-color: {COLORS["bg_card"]};
    color: {COLORS["text_primary"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    gridline-color: {COLORS["border"]};
    font-size: 12px;
    selection-background-color: rgba(34, 197, 94, 0.15);
    selection-color: {COLORS["text_primary"]};
}}
QTableWidget::item {{
    padding: 10px 12px;
    border-bottom: 1px solid {COLORS["border"]};
}}
QTableWidget::item:selected {{
    background-color: rgba(34, 197, 94, 0.15);
}}
QHeaderView::section {{
    background-color: {COLORS["bg_elevated"]};
    color: {COLORS["text_secondary"]};
    border: none;
    border-bottom: 1px solid {COLORS["border"]};
    padding: 10px 12px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

/* Scrollbar */
QScrollBar:vertical {{
    background-color: {COLORS["bg_main"]};
    width: 8px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background-color: {COLORS["border"]};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: #3A3A3A;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

/* Combo Box */
QComboBox {{
    background-color: {COLORS["bg_elevated"]};
    color: {COLORS["text_primary"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
}}
QComboBox:hover {{
    border-color: #3A3A3A;
}}
QComboBox:focus {{
    border-color: {COLORS["accent_primary"]};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {COLORS["text_secondary"]};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {COLORS["bg_card"]};
    color: {COLORS["text_primary"]};
    border: 1px solid {COLORS["border"]};
    selection-background-color: rgba(34, 197, 94, 0.15);
    outline: none;
}}

/* Status Badges */
QLabel#statusBadge {{
    background-color: {COLORS["bg_elevated"]};
    color: {COLORS["text_secondary"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 12px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel#statusBadge[status="ready"] {{
    background-color: rgba(34, 197, 94, 0.15);
    color: {COLORS["accent_primary"]};
    border-color: rgba(34, 197, 94, 0.3);
}}
QLabel#statusBadge[status="warning"] {{
    background-color: rgba(245, 158, 11, 0.15);
    color: {COLORS["warning"]};
    border-color: rgba(245, 158, 11, 0.3);
}}
QLabel#statusBadge[status="error"] {{
    background-color: rgba(239, 68, 68, 0.15);
    color: {COLORS["danger"]};
    border-color: rgba(239, 68, 68, 0.3);
}}

/* Dialog */
QDialog {{
    background-color: {COLORS["bg_main"]};
    color: {COLORS["text_primary"]};
}}
QDialog QLabel {{
    color: {COLORS["text_primary"]};
}}
QDialog QPushButton {{
    min-width: 80px;
}}

/* Separator */
QFrame#separator {{
    background-color: {COLORS["border"]};
    max-height: 1px;
    min-height: 1px;
}}

/* Group Box */
QGroupBox {{
    color: {COLORS["text_primary"]};
    font-size: 13px;
    font-weight: 500;
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    margin-top: 16px;
    padding-top: 16px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 8px;
    color: {COLORS["text_secondary"]};
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
"""

def apply_stylesheet(app):
    """Apply the global stylesheet to the application."""
    app.setStyleSheet(STYLESHEET)