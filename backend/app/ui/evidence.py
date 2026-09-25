"""
ReConstructAI - Evidence / File Management Page
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QAbstractItemView, QComboBox, QLineEdit,
    QSplitter, QScrollArea, QSizePolicy, QSpacerItem,
    QMessageBox, QProgressBar, QMenu
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer, QPoint
from PySide6.QtGui import QFont, QAction
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
import hashlib

# Import analysis worker
from app.ui.analysis_worker import AnalysisWorker, SingleFileAnalysisWorker


class StatusBadge(QLabel):
    """Status badge widget with color coding."""
    
    STATUS_COLORS = {
        "UNANALYZED": ("#737373", "#303030"),
        "ANALYZING": ("#F59E0B", "#3D2B00"),
        "HEALTHY": ("#22C55E", "#0F2D15"),
        "SUSPICIOUS": ("#F59E0B", "#3D2B00"),
        "CORRUPTED": ("#EF4444", "#2D0F0F"),
        "FRAGMENTED": ("#14B8A6", "#0B2D2B"),
        "PARTIALLY_RECOVERABLE": ("#22C55E", "#0F2D15"),
        "RECOVERED": ("#22C55E", "#0F2D15"),
    }
    
    def __init__(self, status: str = "UNANALYZED", parent=None):
        super().__init__(parent)
        self.setObjectName("statusBadge")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(100)
        self.setMaximumWidth(140)
        self.setFixedHeight(28)
        font = QFont()
        font.setPointSize(10)
        font.setWeight(QFont.Medium)
        self.setFont(font)
        self.set_status(status)
    
    def set_status(self, status: str):
        self._status = status
        self.setText(status.replace("_", " "))
        text_color, bg_color = self.STATUS_COLORS.get(status, ("#737373", "#303030"))
        self.setStyleSheet(f"""
            QLabel#statusBadge {{
                background-color: {bg_color};
                color: {text_color};
                border: 1px solid {text_color}40;
                border-radius: 14px;
                padding: 4px 12px;
                font-size: 10px;
                font-weight: 600;
            }}
        """)


class FileTableWidget(QTableWidget):
    """Custom file table with status badges and sorting."""
    
    file_selected = Signal(dict)  # Emits file data
    
    COLUMNS = [
        ("name", "Filename", 250),
        ("type", "Type", 100),
        ("size", "Size", 100),
        ("status", "Status", 140),
        ("path", "Path", 300),
    ]
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._files = []
        self._setup_ui()
    
    def _setup_ui(self):
        self.setColumnCount(len(self.COLUMNS))
        self.setHorizontalHeaderLabels([col[1] for col in self.COLUMNS])
        
        header = self.horizontalHeader()
        for i, (_, _, width) in enumerate(self.COLUMNS):
            if width:
                header.setSectionResizeMode(i, QHeaderView.Fixed)
                self.setColumnWidth(i, width)
            else:
                header.setSectionResizeMode(i, QHeaderView.Stretch)
        
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setAlternatingRowColors(False)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSortingEnabled(True)
        
        self.itemSelectionChanged.connect(self._on_selection_changed)
    
    def set_files(self, files: List[Dict[str, Any]]):
        """Set the file list and populate table."""
        self._files = files
        self.setRowCount(len(files))
        
        for row, file_data in enumerate(files):
            self._populate_row(row, file_data)
        
        # Re-apply sorting
        self.sortItems(0, Qt.AscendingOrder)
    
    def _populate_row(self, row: int, file_data: Dict[str, Any]):
        """Populate a single table row."""
        # Filename
        name_item = QTableWidgetItem(file_data.get("name", ""))
        name_item.setData(Qt.UserRole, file_data)
        name_item.setToolTip(file_data.get("name", ""))
        self.setItem(row, 0, name_item)
        
        # Type
        self.setItem(row, 1, QTableWidgetItem(file_data.get("type", "")))
        
        # Size
        size_str = self._format_size(file_data.get("size", 0))
        size_item = QTableWidgetItem(size_str)
        size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setItem(row, 2, size_item)
        
        # Status badge
        status = file_data.get("status", "UNANALYZED")
        badge = StatusBadge(status)
        badge_container = QWidget()
        badge_layout = QHBoxLayout(badge_container)
        badge_layout.setContentsMargins(8, 4, 8, 4)
        badge_layout.addWidget(badge)
        badge_layout.addStretch()
        self.setCellWidget(row, 3, badge_container)
        
        # Path
        path_item = QTableWidgetItem(file_data.get("path", ""))
        path_item.setToolTip(file_data.get("path", ""))
        self.setItem(row, 4, path_item)
    
    def _format_size(self, size: int) -> str:
        """Format file size human-readable."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    def _on_selection_changed(self):
        selected = self.selectedItems()
        if selected:
            row = selected[0].row()
            item = self.item(row, 0)
            if item:
                file_data = item.data(Qt.UserRole)
                if file_data:
                    self.file_selected.emit(file_data)
    
    def get_selected_file(self) -> Optional[Dict[str, Any]]:
        selected = self.selectedItems()
        if selected:
            row = selected[0].row()
            item = self.item(row, 0)
            if item:
                return item.data(Qt.UserRole)
        return None
    
    def filter_by_status(self, status: str):
        """Filter table rows by status."""
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item:
                file_data = item.data(Qt.UserRole)
                if file_data:
                    file_status = file_data.get("status", "UNANALYZED")
                    if status == "All" or file_status == status:
                        self.setRowHidden(row, False)
                    else:
                        self.setRowHidden(row, True)
    
    def update_file_status(self, file_path: str, status: str):
        """Update status of a specific file."""
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item:
                file_data = item.data(Qt.UserRole)
                if file_data and file_data.get("path") == file_path:
                    file_data["status"] = status
                    # Update badge
                    badge_container = self.cellWidget(row, 3)
                    if badge_container:
                        badge = badge_container.findChild(StatusBadge)
                        if badge:
                            badge.set_status(status)
                    break


class FileDetailsPanel(QWidget):
    """File details panel showing analysis results."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(360)
        self._setup_ui()
        self.clear_details()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Panel header
        header = QFrame()
        header.setObjectName("card")
        header.setFixedHeight(60)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 16, 0)
        
        title = QLabel("File Details")
        title.setObjectName("sectionTitle")
        header_layout.addWidget(title)
        header_layout.addStretch()
        
        layout.addWidget(header)
        
        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(16, 16, 16, 16)
        self.content_layout.setSpacing(16)
        
        scroll.setWidget(self.content)
        layout.addWidget(scroll)
        
        # Initialize detail fields
        self._fields = {}
        field_defs = [
            ("filename", "Filename", True),
            ("path", "Path", False),
            ("size", "Size", False),
            ("sha256", "SHA-256", True),
            ("detected_type", "Detected Type", False),
            ("mime_type", "MIME Type", False),
            ("entropy", "Entropy", False),
            ("status", "Status", True),
        ]
        
        for key, label, copyable in field_defs:
            self._add_field(key, label, copyable)
        
        self.content_layout.addStretch()
    
    def _add_field(self, key: str, label: str, copyable: bool):
        """Add a detail field row."""
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(4)
        
        lbl = QLabel(label)
        lbl.setObjectName("mutedLabel")
        lbl.setStyleSheet("font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px;")
        container_layout.addWidget(lbl)
        
        value_lbl = QLabel("—")
        value_lbl.setObjectName("bodyLabel")
        value_lbl.setWordWrap(True)
        value_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        value_lbl.setStyleSheet("font-family: 'Consolas', 'Monospace'; font-size: 12px;")
        container_layout.addWidget(value_lbl)
        
        self._fields[key] = value_lbl
        self.content_layout.addWidget(container)
    
    def set_file_data(self, file_data: Dict[str, Any]):
        """Populate panel with file data."""
        self._fields["filename"].setText(file_data.get("name", "—"))
        self._fields["path"].setText(file_data.get("path", "—"))
        self._fields["size"].setText(self._format_size(file_data.get("size", 0)))
        self._fields["sha256"].setText(file_data.get("sha256", "—"))
        self._fields["detected_type"].setText(file_data.get("detected_type", "—"))
        self._fields["mime_type"].setText(file_data.get("mime_type", "—"))
        
        entropy = file_data.get("entropy")
        if entropy is not None:
            self._fields["entropy"].setText(f"{entropy:.4f}")
        else:
            self._fields["entropy"].setText("—")
        
        status = file_data.get("status", "UNANALYZED")
        self._fields["status"].setText(status.replace("_", " "))
        # Color the status
        text_color, _ = StatusBadge.STATUS_COLORS.get(status, ("#737373", "#303030"))
        self._fields["status"].setStyleSheet(f"font-family: 'Consolas', 'Monospace'; font-size: 12px; color: {text_color}; font-weight: 600;")
        
        # Add fragment info if available
        self._update_fragment_info(file_data)
        
        # Add reconstruction info if available
        self._update_reconstruction_info(file_data)
    
    def _update_fragment_info(self, file_data: Dict[str, Any]):
        """Update fragment information display."""
        fragments = file_data.get("fragments")
        if fragments:
            # Remove existing fragment section if any
            self._remove_section("fragments")
            
            # Add fragment count
            count_label = QLabel(f"Fragments: {len(fragments)}")
            count_label.setObjectName("bodyLabel")
            count_label.setStyleSheet("font-family: 'Consolas', 'Monospace'; font-size: 12px; color: #14B8A6; font-weight: 600;")
            count_label.setProperty("section", "fragments")
            self.content_layout.insertWidget(self.content_layout.count() - 1, count_label)
            
            # Add fragment details
            for i, frag in enumerate(fragments[:5]):  # Show first 5
                frag_text = f"  {frag.get('fragment_id', '?')}: offset={frag.get('offset', 0)}, size={frag.get('size', 0)}, entropy={frag.get('entropy', 0):.2f}"
                frag_label = QLabel(frag_text)
                frag_label.setObjectName("bodyLabel")
                frag_label.setStyleSheet("font-family: 'Consolas', 'Monospace'; font-size: 11px; color: #A3A3A3;")
                frag_label.setProperty("section", "fragments")
                self.content_layout.insertWidget(self.content_layout.count() - 1, frag_label)
            
            if len(fragments) > 5:
                more_label = QLabel(f"  ... and {len(fragments) - 5} more fragments")
                more_label.setObjectName("bodyLabel")
                more_label.setStyleSheet("font-family: 'Consolas', 'Monospace'; font-size: 11px; color: #737373;")
                more_label.setProperty("section", "fragments")
                self.content_layout.insertWidget(self.content_layout.count() - 1, more_label)
    
    def _update_reconstruction_info(self, file_data: Dict[str, Any]):
        """Update reconstruction information display."""
        reconstructions = file_data.get("reconstructions")
        if reconstructions:
            # Remove existing reconstruction section if any
            self._remove_section("reconstructions")
            
            for i, recon in enumerate(reconstructions):
                recon_text = (f"Reconstruction {recon.get('reconstruction_id', '?')}: "
                              f"{recon.get('status', '?')}, "
                              f"integrity={recon.get('integrity_score', 0):.2f}, "
                              f"confidence={recon.get('confidence_score', 0):.2f}, "
                              f"fragments={recon.get('fragment_count', 0)}")
                recon_label = QLabel(recon_text)
                recon_label.setObjectName("bodyLabel")
                recon_label.setStyleSheet("font-family: 'Consolas', 'Monospace'; font-size: 11px; color: #22C55E;")
                recon_label.setProperty("section", "reconstructions")
                self.content_layout.insertWidget(self.content_layout.count() - 1, recon_label)
    
    def _remove_section(self, section_name: str):
        """Remove widgets from a section."""
        # Iterate backwards to safely remove
        for i in range(self.content_layout.count() - 1, -1, -1):
            widget = self.content_layout.itemAt(i).widget()
            if widget and widget.property("section") == section_name:
                widget.setParent(None)
                widget.deleteLater()
    
    def clear_details(self):
        """Clear all fields."""
        for field in self._fields.values():
            field.setText("—")
            field.setStyleSheet("font-family: 'Consolas', 'Monospace'; font-size: 12px;")
        # Clear fragment and reconstruction sections
        self._remove_section("fragments")
        self._remove_section("reconstructions")
    
    def _format_size(self, size: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


class EvidencePage(QWidget):
    """Main evidence/file management page."""
    
    analyze_requested = Signal(str)  # Emits folder path
    folder_selected = Signal(str)    # Emits selected folder path
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._evidence_folder = None
        self._files = []
        self._analysis_worker = None
        self._single_file_worker = None
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        # Top toolbar
        toolbar = QFrame()
        toolbar.setObjectName("card")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(16, 12, 16, 12)
        toolbar_layout.setSpacing(12)
        
        # Folder selection
        self.folder_label = QLabel("No evidence folder selected")
        self.folder_label.setObjectName("bodyLabel")
        self.folder_label.setStyleSheet("font-family: 'Consolas', 'Monospace'; font-size: 12px;")
        self.folder_label.setMinimumWidth(300)
        toolbar_layout.addWidget(self.folder_label, 1)
        
        select_btn = QPushButton("Select Evidence Folder")
        select_btn.setObjectName("primaryButton")
        select_btn.setCursor(Qt.PointingHandCursor)
        select_btn.setMinimumWidth(180)
        select_btn.clicked.connect(self._select_folder)
        toolbar_layout.addWidget(select_btn)
        
        # Spacer
        toolbar_layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
        
        # File count
        self.file_count_label = QLabel("0 files")
        self.file_count_label.setObjectName("mutedLabel")
        toolbar_layout.addWidget(self.file_count_label)
        
        layout.addWidget(toolbar)
        
        # Filter bar
        filter_bar = QFrame()
        filter_bar.setObjectName("card")
        filter_layout = QHBoxLayout(filter_bar)
        filter_layout.setContentsMargins(16, 10, 16, 10)
        filter_layout.setSpacing(12)
        
        filter_label = QLabel("Filter:")
        filter_label.setObjectName("mutedLabel")
        filter_layout.addWidget(filter_label)
        
        self.status_filter = QComboBox()
        self.status_filter.addItems([
            "All", "UNANALYZED", "ANALYZING", "HEALTHY", 
            "SUSPICIOUS", "CORRUPTED", "FRAGMENTED", 
            "PARTIALLY_RECOVERABLE", "RECOVERED"
        ])
        self.status_filter.setMinimumWidth(180)
        self.status_filter.currentTextChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.status_filter)
        
        # Search
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search files...")
        self.search_box.setMaximumWidth(250)
        self.search_box.textChanged.connect(self._on_search_changed)
        filter_layout.addWidget(self.search_box)
        
        filter_layout.addStretch()
        
        # Analyze button
        self.analyze_btn = QPushButton("Analyze Evidence")
        self.analyze_btn.setObjectName("primaryButton")
        self.analyze_btn.setCursor(Qt.PointingHandCursor)
        self.analyze_btn.setMinimumWidth(160)
        self.analyze_btn.setEnabled(False)
        self.analyze_btn.clicked.connect(self._on_analyze_clicked)
        filter_layout.addWidget(self.analyze_btn)
        
        # Single file analysis button
        self.analyze_single_btn = QPushButton("Analyze Single File")
        self.analyze_single_btn.setObjectName("secondaryButton")
        self.analyze_single_btn.setCursor(Qt.PointingHandCursor)
        self.analyze_single_btn.setMinimumWidth(160)
        self.analyze_single_btn.clicked.connect(self._on_analyze_single_clicked)
        filter_layout.addWidget(self.analyze_single_btn)
        
        layout.addWidget(filter_bar)
        
        # Main content splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        
        # Left: File table
        table_container = QFrame()
        table_container.setObjectName("card")
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(0)
        
        self.file_table = FileTableWidget()
        self.file_table.file_selected.connect(self._on_file_selected)
        table_layout.addWidget(self.file_table)
        
        splitter.addWidget(table_container)
        
        # Right: Details panel
        self.details_panel = FileDetailsPanel()
        splitter.addWidget(self.details_panel)
        
        splitter.setSizes([800, 360])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        
        layout.addWidget(splitter, 1)
        
        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        
        # Status label
        self.status_label = QLabel("Select an evidence folder to begin")
        self.status_label.setObjectName("mutedLabel")
        self.status_label.setStyleSheet("padding: 8px;")
        layout.addWidget(self.status_label)
    
    def _select_folder(self):
        """Open folder selection dialog."""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Evidence Folder",
            str(Path.home()),
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        
        if folder:
            self._load_folder(folder)
    
    def _load_folder(self, folder_path: str):
        """Load and discover files in the selected folder."""
        self._evidence_folder = folder_path
        self.folder_label.setText(folder_path)
        self.folder_label.setToolTip(folder_path)
        self.analyze_btn.setEnabled(True)
        
        self.status_label.setText("Discovering files...")
        QTimer.singleShot(100, lambda: self._discover_files(folder_path))
    
    def _discover_files(self, folder_path: str):
        """Recursively discover files in folder."""
        self._files = []
        
        try:
            for root, dirs, files in os.walk(folder_path):
                # Skip hidden directories
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                
                for filename in files:
                    if filename.startswith('.'):
                        continue
                    
                    file_path = os.path.join(root, filename)
                    try:
                        stat = os.stat(file_path)
                        size = stat.st_size
                        
                        # Get extension
                        ext = os.path.splitext(filename)[1].lower()
                        if not ext:
                            ext = "unknown"
                        else:
                            ext = ext[1:]  # Remove leading dot
                        
                        # Calculate SHA-256
                        sha256 = self._calculate_sha256(file_path)
                        
                        # Detect type (basic)
                        detected_type = self._detect_type(file_path)
                        mime_type = self._get_mime_type(ext)
                        
                        file_data = {
                            "name": filename,
                            "path": file_path,
                            "rel_path": os.path.relpath(file_path, folder_path),
                            "size": size,
                            "type": ext.upper(),
                            "extension": ext,
                            "sha256": sha256,
                            "detected_type": detected_type,
                            "mime_type": mime_type,
                            "entropy": None,
                            "status": "UNANALYZED",
                        }
                        
                        self._files.append(file_data)
                        
                    except (OSError, PermissionError):
                        continue
            
            self.file_table.set_files(self._files)
            self.file_count_label.setText(f"{len(self._files)} files")
            self.status_label.setText(f"Discovered {len(self._files)} files in {self._evidence_folder}")
            
            self.folder_selected.emit(folder_path)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to discover files: {str(e)}")
            self.status_label.setText(f"Error: {str(e)}")
    
    def _calculate_sha256(self, file_path: str) -> str:
        """Calculate SHA-256 hash of file."""
        sha256 = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except:
            return "—"
    
    def _detect_type(self, file_path: str) -> str:
        """Basic file type detection."""
        try:
            with open(file_path, "rb") as f:
                header = f.read(16)
            
            # Magic bytes
            if header.startswith(b"%PDF"):
                return "PDF"
            elif header.startswith(b"\x89PNG"):
                return "PNG"
            elif header.startswith(b"\xff\xd8\xff"):
                return "JPEG"
            elif header.startswith(b"PK\x03\x04") or header.startswith(b"PK\x05\x06"):
                return "ZIP"
            elif header.startswith(b"MZ"):
                return "PE Executable"
            elif header.startswith(b"\x7fELF"):
                return "ELF Executable"
            elif header[:4] in (b"RIFF", b"Rar!"):
                return "RIFF/RAR"
            elif all(32 <= b <= 126 or b in (9, 10, 13) for b in header):
                return "Text"
            else:
                return "Binary"
        except:
            return "Unknown"
    
    def _get_mime_type(self, ext: str) -> str:
        """Get MIME type from extension."""
        mime_map = {
            "pdf": "application/pdf",
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "zip": "application/zip",
            "txt": "text/plain",
            "py": "text/x-python",
            "json": "application/json",
            "xml": "application/xml",
            "html": "text/html",
            "exe": "application/x-dosexec",
            "dll": "application/x-dosexec",
        }
        return mime_map.get(ext, "application/octet-stream")
    
    def _on_filter_changed(self, status: str):
        self.file_table.filter_by_status(status)
    
    def _on_search_changed(self, text: str):
        text = text.lower()
        for row in range(self.file_table.rowCount()):
            item = self.file_table.item(row, 0)
            if item:
                file_data = item.data(Qt.UserRole)
                if file_data:
                    name = file_data.get("name", "").lower()
                    path = file_data.get("rel_path", "").lower()
                    if text in name or text in path:
                        self.file_table.setRowHidden(row, False)
                    else:
                        self.file_table.setRowHidden(row, True)
    
    def _on_file_selected(self, file_data: Dict[str, Any]):
        self.details_panel.set_file_data(file_data)
    
    def _on_analyze_clicked(self):
        if self._evidence_folder:
            self.analyze_requested.emit(self._evidence_folder)
            self.progress_bar.show()
            self.analyze_btn.setEnabled(False)
            self.analyze_btn.setText("Analyzing...")
            self.status_label.setText("Analysis started...")
    
    def set_analysis_complete(self, success: bool, message: str = ""):
        """Called when analysis completes."""
        self.progress_bar.hide()
        self.analyze_btn.setEnabled(True)
        self.analyze_btn.setText("Analyze Evidence")
        if success:
            self.status_label.setText(message or "Analysis complete")
        else:
            self.status_label.setText(f"Analysis failed: {message}")
    
    def update_file_analysis(self, file_path: str, analysis_data: Dict[str, Any]):
        """Update a file's analysis results."""
        # Update internal data
        for file_data in self._files:
            if file_data["path"] == file_path:
                file_data.update(analysis_data)
                break
        
        # Update table
        self.file_table.update_file_status(file_path, analysis_data.get("status", "UNANALYZED"))
        
        # Update details if this file is selected
        selected = self.file_table.get_selected_file()
        if selected and selected.get("path") == file_path:
            self.details_panel.set_file_data(selected)
    
    # ============================================================
    # Folder Analysis (using CoreEngine via background worker)
    # ============================================================
    
    def start_folder_analysis(self, case_id: str = None, case_name: str = "Evidence Analysis"):
        """Start background analysis of all discovered files."""
        if not self._evidence_folder or not self._files:
            return
        
        # Get list of file paths to analyze
        file_paths = [f["path"] for f in self._files if f["status"] == "UNANALYZED"]
        
        if not file_paths:
            self.status_label.setText("All files already analyzed")
            return
        
        # Create worker
        self._analysis_worker = AnalysisWorker(
            evidence_folder=self._evidence_folder,
            file_paths=file_paths,
            case_id=case_id,
            case_name=case_name
        )
        
        # Connect signals
        self._analysis_worker.progress.connect(self._on_analysis_progress)
        self._analysis_worker.file_started.connect(self._on_file_analysis_started)
        self._analysis_worker.file_completed.connect(self._on_file_analysis_completed)
        self._analysis_worker.file_failed.connect(self._on_file_analysis_failed)
        self._analysis_worker.analysis_complete.connect(self._on_folder_analysis_complete)
        self._analysis_worker.case_created.connect(self._on_case_created)
        
        # Update UI
        self.progress_bar.show()
        self.analyze_btn.setEnabled(False)
        self.analyze_btn.setText("Analyzing...")
        self.analyze_single_btn.setEnabled(False)
        
        # Start worker
        self._analysis_worker.start()
    
    def _on_analysis_progress(self, message: str, percent: int, stage: str):
        """Handle progress updates from worker."""
        self.status_label.setText(message)
        if percent > 0:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(percent)
        else:
            self.progress_bar.setRange(0, 0)  # Indeterminate
    
    def _on_file_analysis_started(self, file_path: str):
        """Handle file analysis start."""
        # Update status to ANALYZING
        self.update_file_analysis(file_path, {"status": "ANALYZING"})
    
    def _on_file_analysis_completed(self, file_path: str, analysis_data: Dict[str, Any]):
        """Handle successful file analysis completion."""
        self.update_file_analysis(file_path, analysis_data)
    
    def _on_file_analysis_failed(self, file_path: str, error: str):
        """Handle file analysis failure."""
        self.update_file_analysis(file_path, {
            "status": "CORRUPTED",
            "error": error
        })
    
    def _on_folder_analysis_complete(self, success: bool, message: str):
        """Handle folder analysis completion."""
        self.progress_bar.hide()
        self.progress_bar.setRange(0, 0)
        self.analyze_btn.setEnabled(True)
        self.analyze_btn.setText("Analyze Evidence")
        self.analyze_single_btn.setEnabled(True)
        self.status_label.setText(message)
        
        # Refresh recovered page if available
        if hasattr(self, 'recovered_page_ref') and self.recovered_page_ref:
            self.recovered_page_ref.refresh()
    
    def _on_case_created(self, case_id: str):
        """Handle case creation."""
        self.status_label.setText(f"Created case: {case_id[:8]}...")
    
    def _on_analyze_clicked(self):
        """Handle Analyze Evidence button click."""
        if self._evidence_folder:
            self.start_folder_analysis()
    
    # ============================================================
    # Single File Analysis
    # ============================================================
    
    def _on_analyze_single_clicked(self):
        """Handle Analyze Single File button click."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select File to Analyze",
            str(Path.home()),
            "All Files (*)"
        )
        
        if file_path:
            self._analyze_single_file(file_path)
    
    def _analyze_single_file(self, file_path: str):
        """Analyze a single file using CoreEngine."""
        # Create worker
        self._single_file_worker = SingleFileAnalysisWorker(file_path)
        
        # Connect signals
        self._single_file_worker.progress.connect(self._on_single_file_progress)
        self._single_file_worker.completed.connect(self._on_single_file_completed)
        
        # Update UI
        self.progress_bar.show()
        self.progress_bar.setRange(0, 0)
        self.analyze_btn.setEnabled(False)
        self.analyze_single_btn.setEnabled(False)
        self.status_label.setText(f"Analyzing {os.path.basename(file_path)}...")
        
        # Start worker
        self._single_file_worker.start()
    
    def _on_single_file_progress(self, message: str, percent: int):
        """Handle single file analysis progress."""
        self.status_label.setText(message)
        if percent > 0:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(percent)
    
    def _on_single_file_completed(self, success: bool, analysis_data: Dict[str, Any], error: str):
        """Handle single file analysis completion."""
        self.progress_bar.hide()
        self.progress_bar.setRange(0, 0)
        self.analyze_btn.setEnabled(True)
        self.analyze_single_btn.setEnabled(True)
        
        if success:
            file_path = analysis_data.get("file_path", "")
            file_name = os.path.basename(file_path)
            
            # Add to files list if not already present
            existing = next((f for f in self._files if f["path"] == file_path), None)
            if not existing:
                # Create file data from analysis
                file_info = analysis_data.get("file_info", {})
                new_file_data = {
                    "name": file_name,
                    "path": file_path,
                    "rel_path": file_name,
                    "size": file_info.get("size", 0),
                    "type": os.path.splitext(file_name)[1][1:].upper() if "." in file_name else "UNKNOWN",
                    "extension": os.path.splitext(file_name)[1][1:].lower() if "." in file_name else "unknown",
                    "sha256": file_info.get("sha256"),
                    "detected_type": file_info.get("file_type"),
                    "mime_type": file_info.get("mime_type"),
                    "entropy": file_info.get("entropy"),
                    "status": analysis_data.get("status", "UNANALYZED"),
                    "scan_id": analysis_data.get("scan_id"),
                    "case_id": analysis_data.get("case_id"),
                    "fragments": analysis_data.get("fragments", []),
                    "reconstructions": analysis_data.get("reconstructions", []),
                    "analysis": analysis_data.get("analysis", {}),
                }
                self._files.append(new_file_data)
                self.file_table.set_files(self._files)
                self.file_count_label.setText(f"{len(self._files)} files")
            
            # Update with full analysis data
            self.update_file_analysis(file_path, analysis_data)
            
            # Select the file in table
            for row in range(self.file_table.rowCount()):
                item = self.file_table.item(row, 0)
                if item:
                    data = item.data(Qt.UserRole)
                    if data and data.get("path") == file_path:
                        self.file_table.selectRow(row)
                        break
            
            self.status_label.setText(f"Analysis complete: {file_name}")
        else:
            self.status_label.setText(f"Analysis failed: {error}")
            QMessageBox.warning(self, "Analysis Failed", f"Failed to analyze file:\n{error}")
    
    def get_evidence_folder(self) -> Optional[str]:
        return self._evidence_folder
    
    def get_files(self) -> List[Dict[str, Any]]:
        return self._files


class RecoveredPage(QWidget):
    """Recovered artifacts page."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)
        
        # Header
        header_layout = QHBoxLayout()
        
        title = QLabel("Recovered Artifacts")
        title.setObjectName("titleLabel")
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("secondaryButton")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        header_layout.addWidget(refresh_btn)
        
        layout.addLayout(header_layout)
        
        # Recovered files table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Filename", "Type", "Size", "SHA-256", "Path"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        layout.addWidget(self.table)
        
        # Empty state
        self.empty_label = QLabel(
            "No recovered artifacts yet.\n\n"
            "Run analysis on evidence files to generate\n"
            "reconstruction candidates, then reconstruct\n"
            "artifacts to populate this section."
        )
        self.empty_label.setObjectName("bodyLabel")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("color: #737373; padding: 80px; line-height: 1.8;")
        self.empty_label.hide()
        layout.addWidget(self.empty_label)
        
        self._load_recovered()
    
    def _load_recovered(self):
        """Load recovered artifacts from storage/reconstructed/."""
        recovered_dir = Path("storage/reconstructed")
        if not recovered_dir.exists():
            recovered_dir.mkdir(parents=True, exist_ok=True)
        
        files = list(recovered_dir.glob("*"))
        
        if not files:
            self.table.hide()
            self.empty_label.show()
            return
        
        self.table.show()
        self.empty_label.hide()
        
        self.table.setRowCount(len(files))
        for row, file_path in enumerate(files):
            try:
                stat = file_path.stat()
                size = stat.st_size
                sha256 = self._calculate_sha256(str(file_path))
                
                self.table.setItem(row, 0, QTableWidgetItem(file_path.name))
                self.table.setItem(row, 1, QTableWidgetItem(file_path.suffix[1:].upper() if file_path.suffix else "UNKNOWN"))
                self.table.setItem(row, 2, QTableWidgetItem(self._format_size(size)))
                self.table.setItem(row, 3, QTableWidgetItem(sha256[:16] + "..."))
                self.table.setItem(row, 4, QTableWidgetItem(str(file_path)))
            except:
                continue
    
    def _calculate_sha256(self, file_path: str) -> str:
        sha256 = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except:
            return "—"
    
    def _format_size(self, size: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    def refresh(self):
        self._load_recovered()


class PlaceholderPage(QWidget):
    """Placeholder page for not-yet-implemented sections."""
    
    def __init__(self, title: str, description: str, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(16)
        layout.addStretch()
        
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(48, 48, 48, 48)
        card_layout.setSpacing(16)
        
        title_lbl = QLabel(title)
        title_lbl.setObjectName("titleLabel")
        title_lbl.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(title_lbl)
        
        desc_lbl = QLabel(description)
        desc_lbl.setObjectName("bodyLabel")
        desc_lbl.setAlignment(Qt.AlignCenter)
        desc_lbl.setWordWrap(True)
        card_layout.addWidget(desc_lbl)
        
        layout.addWidget(card, alignment=Qt.AlignCenter)
        layout.addStretch()