"""
ReConstructAI - Deleted Data Recovery UI Page
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QAbstractItemView, QComboBox, QLineEdit,
    QSplitter, QScrollArea, QSizePolicy, QSpacerItem,
    QMessageBox, QProgressBar
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer
from PySide6.QtGui import QFont
import os
from pathlib import Path
from typing import Optional, List, Dict, Any

from app.recovery.deleted_file_scanner import DeletedFileScanner
from app.recovery.candidate_extractor import CandidateExtractor
from app.recovery.models import DeletedDataCandidate, RecoveryScanResult


class DeletedDataRecoveryPage(QWidget):
    """Deleted data recovery page."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._image_path = None
        self._candidates = []
        self._scan_worker = None
        self._extract_worker = None
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        # Header
        header_layout = QHBoxLayout()
        
        title = QLabel("Deleted Data Recovery")
        title.setObjectName("titleLabel")
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        layout.addLayout(header_layout)
        
        # Top section - image selection
        image_section = QFrame()
        image_section.setObjectName("card")
        image_layout = QVBoxLayout(image_section)
        image_layout.setContentsMargins(20, 16, 20, 16)
        image_layout.setSpacing(12)
        
        section_title = QLabel("Storage Image")
        section_title.setObjectName("sectionTitle")
        image_layout.addWidget(section_title)
        
        image_row = QHBoxLayout()
        image_row.setSpacing(12)
        
        self.image_label = QLabel("No storage image selected")
        self.image_label.setObjectName("bodyLabel")
        self.image_label.setStyleSheet("font-family: 'Consolas', 'Monospace'; font-size: 12px;")
        image_row.addWidget(self.image_label, 1)
        
        select_btn = QPushButton("Select Image")
        select_btn.setObjectName("secondaryButton")
        select_btn.setCursor(Qt.PointingHandCursor)
        select_btn.clicked.connect(self._select_image)
        image_row.addWidget(select_btn)
        
        self.scan_btn = QPushButton("Scan Image")
        self.scan_btn.setObjectName("primaryButton")
        self.scan_btn.setCursor(Qt.PointingHandCursor)
        self.scan_btn.setEnabled(False)
        self.scan_btn.clicked.connect(self._start_scan)
        image_row.addWidget(self.scan_btn)
        
        image_layout.addLayout(image_row)
        
        self.image_info_label = QLabel("Supported formats: .dd, .img (raw disk images)")
        self.image_info_label.setObjectName("mutedLabel")
        image_layout.addWidget(self.image_info_label)
        
        layout.addWidget(image_section)
        
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
            "All", "DELETED_CANDIDATE", "RECOVERABLE", "PARTIAL",
            "DATA_UNAVAILABLE", "REUSED_METADATA", "EXTRACTION_FAILED", "EXTRACTED"
        ])
        self.status_filter.setMinimumWidth(180)
        self.status_filter.currentTextChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.status_filter)
        
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search candidates...")
        self.search_box.setMaximumWidth(250)
        self.search_box.textChanged.connect(self._on_search_changed)
        filter_layout.addWidget(self.search_box)
        
        filter_layout.addStretch()
        
        self.extract_btn = QPushButton("Extract Selected")
        self.extract_btn.setObjectName("secondaryButton")
        self.extract_btn.setCursor(Qt.PointingHandCursor)
        self.extract_btn.setEnabled(False)
        self.extract_btn.clicked.connect(self._on_extract_selected)
        filter_layout.addWidget(self.extract_btn)
        
        layout.addWidget(filter_bar)
        
        # Results table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Candidate", "Original Name", "Path", "Size", "Status", "Type"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.itemSelectionChanged.connect(self._on_candidate_selected)
        
        layout.addWidget(self.table)
        
        # Empty state
        self.empty_label = QLabel(
            "No deleted data candidates found yet.\n\n"
            "Select a storage image and click Scan Image to discover\n"
            "deleted and unallocated file entries."
        )
        self.empty_label.setObjectName("bodyLabel")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("color: #737373; padding: 80px; line-height: 1.8;")
        self.empty_label.hide()
        layout.addWidget(self.empty_label)
        
        # Details panel
        details_section = QFrame()
        details_section.setObjectName("card")
        details_layout = QVBoxLayout(details_section)
        details_layout.setContentsMargins(16, 14, 16, 14)
        details_layout.setSpacing(8)
        
        details_title = QLabel("Candidate Details")
        details_title.setObjectName("sectionTitle")
        details_layout.addWidget(details_title)
        
        self.details_label = QLabel("Select a candidate to view details")
        self.details_label.setObjectName("bodyLabel")
        self.details_label.setWordWrap(True)
        details_layout.addWidget(self.details_label)
        
        layout.addWidget(details_section)
        
        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Select a storage image to begin")
        self.status_label.setObjectName("mutedLabel")
        self.status_label.setStyleSheet("padding: 8px;")
        layout.addWidget(self.status_label)
    
    def _select_image(self):
        """Open file picker for storage image."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Storage Image",
            str(Path.home()),
            "Storage Images (*.dd *.img);;All Files (*)"
        )
        
        if file_path:
            self._image_path = file_path
            self.image_label.setText(file_path)
            self.image_label.setToolTip(file_path)
            self.scan_btn.setEnabled(True)
            self.status_label.setText(f"Selected image: {file_path}")
    
    def _start_scan(self):
        """Start scanning the selected image."""
        if not self._image_path:
            return
        
        self.progress_bar.show()
        self.progress_bar.setRange(0, 0)
        self.scan_btn.setEnabled(False)
        self.status_label.setText("Scanning image...")
        
        # Run scan in background thread
        self._scan_worker = DeletedDataScanWorker(self._image_path)
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.completed.connect(self._on_scan_completed)
        self._scan_worker.start()
    
    def _on_scan_progress(self, message: str):
        self.status_label.setText(message)
    
    def _on_scan_completed(self, result: RecoveryScanResult):
        self.progress_bar.hide()
        self.scan_btn.setEnabled(True)
        
        if result.error:
            self.status_label.setText(f"Scan failed: {result.error}")
            QMessageBox.warning(self, "Scan Failed", result.error)
            return
        
        self._candidates = result.candidates
        self._populate_table()
        
        if result.warning:
            self.status_label.setText(f"Scan complete with warning: {result.warning}")
        else:
            self.status_label.setText(f"Scan complete: {len(self._candidates)} candidates found")
    
    def _populate_table(self):
        self.table.setRowCount(len(self._candidates))
        
        if not self._candidates:
            self.table.hide()
            self.empty_label.show()
            return
        
        self.table.show()
        self.empty_label.hide()
        
        for row, candidate in enumerate(self._candidates):
            self.table.setItem(row, 0, QTableWidgetItem(candidate.candidate_id))
            self.table.setItem(row, 1, QTableWidgetItem(candidate.original_name or "—"))
            self.table.setItem(row, 2, QTableWidgetItem(candidate.original_path or "—"))
            self.table.setItem(row, 3, QTableWidgetItem(self._format_size(candidate.size)))
            self.table.setItem(row, 4, QTableWidgetItem(candidate.recovery_status))
            self.table.setItem(row, 5, QTableWidgetItem(candidate.file_type or "—"))
            
            # Store candidate data
            self.table.item(row, 0).setData(Qt.UserRole, candidate)
    
    def _on_candidate_selected(self):
        selected = self.table.selectedItems()
        if not selected:
            return
        
        row = selected[0].row()
        candidate = self.table.item(row, 0).data(Qt.UserRole)
        if candidate:
            self._show_candidate_details(candidate)
            self.extract_btn.setEnabled(candidate.is_recoverable)
    
    def _show_candidate_details(self, candidate: DeletedDataCandidate):
        """Show candidate details."""
        details = []
        details.append(f"Candidate: {candidate.candidate_id}")
        details.append(f"Original Name: {candidate.original_name or '—'}")
        details.append(f"Original Path: {candidate.original_path or '—'}")
        details.append(f"Size: {self._format_size(candidate.size)}")
        details.append(f"Metadata Address: {candidate.metadata_address}")
        details.append(f"Allocation Status: {candidate.allocation_status}")
        details.append(f"Deleted: {'Yes' if candidate.deleted_status else 'No'}")
        details.append(f"Data Availability: {candidate.data_availability}")
        details.append(f"Recovery Status: {candidate.recovery_status}")
        
        if candidate.extracted_sha256:
            details.append(f"SHA-256: {candidate.extracted_sha256}")
            details.append(f"Extracted Size: {self._format_size(candidate.extracted_size)}")
            details.append(f"Detected Type: {candidate.extracted_file_type or '—'}")
            details.append(f"MIME: {candidate.extracted_mime_type or '—'}")
            details.append(f"Entropy: {candidate.extracted_entropy}")
            details.append(f"Extracted To: {candidate.extracted_path}")
        
        if candidate.source_extents:
            details.append(f"Source Extents: {len(candidate.source_extents)}")
            for extent in candidate.source_extents[:5]:
                details.append(f"  Offset {extent.offset}, Size {self._format_size(extent.size)}")
            if len(candidate.source_extents) > 5:
                details.append(f"  ... and {len(candidate.source_extents) - 5} more")
        
        if candidate.error:
            details.append(f"Error: {candidate.error}")
        
        self.details_label.setText("\n".join(details))
    
    def _on_filter_changed(self, status: str):
        for row in range(self.table.rowCount()):
            candidate = self.table.item(row, 0).data(Qt.UserRole)
            if candidate:
                if status == "All" or candidate.recovery_status == status or candidate.data_availability == status:
                    self.table.setRowHidden(row, False)
                else:
                    self.table.setRowHidden(row, True)
    
    def _on_search_changed(self, text: str):
        text = text.lower()
        for row in range(self.table.rowCount()):
            candidate = self.table.item(row, 0).data(Qt.UserRole)
            if candidate:
                name = (candidate.original_name or "").lower()
                path = (candidate.original_path or "").lower()
                if text in name or text in path or text in candidate.candidate_id.lower():
                    self.table.setRowHidden(row, False)
                else:
                    self.table.setRowHidden(row, True)
    
    def _on_extract_selected(self):
        """Extract selected candidate."""
        selected = self.table.selectedItems()
        if not selected:
            return
        
        row = selected[0].row()
        candidate = self.table.item(row, 0).data(Qt.UserRole)
        if not candidate or not candidate.is_recoverable:
            QMessageBox.warning(self, "Extraction", "Selected candidate is not recoverable.")
            return
        
        self.progress_bar.show()
        self.progress_bar.setRange(0, 0)
        self.extract_btn.setEnabled(False)
        self.status_label.setText(f"Extracting {candidate.candidate_id}...")
        
        self._extract_worker = CandidateExtractionWorker(candidate)
        self._extract_worker.progress.connect(self._on_extract_progress)
        self._extract_worker.completed.connect(self._on_extract_completed)
        self._extract_worker.start()
    
    def _on_extract_progress(self, message: str):
        self.status_label.setText(message)
    
    def _on_extract_completed(self, candidate: DeletedDataCandidate):
        self.progress_bar.hide()
        self.extract_btn.setEnabled(False)
        
        # Update candidate in list
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.UserRole) == candidate:
                self.table.setItem(row, 4, QTableWidgetItem(candidate.recovery_status))
                self.table.setItem(row, 5, QTableWidgetItem(candidate.extracted_file_type or candidate.file_type or "—"))
                break
        
        if candidate.recovery_status == "EXTRACTED":
            self.status_label.setText(f"Extracted {candidate.candidate_id} to {candidate.extracted_path}")
        else:
            self.status_label.setText(f"Extraction failed: {candidate.error}")
            QMessageBox.warning(self, "Extraction Failed", candidate.error or "Extraction failed")
        
        self._show_candidate_details(candidate)
    
    def _format_size(self, size: int) -> str:
        if size <= 0:
            return "0 B"
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


class DeletedDataScanWorker(QThread):
    """Background worker for scanning storage image."""
    
    progress = Signal(str)
    completed = Signal(object)
    
    def __init__(self, image_path: str):
        super().__init__()
        self.image_path = image_path
    
    def run(self):
        try:
            self.progress.emit("Opening image...")
            scanner = DeletedFileScanner(self.image_path)
            self.progress.emit("Scanning filesystem...")
            result = scanner.scan()
            self.completed.emit(result)
        except Exception as e:
            self.completed.emit(RecoveryScanResult(
                image_path=self.image_path,
                error=str(e)
            ))


class CandidateExtractionWorker(QThread):
    """Background worker for extracting candidate."""
    
    progress = Signal(str)
    completed = Signal(object)
    
    def __init__(self, candidate: DeletedDataCandidate):
        super().__init__()
        self.candidate = candidate
    
    def run(self):
        try:
            self.progress.emit("Extracting candidate...")
            extractor = CandidateExtractor()
            result = extractor.extract_candidate(self.candidate)
            self.completed.emit(result)
        except Exception as e:
            self.candidate.recovery_status = "EXTRACTION_FAILED"
            self.candidate.error = str(e)
            self.completed.emit(self.candidate)
