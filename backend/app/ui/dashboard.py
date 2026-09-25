"""
ReConstructAI - Dashboard Page
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QSizePolicy, QSpacerItem
)
from PySide6.QtCore import Qt, Signal


class DashboardPage(QWidget):
    """Main dashboard with empty state and quick actions."""
    
    create_case_requested = Signal()
    open_case_requested = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)
        
        # Hero section
        hero = QFrame()
        hero.setObjectName("card")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(40, 40, 40, 40)
        hero_layout.setSpacing(16)
        
        title = QLabel("ReConstructAI")
        title.setObjectName("titleLabel")
        hero_layout.addWidget(title, alignment=Qt.AlignCenter)
        
        subtitle = QLabel("Recover. Reconstruct. Understand.")
        subtitle.setObjectName("subtitleLabel")
        subtitle.setStyleSheet("font-size: 16px;")
        hero_layout.addWidget(subtitle, alignment=Qt.AlignCenter)
        
        description = QLabel(
            "AI-assisted digital evidence recovery and reconstruction workspace.\n"
            "Create a new case or open an existing one to begin investigation."
        )
        description.setObjectName("bodyLabel")
        description.setAlignment(Qt.AlignCenter)
        description.setWordWrap(True)
        description.setStyleSheet("line-height: 1.6; margin-top: 8px;")
        hero_layout.addWidget(description)
        
        # Action buttons
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(16)
        actions_layout.addStretch()
        
        create_btn = QPushButton("Create New Case")
        create_btn.setObjectName("primaryButton")
        create_btn.setCursor(Qt.PointingHandCursor)
        create_btn.setMinimumWidth(180)
        create_btn.clicked.connect(self.create_case_requested.emit)
        actions_layout.addWidget(create_btn)
        
        open_btn = QPushButton("Open Case")
        open_btn.setObjectName("secondaryButton")
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.setMinimumWidth(180)
        open_btn.clicked.connect(self.open_case_requested.emit)
        actions_layout.addWidget(open_btn)
        
        actions_layout.addStretch()
        hero_layout.addLayout(actions_layout)
        
        layout.addWidget(hero)
        
        # System status section
        status_section = QFrame()
        status_section.setObjectName("card")
        status_layout = QVBoxLayout(status_section)
        status_layout.setContentsMargins(24, 20, 24, 20)
        status_layout.setSpacing(16)
        
        status_title = QLabel("System Status")
        status_title.setObjectName("sectionTitle")
        status_layout.addWidget(status_title)
        
        # Status grid
        grid_layout = QHBoxLayout()
        grid_layout.setSpacing(16)
        
        self._status_cards = {}
        for key, label, initial_status, initial_msg in [
            ("engine", "Core Engine", "ready", "Ready"),
            ("database", "Database", "ready", "Connected"),
            ("storage", "Local Storage", "ready", "Ready"),
        ]:
            card = QFrame()
            card.setObjectName("elevatedPanel")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(20, 16, 20, 16)
            card_layout.setSpacing(8)
            
            lbl = QLabel(label)
            lbl.setObjectName("mutedLabel")
            lbl.setStyleSheet("font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;")
            card_layout.addWidget(lbl)
            
            status = QLabel(initial_msg)
            status.setObjectName("statusBadge")
            status.setProperty("status", initial_status)
            status.setStyleSheet(status.styleSheet())
            card_layout.addWidget(status, alignment=Qt.AlignLeft)
            
            self._status_cards[key] = status
            grid_layout.addWidget(card)
        
        status_layout.addLayout(grid_layout)
        layout.addWidget(status_section)
        
        layout.addStretch()
    
    def update_status(self, component: str, status: str, message: str = ""):
        """Update a system status badge."""
        if component in self._status_cards:
            label = self._status_cards[component]
            label.setText(message or status)
            label.setProperty("status", status)
            label.style().unpolish(label)
            label.style().polish(label)