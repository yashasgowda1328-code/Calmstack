"""
ReConstructAI - Deleted Data Recovery Page

Drives the existing deleted-file recovery engine (DeletedFileScanner,
CandidateExtractor) over a real .dd / .img storage image. Nothing on this page
is simulated: candidates come from scanning the image, and extraction writes a
real file whose path and hash are reported back.
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QSplitter,
    QStackedWidget,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.recovery.candidate_extractor import CandidateExtractor
from app.recovery.deleted_file_scanner import DeletedFileScanner
from app.recovery.models import DeletedDataCandidate, RecoveryScanResult
from app.ui.components import (
    DetailsPanel,
    EmptyState,
    ForensicTable,
    Page,
    StatusChip,
    Toolbar,
    format_entropy,
    format_offset,
    format_size,
    make_button,
    shorten_hash,
    status_display,
)
from app.ui.session import SESSION


#: Statuses the recovery engine reports, used only to label the column.
#: The filter itself is built from the tokens actually present in a scan, so it
#: can never offer a status the engine cannot produce.
KNOWN_STATUSES = (
    "NOT_EXTRACTED",
    "EXTRACTED",
    "EXTRACTION_FAILED",
    "available",
    "partial",
    "unavailable",
    "reused",
)


CANDIDATE_COLUMNS = [
    {
        "key": "candidate_id",
        "label": "Candidate",
        "width": 150,
        "kind": "mono",
        "value": lambda r: (r.get("candidate_id"), "mono"),
    },
    {
        "key": "original_name",
        "label": "Original Name",
        "stretch": True,
        "kind": "text",
        "value": lambda r: (r.get("original_name"), "text"),
        "tooltip": lambda r: r.get("original_path") or r.get("original_name") or "",
    },
    {
        "key": "size",
        "label": "Size",
        "width": 100,
        "kind": "size",
        "value": lambda r: (format_size(r.get("size")), "size"),
    },
    {
        "key": "metadata_address",
        "label": "Metadata",
        "width": 110,
        "kind": "mono",
        "value": lambda r: (r.get("metadata_address"), "mono"),
    },
    {
        "key": "recovery_status",
        "label": "Status",
        "width": 165,
        "kind": "center",
        "value": lambda r: (status_display(r.get("recovery_status")), "center"),
    },
    {
        "key": "file_type",
        "label": "Type",
        "width": 120,
        "kind": "text",
        "value": lambda r: (r.get("extracted_file_type") or r.get("file_type"), "text"),
    },
]


class DeletedDataScanWorker(QThread):
    """Background worker for scanning a storage image."""

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
        except Exception as exc:
            self.completed.emit(
                RecoveryScanResult(image_path=self.image_path, error=str(exc))
            )


class CandidateExtractionWorker(QThread):
    """Background worker for extracting a candidate."""

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
        except Exception as exc:
            self.candidate.recovery_status = "EXTRACTION_FAILED"
            self.candidate.error = str(exc)
            self.completed.emit(self.candidate)


class DeletedDataRecoveryPage(Page):
    """Deleted data recovery page."""

    def __init__(self, parent=None):
        self._image_path: Optional[str] = None
        self._candidates: List[Dict[str, Any]] = []
        self._scan_worker: Optional[DeletedDataScanWorker] = None
        self._extract_worker: Optional[CandidateExtractionWorker] = None
        super().__init__(
            "Deleted Data Recovery",
            "Scan a raw storage image for deleted and unallocated entries",
            parent=parent,
        )
        self._setup_body()

    # ----------------------------------------------------------------
    # Construction
    # ----------------------------------------------------------------

    def _setup_body(self):
        self.btn_select = make_button(
            "Select Image",
            self._select_image,
            variant="secondary",
            tooltip="Choose a .dd or .img raw storage image",
        )
        self.btn_scan = make_button(
            "Scan Image",
            self._start_scan,
            variant="primary",
            tooltip="Scan the selected image for deleted file entries",
        )
        self.btn_extract = make_button(
            "Extract Selected",
            self._on_extract_selected,
            variant="secondary",
            tooltip="Extract the selected candidate's data from the image",
        )
        self.add_header_widget(self.btn_select)
        self.add_header_widget(self.btn_scan)
        self.add_header_widget(self.btn_extract)

        self.toolbar = Toolbar()
        self.image_label = QLabel("No storage image selected")
        self.image_label.setObjectName("monoValue")
        self.image_label.setMaximumWidth(420)
        self.image_label.setToolTip("No storage image selected")
        self.toolbar.add_widget(self.image_label)

        self.count_label = QLabel("0 candidates")
        self.count_label.setObjectName("mutedLabel")
        self.toolbar.add_widget(self.count_label)

        self.result_chip = StatusChip("Not scanned", "UNANALYZED")
        self.result_chip.setToolTip("Outcome of the last image scan")
        self.toolbar.add_widget(self.result_chip)
        self.toolbar.add_spacer()

        self.status_filter = QComboBox()
        self.status_filter.addItem("All statuses", "")
        self.status_filter.setMinimumWidth(180)
        self.status_filter.setToolTip("Show only candidates with this recovery status")
        self.status_filter.currentIndexChanged.connect(self._on_filter_changed)
        self.toolbar.add_widget(self.status_filter)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search candidates")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setMaximumWidth(220)
        self.search_box.setMinimumWidth(140)
        self.search_box.textChanged.connect(self._on_search_changed)
        self.toolbar.add_widget(self.search_box)
        self.add_widget(self.toolbar)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.hide()
        self.add_widget(self.progress_bar)

        self.workspace = QStackedWidget()

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(1)

        self.table = ForensicTable(CANDIDATE_COLUMNS, object_name="dataTable")
        self.table.itemSelectionChanged.connect(self._on_candidate_selected)
        self.splitter.addWidget(self.table)

        self.details = DetailsPanel("Candidate Details")
        self.details.clear("Select a candidate to view its recovered metadata")
        self.splitter.addWidget(self.details)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([860, 380])
        self.workspace.addWidget(self.splitter)

        self.empty_state = EmptyState(
            "No deleted data candidates found yet",
            "Select a storage image and click Scan Image to discover "
            "deleted and unallocated file entries.",
        )
        self.workspace.addWidget(self.empty_state)
        self.add_widget(self.workspace, 1)

        self.status_label = QLabel("Select a storage image to begin")
        self.status_label.setObjectName("pageSubtitle")
        self.status_label.setWordWrap(True)
        self.add_widget(self.status_label)

        self.btn_scan.setEnabled(False)
        self.btn_extract.setEnabled(False)
        self.workspace.setCurrentIndex(1)
        self._update_buttons()

    # ----------------------------------------------------------------
    # Image selection and scan
    # ----------------------------------------------------------------

    def _select_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Storage Image",
            str(Path.home()),
            "Storage Images (*.dd *.img);;All Files (*)",
        )
        if not file_path:
            return
        self._image_path = file_path
        self.image_label.setText(Path(file_path).name)
        self.image_label.setToolTip(file_path)
        self.set_subtitle(file_path)
        self.status_label.setText(f"Selected image: {file_path}")
        self._update_buttons()

    def _start_scan(self):
        if not self._image_path or self._scan_worker is not None:
            return
        if self._extract_worker is not None and self._extract_worker.isRunning():
            return

        self.progress_bar.show()
        self._update_buttons()
        self.status_label.setText("Scanning image...")

        self._scan_worker = DeletedDataScanWorker(self._image_path)
        self._scan_worker.progress.connect(self._on_progress)
        self._scan_worker.completed.connect(self._on_scan_completed)
        self._scan_worker.start()

    def _on_progress(self, message: str):
        self.status_label.setText(message)

    def _on_scan_completed(self, result: RecoveryScanResult):
        self.progress_bar.hide()
        self._scan_worker = None
        self._update_buttons()

        if result.error:
            self.status_label.setText(f"Scan failed: {result.error}")
            self.result_chip.set_status("Scan failed", "ERROR")
            QMessageBox.warning(self, "Scan Failed", result.error)
            return

        self._candidates = [self._to_record(c) for c in result.candidates]
        self._render()

        if result.warning:
            self.status_label.setText(f"Scan complete with warning: {result.warning}")
            self.result_chip.set_status("Scan warning", "PENDING")
        elif self._candidates:
            recoverable = sum(1 for c in result.candidates if c.is_recoverable)
            self.status_label.setText(
                f"Scan complete: {len(self._candidates)} candidate(s), "
                f"{recoverable} recoverable."
            )
            self.result_chip.set_status(
                f"{len(self._candidates)} candidates", "CANDIDATES_FOUND"
            )
            SESSION.log_activity(
                f"Scanned {Path(self._image_path).name}: "
                f"{len(self._candidates)} deleted candidate(s)",
                "recovery",
            )
        else:
            self.status_label.setText("Scan complete: no deleted candidates found.")
            self.result_chip.set_status("No candidates", "NO_CANDIDATES")

    @staticmethod
    def _to_record(candidate: DeletedDataCandidate) -> Dict[str, Any]:
        return {
            "candidate": candidate,
            "candidate_id": candidate.candidate_id,
            "original_name": candidate.original_name,
            "original_path": candidate.original_path,
            "size": candidate.size,
            "metadata_address": candidate.metadata_address,
            "allocation_status": candidate.allocation_status,
            "deleted_status": candidate.deleted_status,
            "data_availability": candidate.data_availability,
            "recovery_status": candidate.recovery_status,
            "file_type": candidate.file_type,
            "extracted_file_type": candidate.extracted_file_type,
            "extracted_mime_type": candidate.extracted_mime_type,
            "extracted_entropy": candidate.extracted_entropy,
            "extracted_sha256": candidate.extracted_sha256,
            "extracted_size": candidate.extracted_size,
            "extracted_path": candidate.extracted_path,
            "extents": list(candidate.source_extents or []),
            "error": candidate.error,
            "is_recoverable": bool(candidate.is_recoverable),
        }

    # ----------------------------------------------------------------
    # Extraction
    # ----------------------------------------------------------------

    def _on_extract_selected(self):
        record = self.table.current_record()
        if not record:
            return
        candidate = record.get("candidate")
        if not candidate or not record.get("is_recoverable"):
            QMessageBox.warning(
                self, "Extraction", "The selected candidate is not recoverable."
            )
            return

        self.progress_bar.show()
        self._update_buttons()
        self.status_label.setText(f"Extracting {record['candidate_id']}...")

        self._extract_worker = CandidateExtractionWorker(candidate)
        self._extract_worker.progress.connect(self._on_progress)
        self._extract_worker.completed.connect(self._on_extract_completed)
        self._extract_worker.start()

    def _on_extract_completed(self, candidate: DeletedDataCandidate):
        self.progress_bar.hide()
        self._extract_worker = None
        self._update_buttons()

        updated = self._to_record(candidate)
        for index, record in enumerate(self._candidates):
            if record.get("candidate_id") == updated["candidate_id"]:
                self._candidates[index] = updated
                break
        self._render()

        if updated.get("recovery_status") == "EXTRACTED":
            self.status_label.setText(
                f"Extracted {updated['candidate_id']} to {updated['extracted_path']}"
            )
            self.result_chip.set_status("Extraction complete", "EXTRACTED")
            SESSION.log_activity(
                f"Extracted {updated.get('original_name') or updated['candidate_id']}",
                "recovery",
            )
        else:
            self.status_label.setText(
                f"Extraction failed: {updated.get('error') or 'unknown error'}"
            )
            self.result_chip.set_status("Extraction failed", "EXTRACTION_FAILED")
            QMessageBox.warning(
                self,
                "Extraction Failed",
                updated.get("error") or "Extraction failed",
            )

    # ----------------------------------------------------------------
    # Rendering
    # ----------------------------------------------------------------

    def _render(self):
        self.table.set_records(self._candidates)
        self.count_label.setText(f"{len(self._candidates)} candidates")
        self._rebuild_status_filter()
        self._on_search_changed(self.search_box.text())
        self.workspace.setCurrentIndex(0 if self.table.rowCount() else 1)
        if not self._candidates:
            self.empty_state.set_state(
                "No deleted data candidates found yet",
                "Select a storage image and click Scan Image to discover "
                "deleted and unallocated file entries.",
            )
        else:
            self.table.select_first()

    def _rebuild_status_filter(self):
        """Offer exactly the statuses this scan actually produced."""
        present = []
        for record in self._candidates:
            for token in (
                record.get("recovery_status"),
                record.get("data_availability"),
            ):
                if token and token not in present:
                    present.append(token)

        present.sort(
            key=lambda token: (
                KNOWN_STATUSES.index(token) if token in KNOWN_STATUSES else len(KNOWN_STATUSES),
                token,
            )
        )
        current = self.status_filter.currentData()
        self.status_filter.blockSignals(True)
        self.status_filter.clear()
        self.status_filter.addItem("All statuses", "")
        for token in present:
            self.status_filter.addItem(status_display(token), token)
        if current:
            index = self.status_filter.findData(current)
            if index > 0:
                self.status_filter.setCurrentIndex(index)
        self.status_filter.blockSignals(False)

    def _on_candidate_selected(self):
        record = self.table.current_record()
        if not record:
            self.details.clear("Select a candidate to view its recovered metadata")
            self.btn_extract.setEnabled(False)
            return

        self.btn_extract.setEnabled(bool(record.get("is_recoverable")))

        identity = self.details.section("identity", "Recovered metadata")
        identity.add_row("Candidate", record.get("candidate_id"), mono=True)
        identity.add_row("Original name", record.get("original_name"))
        identity.add_row("Original path", record.get("original_path"))
        identity.add_row("Size", format_size(record.get("size")))
        identity.add_row("Metadata address", record.get("metadata_address"), mono=True)
        identity.add_row("Allocation", record.get("allocation_status"))
        identity.add_row("Deleted", "Yes" if record.get("deleted_status") else "No")
        identity.add_row("Data availability", record.get("data_availability"))
        identity.add_row("Recovery status", status_display(record.get("recovery_status")))

        extents = record.get("extents") or []
        if extents:
            extent_section = self.details.section("extents", "Source extents")
            for extent in extents[:5]:
                extent_section.add_row(
                    f"At {format_offset(getattr(extent, 'offset', None))}",
                    format_size(getattr(extent, "size", None)),
                    mono=True,
                )
            if len(extents) > 5:
                extent_section.add_row("More", f"{len(extents) - 5} more extents")

        if record.get("extracted_path"):
            extracted = self.details.section("extracted", "Extraction result")
            extracted.add_row("Extracted to", record.get("extracted_path"), mono=True)
            extracted.add_row("Size", format_size(record.get("extracted_size")))
            extracted.add_row(
                "SHA-256", shorten_hash(record.get("extracted_sha256"), 16, 12), mono=True
            )
            extracted.add_row("Type", record.get("extracted_file_type"))
            extracted.add_row("MIME", record.get("extracted_mime_type"))
            extracted.add_row(
                "Entropy", format_entropy(record.get("extracted_entropy"))
            )

        if record.get("error"):
            error = self.details.section("error", "Error")
            error.add_row("Message", record.get("error"))

    def _on_filter_changed(self, _index: int):
        if not self._candidates:
            return
        wanted = self.status_filter.currentData()
        predicate = None
        if wanted:
            predicate = (
                lambda r: r.get("recovery_status") == wanted
                or r.get("data_availability") == wanted
            )
        self.table.apply_filter(predicate)
        self.workspace.setCurrentIndex(0 if self.table.rowCount() else 1)

    def _on_search_changed(self, text: str):
        self.table.apply_search(text)
        self.workspace.setCurrentIndex(0 if self.table.rowCount() else 1)

    # ----------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------

    def _update_buttons(self):
        scanning = self._scan_worker is not None
        extracting = self._extract_worker is not None
        self.btn_select.setEnabled(not scanning and not extracting)
        self.btn_scan.setEnabled(bool(self._image_path) and not scanning and not extracting)
        self.btn_extract.setEnabled(
            not scanning and not extracting and bool(self.table.current_record())
        )

    def candidates(self) -> List[Dict[str, Any]]:
        return list(self._candidates)
