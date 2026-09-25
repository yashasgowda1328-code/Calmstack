"""
ReConstructAI - Cases Page
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QDialog, QFormLayout, QTextEdit, QDialogButtonBox,
    QMessageBox, QAbstractItemView, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from datetime import datetime
import uuid

# Import existing database functions
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.storage.database import (
    initialize_database, create_case, list_cases, get_case
)


class CreateCaseDialog(QDialog):
    """Dialog for creating a new case."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create New Case")
        self.setMinimumWidth(480)
        self.setModal(True)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        title = QLabel("Create New Case")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        
        form = QFormLayout()
        form.setSpacing(16)
        form.setLabelAlignment(Qt.AlignLeft)
        
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter case name")
        self.name_edit.setMinimumHeight(40)
        form.addRow("Case Name *", self.name_edit)
        
        self.desc_edit = QTextEdit()
        self.desc_edit.setPlaceholderText("Optional description...")
        self.desc_edit.setMaximumHeight(100)
        form.addRow("Description", self.desc_edit)
        
        layout.addLayout(form)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.setObjectName("dialogButtons")
        ok_btn = button_box.button(QDialogButtonBox.Ok)
        ok_btn.setObjectName("primaryButton")
        ok_btn.setText("Create Case")
        cancel_btn = button_box.button(QDialogButtonBox.Cancel)
        cancel_btn.setObjectName("secondaryButton")
        
        button_box.accepted.connect(self._validate_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _validate_and_accept(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Validation Error", "Case name is required.")
            return
        self.accept()
    
    def get_case_data(self):
        return {
            "name": self.name_edit.text().strip(),
            "description": self.desc_edit.toPlainText().strip()
        }


class CasesPage(QWidget):
    """Cases management page."""
    
    case_selected = Signal(str)  # Emits case_id
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._cases = []
        self._selected_case_id = None
        self._setup_ui()
        self._load_cases()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(20)
        
        # Header with actions
        header_layout = QHBoxLayout()
        header_layout.setSpacing(16)
        
        title = QLabel("Cases")
        title.setObjectName("titleLabel")
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("secondaryButton")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.clicked.connect(self._load_cases)
        header_layout.addWidget(refresh_btn)
        
        create_btn = QPushButton("Create New Case")
        create_btn.setObjectName("primaryButton")
        create_btn.setCursor(Qt.PointingHandCursor)
        create_btn.clicked.connect(self._create_case)
        header_layout.addWidget(create_btn)
        
        layout.addLayout(header_layout)
        
        # Cases table
        self.table = QTableWidget()
        self.table.setObjectName("casesTable")
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Case ID", "Name", "Description", "Created", "Actions"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        layout.addWidget(self.table)
        
        # Empty state
        self.empty_label = QLabel("No cases yet. Create your first case to begin.")
        self.empty_label.setObjectName("bodyLabel")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("color: #737373; padding: 60px;")
        self.empty_label.hide()
        layout.addWidget(self.empty_label)
    
    def _load_cases(self):
        """Load cases from database."""
        try:
            self._cases = list_cases()
            self._populate_table()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load cases: {str(e)}")
    
    def _populate_table(self):
        self.table.setRowCount(len(self._cases))
        
        if len(self._cases) == 0:
            self.table.hide()
            self.empty_label.show()
            return
        
        self.table.show()
        self.empty_label.hide()
        
        for row, case in enumerate(self._cases):
            case_id = case.get('case_id', '')
            name = case.get('name', '')
            description = case.get('description', '') or '—'
            created_at = case.get('created_at', '')
            
            # Format date
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    created_str = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    created_str = created_at[:16] if len(created_at) >= 16 else created_at
            else:
                created_str = "—"
            
            # Case ID (truncated for display)
            id_item = QTableWidgetItem(case_id[:8] + "..." if len(case_id) > 8 else case_id)
            id_item.setData(Qt.UserRole, case_id)
            id_item.setToolTip(case_id)
            self.table.setItem(row, 0, id_item)
            
            self.table.setItem(row, 1, QTableWidgetItem(name))
            self.table.setItem(row, 2, QTableWidgetItem(description))
            self.table.setItem(row, 3, QTableWidgetItem(created_str))
            
            # Select button
            select_btn = QPushButton("Select")
            select_btn.setObjectName("ghostButton")
            select_btn.setCursor(Qt.PointingHandCursor)
            select_btn.setProperty("case_id", case_id)
            select_btn.clicked.connect(lambda checked, cid=case_id: self._on_select_case(cid))
            
            # Store in a container widget
            btn_container = QWidget()
            btn_layout = QHBoxLayout(btn_container)
            btn_layout.setContentsMargins(8, 4, 8, 4)
            btn_layout.addWidget(select_btn)
            btn_layout.addStretch()
            self.table.setCellWidget(row, 4, btn_container)
        
        # Restore selection if exists
        if self._selected_case_id:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if item and item.data(Qt.UserRole) == self._selected_case_id:
                    self.table.selectRow(row)
                    break
    
    def _create_case(self):
        dialog = CreateCaseDialog(self)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_case_data()
            try:
                case_id = str(uuid.uuid4())
                create_case(case_id, data["name"], data["description"])
                self._load_cases()
                
                # Select the newly created case
                self._selected_case_id = case_id
                self._populate_table()
                self.case_selected.emit(case_id)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create case: {str(e)}")
    
    def _on_select_case(self, case_id: str):
        self._selected_case_id = case_id
        self.case_selected.emit(case_id)
        # Update button states
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 4)
            if widget:
                btn = widget.findChild(QPushButton)
                if btn and btn.property("case_id") == case_id:
                    btn.setText("Selected")
                    btn.setEnabled(False)
                elif btn:
                    btn.setText("Select")
                    btn.setEnabled(True)
    
    def get_selected_case_id(self):
        return self._selected_case_id
    
    def get_selected_case(self):
        if self._selected_case_id:
            return get_case(self._selected_case_id)
        return None