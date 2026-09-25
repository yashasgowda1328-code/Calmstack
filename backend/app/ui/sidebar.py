"""
ReConstructAI - Sidebar Navigation Component
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QFrame,
    QSizePolicy, QButtonGroup
)
from PySide6.QtCore import Qt, Signal


class NavButton(QPushButton):
    """Navigation button with checkable state."""
    
    def __init__(self, text: str, icon_text: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("navButton")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(48)
        
        # Combine icon and text
        if icon_text:
            self.setText(f"  {icon_text}  {text}")
        else:
            self.setText(f"  {text}")


class Sidebar(QWidget):
    """Left sidebar navigation."""
    
    navigation_changed = Signal(str)  # Emits page name
    
    NAV_ITEMS = [
        ("evidence", "Evidence", "📁"),
        ("all_files", "All Files", "📄"),
        ("healthy", "Healthy", "✅"),
        ("suspicious", "Suspicious", "⚠️"),
        ("corrupted", "Corrupted", "❌"),
        ("fragments", "Fragments", "🧩"),
        ("recovered", "Recovered", "🔧"),
        ("deleted_recovery", "Deleted Data Recovery", "🗑️"),
        ("reports", "Reports", "📋"),
    ]
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(240)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        
        self._buttons = {}
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 20)
        layout.setSpacing(8)
        
        # App title in sidebar
        title = QLabel("ReConstructAI")
        title.setObjectName("titleLabel")
        title.setStyleSheet("font-size: 18px; padding: 0 8px 16px 8px;")
        layout.addWidget(title)
        
        subtitle = QLabel("Recover. Reconstruct. Understand.")
        subtitle.setObjectName("mutedLabel")
        subtitle.setStyleSheet("padding: 0 8px 24px 8px;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        
        # Separator
        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)
        
        # Navigation buttons
        for page_id, label, icon in self.NAV_ITEMS:
            btn = NavButton(label, icon)
            btn.clicked.connect(lambda checked, pid=page_id: self._on_nav_clicked(pid))
            self._button_group.addButton(btn)
            self._buttons[page_id] = btn
            layout.addWidget(btn)
        
        # Select first by default
        self._buttons["evidence"].setChecked(True)
        
        layout.addStretch()
        
        # System status at bottom
        status_frame = QFrame()
        status_frame.setObjectName("elevatedPanel")
        status_layout = QVBoxLayout(status_frame)
        status_layout.setContentsMargins(12, 10, 12, 10)
        status_layout.setSpacing(6)
        
        status_title = QLabel("System Status")
        status_title.setObjectName("mutedLabel")
        status_layout.addWidget(status_title)
        
        self._status_labels = {}
        for key, label in [
            ("engine", "Core Engine"),
            ("database", "Database"),
            ("storage", "Local Storage"),
        ]:
            row = QWidget()
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(2)
            
            lbl = QLabel(label)
            lbl.setObjectName("mutedLabel")
            lbl.setStyleSheet("font-size: 11px;")
            row_layout.addWidget(lbl)
            
            status = QLabel("Checking...")
            status.setObjectName("statusBadge")
            status.setProperty("status", "warning")
            status.setStyleSheet(status.styleSheet())
            row_layout.addWidget(status)
            
            self._status_labels[key] = status
            status_layout.addWidget(row)
        
        layout.addWidget(status_frame)
    
    def _on_nav_clicked(self, page_id: str):
        self.navigation_changed.emit(page_id)
    
    def set_page(self, page_id: str):
        """Programmatically set the active page."""
        if page_id in self._buttons:
            self._buttons[page_id].setChecked(True)
    
    def update_status(self, component: str, status: str, message: str = ""):
        """Update system status badge."""
        if component in self._status_labels:
            label = self._status_labels[component]
            label.setText(message or status)
            label.setProperty("status", status)
            label.style().unpolish(label)
            label.style().polish(label)