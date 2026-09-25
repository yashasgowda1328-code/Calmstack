"""
ReConstructAI - Evidence Workspace

The main investigation workspace: select a source, run analysis, review
files and inspect per-file identity, integrity and recovery detail.

Before a folder is selected the page shows the already-analyzed records
from the database, so the workspace is useful immediately and empty states
always explain themselves.
"""

import hashlib
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.storage.database import get_feedback_reports_by_target, save_feedback_report
from app.ui.analysis_worker import (
    AnalysisWorker,
    CrossEvidenceRecoveryWorker,
    SingleFileAnalysisWorker,
)
from app.ui.components import (
    COLORS,
    NOT_AVAILABLE,
    RELEVANCE_PALETTE,
    DetailsPanel,
    EmptyState,
    ForensicTable,
    Page,
    StatusChip,
    Toolbar,
    format_bytes_exact,
    format_datetime,
    format_entropy,
    format_offset,
    format_score,
    format_size,
    make_button,
    status_display,
    status_palette,
)
from app.ui.session import SESSION

# Backwards-compatible alias: the status chip replaced the old badge widget.
StatusBadge = StatusChip


#: Status tokens offered by the Evidence status filter.
STATUS_FILTERS = [
    ("All statuses", None),
    ("Unanalyzed", "UNANALYZED"),
    ("Analyzing", "ANALYZING"),
    ("Healthy", "HEALTHY"),
    ("Suspicious", "SUSPICIOUS"),
    ("Corrupted", "CORRUPTED"),
    ("Analysis failed", "ANALYSIS_FAILED"),
    ("Fragmented", "FRAGMENTED"),
    ("Partially recoverable", "PARTIALLY_RECOVERABLE"),
    ("Recovered", "RECOVERED"),
]


# ====================================================================
# Table
# ====================================================================

#: Compact, investigation-oriented columns (the path lives in the details).
FILE_COLUMNS = [
    {
        "key": "name",
        "label": "Name",
        "stretch": True,
        "kind": "text",
        "value": lambda r: (r.get("name"), "text"),
        "tooltip": lambda r: r.get("path") or r.get("name") or "",
    },
    {
        "key": "type",
        "label": "Type",
        "width": 130,
        "kind": "text",
        "value": lambda r: (r.get("type") or r.get("detected_type"), "text"),
    },
    {
        "key": "size",
        "label": "Size",
        "width": 96,
        "kind": "size",
        "value": lambda r: (format_size(r.get("size")), "size"),
    },
    {
        "key": "status",
        "label": "Status",
        "width": 150,
        "kind": "center",
        "value": lambda r: (status_display(r.get("status")), "center"),
    },
    {
        "key": "integrity",
        "label": "Integrity",
        "width": 96,
        "kind": "size",
        "value": lambda r: (
            format_score(r.get("integrity"), 2) if r.get("integrity") is not None else None,
            "size",
        ),
        "tooltip": "Reconstruction integrity score (0-1) when a candidate exists.",
    },
]


class FileTableWidget(ForensicTable):
    """Evidence file table. Emits the full record for the selected row."""

    file_selected = Signal(dict)

    COLUMNS = FILE_COLUMNS

    def __init__(self, parent=None):
        super().__init__(FILE_COLUMNS, parent=parent, object_name="dataTable")
        self._files: List[Dict[str, Any]] = []
        self.itemSelectionChanged.connect(self._on_selection_changed)

    def set_files(self, files: List[Dict[str, Any]]):
        self._files = list(files)
        self.set_records(self._files)

    def files(self) -> List[Dict[str, Any]]:
        return list(self._files)

    def _on_selection_changed(self):
        record = self.current_record()
        if record is not None:
            self.file_selected.emit(record)

    def get_selected_file(self) -> Optional[Dict[str, Any]]:
        return self.current_record()

    def update_file_status(self, file_path: str, status: str):
        """Update the status of a single row in place."""
        for row, record in enumerate(self._files):
            if record.get("path") == file_path:
                record["status"] = status
                item = self.item(row, 3)
                if item is not None:
                    item.setText(status_display(status))
                return

    def select_by_path(self, file_path: str):
        for row, record in enumerate(self._records):
            if record.get("path") == file_path:
                self.selectRow(row)
                return True
        return False


# ====================================================================
# Details panel
# ====================================================================

class FileDetailsPanel(QWidget):
    """File detail panel: Identity, Integrity, Recovery & AI, Context."""

    report_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._current_file_data: Optional[Dict[str, Any]] = None
        self._setup_ui()
        self.clear_details()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.panel = DetailsPanel("File Details", min_width=300, max_width=440)
        layout.addWidget(self.panel)

        # The Report-as-Useful action lives in the panel header so the panel
        # stays a single reusable component.
        self.report_btn = make_button(
            "Report as Useful",
            variant="ghost",
            tooltip="Submit a feedback report for this file",
        )
        self.report_btn.clicked.connect(self._on_report_clicked)
        self.report_btn.hide()
        self.panel.add_header_action(self.report_btn)

        self.identity = self.panel.section("identity", "Identity")
        self._row_filename = self.identity.add_row("Filename")
        self._row_path = self.identity.add_row("Path", mono=True)
        self._row_type = self.identity.add_row("Type")
        self._row_mime = self.identity.add_row("MIME")
        self._row_size = self.identity.add_row("Size")

        self.integrity = self.panel.section("integrity", "Integrity")
        self._row_sha256 = self.integrity.add_row("SHA-256", mono=True)
        self._row_entropy = self.integrity.add_row("Entropy", mono=True)
        self._row_integrity = self.integrity.add_row("Integrity", mono=True)
        self._row_status = self.integrity.add_row("Status")

        self.recovery = self.panel.section("recovery", "Recovery / AI")
        self._row_fragments = self.recovery.add_row("Fragments")
        self._row_relevance = self.recovery.add_row("AI relevance", mono=True)
        self._row_relevance_class = self.recovery.add_row("Relevance class")
        self._row_confidence = self.recovery.add_row("Recovery confidence", mono=True)
        self._row_reconstruction = self.recovery.add_row("Reconstruction")
        self._row_validation = self.recovery.add_row("Validation")

        self.context = self.panel.section("context", "Context")
        self._row_case = self.context.add_row("Case")
        self._row_scan = self.context.add_row("Scan", mono=True)
        self._row_analyzed = self.context.add_row("Analyzed")

        self.fragment_body = self.panel.section("fragments", "Fragments")
        self._row_fragments_detail = self.fragment_body.add_row("Extracted", mono=True)

        self.feedback = self.panel.section("feedback", "User Feedback")
        self._row_feedback_status = self.feedback.add_row("Status")
        self._row_feedback_reason = self.feedback.add_row("Reason")
        self._row_feedback_date = self.feedback.add_row("Date")
        self.feedback.setVisible(False)

    # ----------------------------------------------------------------
    # Population
    # ----------------------------------------------------------------

    def set_file_data(self, file_data: Dict[str, Any]):
        """Populate every section from a real file record."""
        self._current_file_data = file_data
        for name in ("identity", "integrity", "recovery", "context"):
            self.panel.section(name)
        self.panel.hide_empty_hint()

        # -- Identity
        self._row_filename.set_value(file_data.get("name"))
        self._row_path.set_value(file_data.get("path"))
        self._row_type.set_value(file_data.get("type") or file_data.get("detected_type"))
        self._row_mime.set_value(file_data.get("mime_type"))
        size = file_data.get("size")
        self._row_size.set_value(format_bytes_exact(size) if size is not None else None)

        # -- Integrity
        sha256 = file_data.get("sha256")
        self._row_sha256.set_value(sha256)
        self._row_sha256.value_label.setToolTip(sha256 or "")

        self._row_entropy.set_value(
            format_entropy(file_data.get("entropy"))
            if file_data.get("entropy") is not None else None
        )

        reconstructions = file_data.get("reconstructions") or []
        integrity = file_data.get("integrity")
        if integrity is None and reconstructions:
            integrity = max(
                (r.get("integrity_score") or 0.0 for r in reconstructions),
                default=None,
            )
        self._row_integrity.set_value(
            format_score(integrity) if integrity is not None else None
        )

        status = file_data.get("status")
        self._row_status.set_value(
            status_display(status) if status else None,
            color=status_palette(status)[0] if status else "",
        )

        # -- Recovery / AI
        self._update_recovery(file_data)
        self._update_context(file_data)
        self._update_fragment_list(file_data)
        self._load_feedback(file_data)

        # Report-as-useful is only offered for genuinely low relevance items.
        classification = (
            file_data.get("ai_classification") or file_data.get("relevance_classification")
        )
        self.report_btn.setVisible(classification == "LOW_RELEVANCE")

    def _update_recovery(self, file_data: Dict[str, Any]):
        fragments = file_data.get("fragments") or []
        if fragments:
            self._row_fragments.set_value(
                f"{len(fragments)} extracted", color=COLORS["accent_secondary"]
            )
        elif file_data.get("fragment_count") is not None:
            self._row_fragments.set_value(str(file_data.get("fragment_count")))
        else:
            self._row_fragments.set_value(None)

        score = file_data.get("relevance_score")
        if score is None:
            scores = [
                f.get("relevance_score") for f in fragments if f.get("relevance_score") is not None
            ]
            if scores:
                score = sum(scores) / len(scores)
        self._row_relevance.set_value(format_score(score) if score is not None else None)

        classification = (
            file_data.get("ai_classification")
            or file_data.get("relevance_classification")
            or file_data.get("relevance_class")
        )
        self._row_relevance_class.set_value(
            status_display(classification) if classification else None,
            color=RELEVANCE_PALETTE.get(classification, "") if classification else "",
        )

        reconstructions = file_data.get("reconstructions") or []
        confidence = file_data.get("confidence")
        if confidence is None and reconstructions:
            confidence = max((r.get("confidence_score") or 0.0) for r in reconstructions)
        self._row_confidence.set_value(
            format_score(confidence) if confidence is not None else None
        )

        if reconstructions:
            best = max(reconstructions, key=lambda r: r.get("confidence_score") or 0.0)
            self._row_reconstruction.set_value(
                f"{len(reconstructions)} candidate(s), best {status_display(best.get('status'))}",
                color=status_palette(best.get("status"))[0],
            )
        else:
            self._row_reconstruction.set_value(None)

        validation = file_data.get("validation_status") or next(
            (r.get("validation_status") for r in reconstructions if r.get("validation_status")),
            None,
        )
        self._row_validation.set_value(
            status_display(validation) if validation else None,
            color=status_palette(validation)[0] if validation else "",
        )

    def _update_context(self, file_data: Dict[str, Any]):
        self._row_case.set_value(file_data.get("case_name"))
        self._row_scan.set_value(file_data.get("scan_id"))
        self._row_scan.value_label.setToolTip(file_data.get("scan_id") or "")
        self._row_analyzed.set_value(
            format_datetime(file_data.get("created_at"))
            if file_data.get("created_at") else None
        )

    def _update_fragment_list(self, file_data: Dict[str, Any]):
        fragments = file_data.get("fragments") or []
        self.fragment_body.setVisible(bool(fragments))
        if not fragments:
            return
        lines = []
        for index, fragment in enumerate(fragments[:6]):
            lines.append(
                f"{index + 1:>2}. {format_offset(fragment.get('offset'))}"
                f"  {format_size(fragment.get('size'))}"
                f"  e={format_entropy(fragment.get('entropy'), 2)}"
            )
        if len(fragments) > 6:
            lines.append(f"    + {len(fragments) - 6} more")
        self._row_fragments_detail.set_value("\n".join(lines))

    # ----------------------------------------------------------------
    # Feedback (existing Report-as-Useful feature)
    # ----------------------------------------------------------------

    def _load_feedback(self, file_data: Dict[str, Any]):
        target_id = (
            file_data.get("file_id") or file_data.get("scan_id") or file_data.get("path")
        )
        if not target_id:
            self.feedback.setVisible(False)
            return
        try:
            feedback = get_feedback_reports_by_target(target_id)
        except Exception:
            feedback = []
        self.set_user_feedback(feedback)

    def set_user_feedback(self, feedback_list: List[Dict[str, Any]]):
        if not feedback_list:
            self.feedback.setVisible(False)
            return

        entry = feedback_list[0]
        self.feedback.setVisible(True)
        self._row_feedback_status.set_value(
            status_display(entry.get("report_status") or "SUBMITTED"),
            color=COLORS["accent_primary"],
        )
        self._row_feedback_reason.set_value(entry.get("user_reason"))
        self._row_feedback_date.set_value(format_datetime(entry.get("created_at")))

    def _on_report_clicked(self):
        """Collect file info and submit a Report-as-Useful feedback entry."""
        file_data = self._current_file_data or {}
        if not file_data:
            return

        reason, ok = QInputDialog.getMultiLineText(
            self,
            "Report as Useful",
            "Why do you consider this file useful? (Optional)",
            "",
        )
        if not ok:
            return
        reason = reason.strip()

        filename = file_data.get("name", "")
        file_path = file_data.get("path", "")
        file_type = file_data.get("type") or file_data.get("detected_type") or ""
        mime_type = file_data.get("mime_type")
        scan_id = file_data.get("scan_id")
        candidate_id = file_data.get("file_id") or file_data.get("candidate_id")
        case_id = file_data.get("case_id")
        target_id = candidate_id or scan_id or file_path or filename
        relevance_score = file_data.get("relevance_score", file_data.get("ai_score"))
        ai_classification = (
            file_data.get("ai_classification")
            or file_data.get("relevance_classification")
            or file_data.get("relevance_class")
            or "LOW_RELEVANCE"
        )
        detection_result = file_data.get("detection_result") or file_data.get("analysis") or ""
        if isinstance(detection_result, (dict, list)):
            detection_result = str(detection_result)

        try:
            report_id = f"FB_{uuid.uuid4().hex[:12]}"
            save_feedback_report(
                report_id=report_id,
                case_id=case_id or "",
                target_id=target_id,
                filename=filename,
                file_path=file_path,
                file_type=file_type,
                relevance_score=relevance_score if relevance_score is not None else 0.0,
                ai_classification=ai_classification,
                detection_result=detection_result,
                user_reason=reason,
                scan_id=scan_id,
                reconstruction_id=file_data.get("reconstruction_id"),
                mime_type=mime_type,
                report_status="submitted",
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Submission Failed",
                f"Could not save the report:\n{str(e)}"
            )
            return

        QMessageBox.information(
            self,
            "Report Submitted",
            "Report submitted successfully."
        )

        self._load_feedback(file_data)

    # ----------------------------------------------------------------
    # Reset
    # ----------------------------------------------------------------

    def clear_details(self):
        for row in (
            self._row_filename, self._row_path, self._row_type, self._row_mime,
            self._row_size, self._row_sha256, self._row_entropy, self._row_integrity,
            self._row_status, self._row_fragments, self._row_relevance,
            self._row_relevance_class, self._row_confidence, self._row_reconstruction,
            self._row_validation, self._row_case, self._row_scan, self._row_analyzed,
            self._row_fragments_detail,
        ):
            row.set_value(None)
        self._current_file_data = None
        self.fragment_body.setVisible(False)
        self.feedback.setVisible(False)
        self.report_btn.hide()
        self.panel.clear("Select a file to view its details")


# ====================================================================
# Analysis progress panel
# ====================================================================

class AnalysisProgressPanel(QFrame):
    """Explicit analysis state: counter, current file, stage, progress."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(10)

        self.title_label = QLabel("Analyzing evidence")
        self.title_label.setObjectName("sectionTitle")
        top.addWidget(self.title_label)

        self.counter_label = QLabel("0 / 0 files")
        self.counter_label.setObjectName("monoValue")
        top.addWidget(self.counter_label)

        top.addStretch(1)

        self.stage_chip = StatusChip("Waiting", "UNANALYZED")
        top.addWidget(self.stage_chip)
        layout.addLayout(top)

        detail = QHBoxLayout()
        detail.setSpacing(16)

        self.current_label = QLabel("Current: -")
        self.current_label.setObjectName("bodyLabel")
        self.current_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.current_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        detail.addWidget(self.current_label, 1)

        self.stage_label = QLabel("Stage: -")
        self.stage_label.setObjectName("bodyLabel")
        detail.addWidget(self.stage_label, 0)
        layout.addLayout(detail)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

    def start(self, total: int, title: str = "Analyzing evidence"):
        self.title_label.setText(title)
        self.counter_label.setText(f"0 / {total} files")
        self.current_label.setText("Current: preparing")
        self.stage_label.setText("Stage: starting")
        self.stage_chip.set_status("Starting", "ANALYZING")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.setVisible(True)

    def set_counter(self, current: int, total: int):
        self.counter_label.setText(f"{current} / {total} files")

    def set_current_file(self, name: str):
        self.current_label.setText(f"Current: {name}")
        self.current_label.setToolTip(name)

    def set_stage(self, label: str, token: str = "ANALYZING"):
        self.stage_label.setText(f"Stage: {label}")
        self.stage_chip.set_status(label, token)

    def set_progress(self, percent: int):
        if percent < 0:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(max(0, min(100, percent)))

    def finish(self, ok: bool, message: str):
        self.setVisible(True)
        if ok:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(100)
            self.title_label.setText("Analysis complete")
            self.stage_chip.set_status("Completed", "COMPLETED")
        else:
            self.title_label.setText("Analysis failed")
            self.stage_chip.set_status("Failed", "FAILED")
        self.current_label.setText(message)


# ====================================================================
# Evidence page
# ====================================================================

class CrossRecoveryDialog(QDialog):
    """Reports exactly what the cross-evidence pipeline returned.

    Nothing here is re-interpreted: every line is a value produced by the
    recovery run, so the investigator can judge the outcome themselves.
    """

    def __init__(self, payload: Dict[str, Any], record_id: Optional[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cross-Evidence Recovery")
        self.setMinimumWidth(620)
        self._payload = payload

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        status = payload.get("status") or "UNKNOWN"
        title = QLabel(f"Recovery {str(status).replace('_', ' ').title()}")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        target = payload.get("target_path") or ""
        summary = QLabel(
            f"{Path(target).name}  -  {format_size(payload.get('target_size'))} target"
        )
        summary.setObjectName("mutedLabel")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        metrics = QHBoxLayout()
        metrics.setSpacing(12)
        for value, caption in (
            (str(payload.get("intact_portions", 0)), "Intact"),
            (str(payload.get("recovered_portions", 0)), "Recovered"),
            (str(payload.get("damaged_portions", 0)), "Damaged"),
            (str(payload.get("missing_portions", 0)), "Missing"),
            (format_score(payload.get("confidence"), 3), "Confidence"),
            (format_score(payload.get("integrity"), 3), "Integrity"),
        ):
            card = QFrame()
            card.setObjectName("card")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 10, 14, 10)
            card_layout.setSpacing(2)
            value_label = QLabel(value)
            value_label.setObjectName("statValue")
            caption_label = QLabel(caption.upper())
            caption_label.setObjectName("mutedLabel")
            card_layout.addWidget(value_label)
            card_layout.addWidget(caption_label)
            metrics.addWidget(card)
        layout.addLayout(metrics)

        artifact = payload.get("artifact_path")
        if artifact:
            artifact_label = QLabel(
                f"Artifact: {artifact}\n"
                f"Size: {format_size(payload.get('artifact_size'))}   "
                f"SHA-256: {payload.get('artifact_sha256') or NOT_AVAILABLE}"
            )
            artifact_label.setObjectName("monoValue")
            artifact_label.setWordWrap(True)
            artifact_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(artifact_label)

        damage = payload.get("damage") or []
        if damage:
            damage_label = QLabel(
                "Damage found: "
                + ", ".join(str(finding.get("kind")) for finding in damage)
            )
            damage_label.setObjectName("bodyLabel")
            damage_label.setWordWrap(True)
            layout.addWidget(damage_label)

        insights = payload.get("insights") or []
        if insights:
            insights_title = QLabel("Findings")
            insights_title.setObjectName("sectionTitle")
            layout.addWidget(insights_title)

            insights_view = QTextEdit()
            insights_view.setReadOnly(True)
            insights_view.setPlainText("\n".join(f"- {line}" for line in insights))
            insights_view.setMinimumHeight(150)
            layout.addWidget(insights_view)

        validation = payload.get("validation") or {}
        if validation:
            notes = validation.get("validation_notes") or []
            validation_label = QLabel(
                f"Structural validation: {validation.get('validation_status') or NOT_AVAILABLE}"
                f"   type: {validation.get('detected_type') or NOT_AVAILABLE}"
                + ("\n" + "\n".join(str(note) for note in notes[:3]) if notes else "")
            )
            validation_label.setObjectName("bodyLabel")
            validation_label.setWordWrap(True)
            layout.addWidget(validation_label)

        if record_id:
            stored = QLabel(f"Stored as reconstruction {record_id}")
            stored.setObjectName("mutedLabel")
            layout.addWidget(stored)
        elif payload.get("artifact_path"):
            unstored = QLabel(
                "The artifact was written to disk but not stored as a record, "
                "because this file has no analysis scan to attach it to. "
                "Analyze the file first to keep the result with its evidence."
            )
            unstored.setObjectName("mutedLabel")
            unstored.setWordWrap(True)
            layout.addWidget(unstored)

        if payload.get("error"):
            error_label = QLabel(str(payload["error"]))
            error_label.setObjectName("bodyLabel")
            error_label.setWordWrap(True)
            layout.addWidget(error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class EvidencePage(Page):
    """Main evidence workspace."""

    analyze_requested = Signal(str)
    folder_selected = Signal(str)

    def __init__(self, parent=None):
        self._evidence_folder: Optional[str] = None
        self._files: List[Dict[str, Any]] = []
        self._dataset: List[Dict[str, Any]] = []
        self._analysis_worker = None
        self._single_file_worker = None
        self._recovery_worker = None
        self._recovery_target: Optional[Dict[str, Any]] = None
        self._total_files = 0
        self._done_files = 0
        self._mode = "dataset"

        #: Set by the shell so a finished analysis can refresh the artifact list.
        self.recovered_page_ref = None

        super().__init__("Evidence", "No evidence source selected", parent=parent)
        self._setup_body()

    # ----------------------------------------------------------------
    # Construction
    # ----------------------------------------------------------------

    def _setup_body(self):
        self.btn_select = make_button(
            "Select Folder", self._on_select_folder_clicked,
            variant="secondary",
            tooltip="Choose an evidence folder to analyze",
        )
        self.btn_analyze = make_button(
            "Analyze Evidence", self._on_analyze_clicked,
            variant="primary",
            tooltip="Run the Core Engine over every unanalyzed file in the folder",
        )
        self.btn_single = make_button(
            "Analyze Single File", self._on_analyze_single_clicked,
            variant="secondary",
            tooltip="Analyze one file without selecting a folder",
        )
        self.btn_recover = make_button(
            "Cross-Evidence Recovery", self._on_cross_recovery_clicked,
            variant="secondary",
            tooltip=(
                "Rebuild the selected file from the other evidence files "
                "listed in this view"
            ),
        )
        for button in (
            self.btn_select,
            self.btn_analyze,
            self.btn_single,
            self.btn_recover,
        ):
            self.add_header_widget(button)

        # Toolbar
        self.toolbar = Toolbar()
        self.count_label = QLabel("0 files")
        self.count_label.setObjectName("mutedLabel")
        self.toolbar.add_widget(self.count_label)

        self.source_chip = StatusChip("Analyzed records", "UNANALYZED")
        self.source_chip.setToolTip("Files currently shown in the table")
        self.toolbar.add_widget(self.source_chip)
        self.toolbar.add_spacer()

        self.status_filter = QComboBox()
        for label, token in STATUS_FILTERS:
            self.status_filter.addItem(label, token)
        self.status_filter.setMinimumWidth(160)
        self.status_filter.setToolTip("Show only files with this status")
        self.status_filter.currentIndexChanged.connect(self._on_filter_changed)
        self.toolbar.add_widget(self.status_filter)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search name or path")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setMaximumWidth(240)
        self.search_box.setMinimumWidth(140)
        self.search_box.textChanged.connect(self._on_search_changed)
        self.toolbar.add_widget(self.search_box)
        self.add_widget(self.toolbar)

        # Workspace: table + details, or a deliberate empty state.
        self.workspace = QStackedWidget()

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(1)

        self.table = FileTableWidget()
        self.table.file_selected.connect(self._on_file_selected)
        self.splitter.addWidget(self.table)

        self.details_panel = FileDetailsPanel()
        self.splitter.addWidget(self.details_panel)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([860, 360])
        self.workspace.addWidget(self.splitter)

        self.empty_state = EmptyState(
            "No evidence selected",
            "Select an evidence folder or analyze a single file to begin.",
        )
        self.workspace.addWidget(self.empty_state)
        self.add_widget(self.workspace, 1)

        # Analysis progress
        self.progress_panel = AnalysisProgressPanel()
        self.add_widget(self.progress_panel)

        self.status_label = QLabel("Select an evidence folder to begin")
        self.status_label.setObjectName("pageSubtitle")
        self.status_label.setWordWrap(True)
        self.add_widget(self.status_label)

        self._update_button_states()
        self.workspace.setCurrentIndex(1)
        self.refresh()

    # ----------------------------------------------------------------
    # Data sources
    # ----------------------------------------------------------------

    def refresh(self):
        """Reload the analyzed dataset shown when no folder is active."""
        from app.ui import data as view

        try:
            self._dataset = view.file_records()
        except Exception as exc:
            self._dataset = []
            self._set_status(f"Could not read the analysis dataset: {exc}")

        if self._mode == "dataset":
            self._apply_records(self._dataset)

    def set_dataset_records(self, records: List[Dict[str, Any]]):
        """Show the analyzed dataset (used when no folder is active)."""
        self._mode = "dataset"
        self.source_chip.set_status("Analyzed records", "UNANALYZED")
        self._apply_records(records)

    def set_folder_records(self, files: List[Dict[str, Any]], folder: str):
        """Show the files discovered in the selected evidence folder."""
        self._mode = "folder"
        self.source_chip.set_status("Folder scan", "PENDING")
        self.set_subtitle(folder)
        self._apply_records(files)

    def _apply_records(self, records: List[Dict[str, Any]]):
        self._files = list(records)
        self.table.set_files(self._files)
        self.count_label.setText(f"{len(self._files)} files")
        self._update_button_states()
        self._on_filter_changed()
        self._on_search_changed(self.search_box.text())

        visible = self._visible_count()
        self.workspace.setCurrentIndex(0 if visible else 1)
        if visible:
            self.table.select_first()
        else:
            self.details_panel.clear_details()
            if not self._files:
                self._show_no_records_state()
            else:
                self.empty_state.set_state(
                    "No files match the current filter",
                    "Clear the search or choose a different status.",
                )

    def _show_no_records_state(self):
        if self._mode == "folder":
            self.empty_state.set_state(
                "No files discovered",
                "The selected folder contains no readable files.",
            )
        elif not self._dataset:
            self.empty_state.set_state(
                "No analysis results yet",
                "Run an evidence analysis to populate this view.",
            )
        else:
            self.empty_state.set_state(
                "No evidence selected",
                "Select an evidence folder or analyze a single file to begin.",
            )

    def _visible_count(self) -> int:
        count = 0
        for row in range(self.table.rowCount()):
            if not self.table.isRowHidden(row):
                count += 1
        return count

    # ----------------------------------------------------------------
    # Folder selection
    # ----------------------------------------------------------------

    def _on_select_folder_clicked(self):
        self._select_folder()

    def _select_folder(self):
        """Open the folder picker."""
        start_dir = self._evidence_folder or str(Path.home())
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Evidence Folder",
            start_dir,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if folder:
            self._load_folder(folder)

    def _load_folder(self, folder_path: str):
        """Store the folder and discover its files on the next event loop pass."""
        self._evidence_folder = folder_path
        SESSION.set_evidence_folder(folder_path)
        self.set_subtitle(folder_path)
        self._set_status("Discovering files...")
        self._update_button_states()
        QTimer.singleShot(0, lambda: self._discover_files(folder_path))

    def _discover_files(self, folder_path: str):
        """Recursively discover files in the folder (hash + type detection)."""
        discovered: List[Dict[str, Any]] = []
        unreadable = 0

        try:
            for root, dirs, files in os.walk(folder_path):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for filename in sorted(files):
                    if filename.startswith("."):
                        continue
                    file_path = os.path.join(root, filename)
                    try:
                        size = os.stat(file_path).st_size
                    except OSError:
                        unreadable += 1
                        continue

                    extension = os.path.splitext(filename)[1]
                    short = extension[1:].lower() if extension else ""
                    discovered.append({
                        "name": filename,
                        "path": file_path,
                        "rel_path": os.path.relpath(file_path, folder_path),
                        "size": size,
                        "type": extension[1:].upper() if extension else "UNKNOWN",
                        "extension": short or "unknown",
                        "sha256": self._calculate_sha256(file_path),
                        "detected_type": self._detect_type(file_path),
                        "mime_type": self._get_mime_type(short),
                        "entropy": None,
                        "status": "UNANALYZED",
                    })
        except Exception as exc:
            QMessageBox.critical(self, "Discovery Failed", f"Could not read the folder:\n{exc}")
            self._set_status(f"Failed to discover files: {exc}")
            return

        self.set_folder_records(discovered, folder_path)
        self.folder_selected.emit(folder_path)
        SESSION.log_activity(f"Selected evidence folder {folder_path}")
        self._set_status(
            f"Discovered {len(discovered)} files"
            + (f" - {unreadable} unreadable" if unreadable else "")
        )

    @staticmethod
    def _calculate_sha256(file_path: str) -> str:
        digest = hashlib.sha256()
        try:
            with open(file_path, "rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()
        except OSError:
            return ""

    @staticmethod
    def _detect_type(file_path: str) -> str:
        try:
            with open(file_path, "rb") as handle:
                header = handle.read(16)
        except OSError:
            return "Unknown"

        if not header:
            return "Empty"
        if header.startswith(b"%PDF"):
            return "PDF"
        if header.startswith(b"\x89PNG"):
            return "PNG"
        if header.startswith(b"\xff\xd8\xff"):
            return "JPEG"
        if header.startswith(b"PK\x03\x04") or header.startswith(b"PK\x05\x06"):
            return "ZIP"
        if header.startswith(b"MZ"):
            return "PE Executable"
        if header.startswith(b"\x7fELF"):
            return "ELF Executable"
        if header[:4] in (b"RIFF", b"Rar!"):
            return "RIFF/RAR"
        if all(32 <= b <= 126 or b in (9, 10, 13) for b in header):
            return "Text"
        return "Binary"

    @staticmethod
    def _get_mime_type(extension: str) -> str:
        return {
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
        }.get(extension, "application/octet-stream")

    # ----------------------------------------------------------------
    # Filtering
    # ----------------------------------------------------------------

    def _on_filter_changed(self):
        self._apply_filter()

    def _on_search_changed(self, text: str):
        self._apply_filter()

    def _apply_filter(self):
        token = self.status_filter.currentData()
        needle = (self.search_box.text() or "").strip().lower()

        def keep(record):
            if token is not None and record.get("status") != token:
                return False
            if not needle:
                return True
            haystack = " ".join(
                str(record.get(field) or "")
                for field in ("name", "path", "detected_type", "mime_type", "sha256", "status")
            ).lower()
            return needle in haystack

        self.table.apply_filter(keep)
        self.workspace.setCurrentIndex(0 if self._visible_count() else 1)
        if not self._visible_count():
            if self._files:
                self.empty_state.set_state(
                    "No files match the current filter",
                    "Clear the search or choose a different status.",
                )
            else:
                self._show_no_records_state()
            self.details_panel.clear_details()

    def _on_file_selected(self, file_data: Dict[str, Any]):
        self.details_panel.set_file_data(file_data)
        self._update_button_states()

    # ----------------------------------------------------------------
    # Folder analysis
    # ----------------------------------------------------------------

    def _on_analyze_clicked(self):
        if self._is_busy():
            return
        if not self._evidence_folder:
            self._set_status("Select an evidence folder first")
            self._select_folder()
            return
        if not self._files:
            self._set_status("No files available to analyze")
            return

        self.analyze_requested.emit(self._evidence_folder)
        self.start_folder_analysis()

    def start_folder_analysis(self, case_id: str = None, case_name: str = "Evidence Analysis"):
        """Start background analysis of the unanalyzed files in the folder."""
        if not self._evidence_folder or not self._files:
            self._set_status("Select an evidence folder before analyzing")
            return
        if self._is_busy():
            self._set_status("An analysis is already running")
            return

        file_paths = [
            f["path"] for f in self._files if f.get("status") in (None, "UNANALYZED")
        ]
        if not file_paths:
            self._set_status("Every file in this folder has already been analyzed")
            return

        worker = AnalysisWorker(
            evidence_folder=self._evidence_folder,
            file_paths=file_paths,
            case_id=case_id,
            case_name=case_name,
        )
        self._analysis_worker = worker
        worker.progress.connect(self._on_analysis_progress)
        worker.stage_changed.connect(self._on_analysis_stage)
        worker.file_started.connect(self._on_file_analysis_started)
        worker.file_completed.connect(self._on_file_analysis_completed)
        worker.file_failed.connect(self._on_file_analysis_failed)
        worker.analysis_complete.connect(self._on_folder_analysis_complete)
        worker.case_created.connect(self._on_case_created)
        worker.relevance_ready.connect(self._on_relevance_ready)

        self._total_files = len(file_paths)
        self._done_files = 0
        self.progress_panel.start(self._total_files)
        self._set_status("Analyzing evidence")
        self._set_busy(True)
        SESSION.log_activity(f"Started analysis of {len(file_paths)} file(s)", "analysis")
        worker.start()

    def _on_analysis_progress(self, message: str, percent: int, stage: str):
        self._set_status(message)
        self.progress_panel.set_progress(percent)

    def _on_analysis_stage(self, stage_token: str, label: str):
        token = "COMPLETED" if stage_token == "completed" else "ANALYZING"
        self.progress_panel.set_stage(label, token)

    def _on_file_analysis_started(self, file_path: str):
        self._done_files += 1
        self.progress_panel.set_counter(self._done_files, self._total_files)
        self.progress_panel.set_current_file(os.path.basename(file_path))
        self.update_file_analysis(file_path, {"status": "ANALYZING"})

    def _on_file_analysis_completed(self, file_path: str, analysis_data: Dict[str, Any]):
        self.update_file_analysis(file_path, analysis_data)

    def _on_file_analysis_failed(self, file_path: str, error: str):
        # A failed run is an analysis error, not evidence of file damage.
        self.update_file_analysis(file_path, {"status": "ANALYSIS_FAILED", "error": error})
        self._set_status(f"{os.path.basename(file_path)}: {error}")

    def _on_folder_analysis_complete(self, success: bool, message: str):
        self._set_busy(False)
        self.progress_panel.finish(success, message)
        self._set_status(message)
        SESSION.log_activity(message, "analysis" if success else "error")

        self._adopt_persisted_results()
        if self.recovered_page_ref is not None:
            try:
                self.recovered_page_ref.refresh()
            except Exception:
                pass

    def _on_case_created(self, case_id: str):
        SESSION.set_case(case_id)
        self._set_status(f"Case created: {case_id[:8]}")

    def _on_relevance_ready(self, scan_id: str, relevance: Dict[str, Dict[str, Any]]):
        SESSION.set_scan(scan_id)
        SESSION.record_relevance(scan_id, relevance)

    def _adopt_persisted_results(self):
        """Replace in-memory results with what the engine actually stored.

        A stored record is matched to a discovered file by content hash, because
        the database keeps a scan-convention path (`uploads/<name>`) rather than
        the folder path the file was actually discovered at.
        """
        from app.ui import data as view

        try:
            self._dataset = view.file_records()
        except Exception:
            self._dataset = []

        if self._mode == "folder":
            by_hash = {
                record.get("sha256"): record
                for record in self._dataset
                if record.get("sha256")
            }
            by_name = {record.get("name"): record for record in self._dataset}

            for record in self._files:
                stored = by_hash.get(record.get("sha256")) or by_name.get(
                    record.get("name")
                )
                if not stored:
                    continue
                for key in (
                    "status", "scan_id", "file_id", "case_id", "case_name",
                    "fragment_count", "relationship_count", "reconstruction_count",
                    "integrity", "confidence", "created_at", "entropy",
                ):
                    record[key] = stored.get(key)
            self._apply_records(self._files)
        else:
            self._apply_records(self._dataset)

    # ----------------------------------------------------------------
    # Single file analysis
    # ----------------------------------------------------------------

    def _on_analyze_single_clicked(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select File to Analyze",
            str(Path.home()),
            "All Files (*)",
        )
        if file_path:
            self._analyze_single_file(file_path)

    def _analyze_single_file(self, file_path: str):
        if self._is_busy():
            self._set_status("An analysis is already running")
            return

        worker = SingleFileAnalysisWorker(file_path, SESSION.case_id)
        self._single_file_worker = worker
        worker.progress.connect(self._on_single_file_progress)
        worker.stage_changed.connect(self._on_analysis_stage)
        worker.completed.connect(self._on_single_file_completed)

        name = os.path.basename(file_path)
        self.progress_panel.start(1, "Analyzing single file")
        self.progress_panel.set_counter(1, 1)
        self.progress_panel.set_current_file(name)
        self._set_status(f"Analyzing {name}")
        self._set_busy(True)
        worker.start()

    def _on_single_file_progress(self, message: str, percent: int):
        self._set_status(message)
        self.progress_panel.set_progress(percent)

    def _on_single_file_completed(self, success: bool, analysis_data: Dict[str, Any], error: str):
        self._set_busy(False)
        if not success:
            message = f"Analysis failed: {error}"
            self.progress_panel.finish(False, message)
            self._set_status(message)
            SESSION.log_activity(message, "error")
            QMessageBox.warning(self, "Analysis Failed", f"Failed to analyze file:\n{error}")
            return

        file_path = analysis_data.get("file_path", "")
        name = os.path.basename(file_path)
        file_info = analysis_data.get("file_info", {}) or {}

        merged = {
            "status": analysis_data.get("status"),
            "sha256": file_info.get("sha256"),
            "detected_type": file_info.get("file_type"),
            "mime_type": file_info.get("mime_type"),
            "entropy": file_info.get("entropy"),
            "size": file_info.get("size"),
            "scan_id": analysis_data.get("scan_id"),
            "case_id": analysis_data.get("case_id"),
            "file_id": analysis_data.get("file_id"),
            "fragments": analysis_data.get("fragments", []),
            "reconstructions": analysis_data.get("reconstructions", []),
            "relationships": analysis_data.get("relationships", []),
            "fragment_count": len(analysis_data.get("fragments", [])),
            "analysis": analysis_data.get("analysis", {}),
        }

        relevance_scores = analysis_data.get("relevance_scores") or {}
        if relevance_scores:
            SESSION.set_scan(analysis_data.get("scan_id"))
            SESSION.record_relevance(analysis_data.get("scan_id"), relevance_scores)
            scores = [
                r.get("relevance_score")
                for r in relevance_scores.values()
                if r.get("relevance_score") is not None
            ]
            if scores:
                merged["relevance_score"] = round(sum(scores) / len(scores), 4)
            classes = [r.get("relevance_class") for r in relevance_scores.values()]
            for candidate in ("HIGH_RELEVANCE", "UNCERTAIN", "LOW_RELEVANCE"):
                if candidate in classes:
                    merged["relevance_class"] = candidate
                    break

        self.update_file_analysis(file_path, merged)
        self.progress_panel.finish(True, f"Analysis complete: {name}")
        self._set_status(f"Analysis complete: {name}")
        SESSION.log_activity(f"Analyzed {name}", "analysis")
        self._adopt_persisted_results()
        self.table.select_by_path(file_path)

    def set_analysis_complete(self, success: bool, message: str = ""):
        """Public entry point for external completion notifications."""
        self._set_busy(False)
        text = message or ("Analysis complete" if success else "Analysis failed")
        self.progress_panel.finish(success, text)
        self._set_status(text)

    # ----------------------------------------------------------------
    # Record updates
    # ----------------------------------------------------------------

    def update_file_analysis(self, file_path: str, analysis_data: Dict[str, Any]):
        """Merge analysis results into the record and refresh the row."""
        target = None
        for record in self._files:
            if record.get("path") == file_path:
                target = record
                break

        if target is None:
            self._add_single_file_record(file_path, analysis_data)
            return

        for key, value in analysis_data.items():
            if key in ("file_path", "file_info"):
                continue
            target[key] = value

        self.table.update_file_status(file_path, target.get("status", "UNANALYZED"))
        selected = self.table.get_selected_file()
        if selected is not None and selected.get("path") == file_path:
            self.details_panel.set_file_data(selected)
        self._apply_filter()

    def _add_single_file_record(self, file_path: str, analysis_data: Dict[str, Any]):
        name = os.path.basename(file_path)
        extension = os.path.splitext(name)[1]
        file_info = analysis_data.get("file_info", {}) or {}
        record = {
            "name": name,
            "path": file_path,
            "rel_path": name,
            "size": file_info.get("size"),
            "type": extension[1:].upper() if extension else "UNKNOWN",
            "extension": extension[1:].lower() if extension else "unknown",
            "sha256": file_info.get("sha256"),
            "detected_type": file_info.get("file_type"),
            "mime_type": file_info.get("mime_type"),
            "entropy": file_info.get("entropy"),
            "status": analysis_data.get("status", "UNANALYZED"),
            "scan_id": analysis_data.get("scan_id"),
            "case_id": analysis_data.get("case_id"),
            "file_id": analysis_data.get("file_id"),
            "fragment_count": analysis_data.get("fragment_count", 0),
            "relationship_count": analysis_data.get("relationship_count", 0),
            "reconstructions": analysis_data.get("reconstructions", []),
            "fragments": analysis_data.get("fragments", []),
        }
        self._files.append(record)
        self.table.set_files(self._files)
        self.count_label.setText(f"{len(self._files)} files")
        self._update_button_states()
        self._apply_filter()
        self.table.select_by_path(file_path)

    # ----------------------------------------------------------------
    # Cross-evidence recovery
    # ----------------------------------------------------------------

    def _on_cross_recovery_clicked(self):
        """Rebuild the selected file from the other evidence in this view."""
        if self._is_busy():
            return

        record = self.table.get_selected_file()
        if not record:
            self._set_status("Select a file to recover")
            return

        target = record.get("path")
        if not target or target == NOT_AVAILABLE or not Path(target).is_file():
            self._set_status(
                "The selected file is no longer readable at its stored path"
            )
            return

        evidence = [
            path
            for path in (
                other.get("path") for other in self._files if other is not record
            )
            if path and path != NOT_AVAILABLE and Path(path).is_file()
        ]
        if not evidence:
            self._set_status(
                "No other readable evidence file is available to recover from"
            )
            return

        confirm = QMessageBox.question(
            self,
            "Cross-Evidence Recovery",
            f"Attempt to rebuild:\n\n{target}\n\n"
            f"using {len(evidence)} other evidence file(s) from this view.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        from app.ui.data import reconstructed_root

        worker = CrossEvidenceRecoveryWorker(
            target_path=target,
            evidence_paths=evidence,
            output_dir=str(reconstructed_root()),
        )
        self._recovery_worker = worker
        worker.progress.connect(self._on_recovery_progress)
        worker.stage_changed.connect(self._on_recovery_stage)
        worker.completed.connect(self._on_recovery_completed)

        self.progress_panel.start(1, title="Cross-evidence recovery")
        self._set_status("Cross-evidence recovery started")
        self._set_busy(True)
        self._recovery_target = record
        worker.start()

    def _on_recovery_progress(self, message: str, percent: int):
        self.progress_panel.set_progress(percent)
        self._set_status(message)

    def _on_recovery_stage(self, _token: str, label: str):
        self.progress_panel.set_stage(label, "RECOVERING")

    def _on_recovery_completed(self, payload: Dict[str, Any]):
        self._set_busy(False)
        self.progress_panel.finish(
            bool(payload.get("artifact_path")),
            f"Cross-evidence recovery {str(payload.get('status', '')).lower()}",
        )
        self._set_status(self._recovery_summary(payload))

        record_id = self._persist_recovery(payload)
        SESSION.log_activity(
            self._recovery_summary(payload), "recovery"
        )

        if record_id:
            self._adopt_persisted_results()
        if self.recovered_page_ref is not None:
            try:
                self.recovered_page_ref.refresh()
            except Exception:
                pass

        dialog = CrossRecoveryDialog(payload, record_id, self)
        dialog.exec()

    def _recovery_summary(self, payload: Dict[str, Any]) -> str:
        status = payload.get("status") or "UNKNOWN"
        target = Path(payload.get("target_path") or "").name
        artifact = payload.get("artifact_path")
        if artifact:
            return f"{target}: {status} -> {artifact}"
        return f"{target}: {status}, no artifact produced"

    def _persist_recovery(self, payload: Dict[str, Any]) -> Optional[str]:
        """Store a real cross-recovery result in the reconstructions table."""
        artifact = payload.get("artifact_path")
        if not artifact or not Path(artifact).is_file():
            return None

        record = self._recovery_target or {}
        scan_id = record.get("scan_id") or SESSION.scan_id
        if not scan_id:
            return None

        fragment_ids: List[str] = []
        file_id = record.get("file_id")
        if file_id:
            try:
                from app.storage.database import get_fragments_by_file

                fragment_ids = [
                    fragment.get("fragment_id")
                    for fragment in get_fragments_by_file(file_id)
                    if fragment.get("fragment_id")
                ]
            except Exception:
                fragment_ids = []

        validation = payload.get("validation") or {}
        portion_states = payload.get("portions") or []
        evidence_quality = "cross_evidence"
        if any(p.get("state") == "RECOVERED" for p in portion_states):
            evidence_quality = "cross_evidence_proven"

        details = {
            "source": "cross_evidence_recovery",
            "target_path": payload.get("target_path"),
            "target_size": payload.get("target_size"),
            "target_sha256": payload.get("target_sha256"),
            "damage": payload.get("damage") or [],
            "insights": payload.get("insights") or [],
            "portions": portion_states,
            "links": payload.get("links") or [],
            "validation": validation,
            "confidence": payload.get("confidence"),
            "integrity": payload.get("integrity"),
            "recovered_bytes": payload.get("recovered_bytes"),
        }

        reconstruction_id = f"XREC_{uuid.uuid4().hex[:12]}"
        try:
            from app.storage.database import save_reconstruction

            save_reconstruction(
                reconstruction_id=reconstruction_id,
                scan_id=scan_id,
                fragment_ids=fragment_ids,
                integrity_score=float(payload.get("integrity") or 0.0),
                confidence_score=float(payload.get("confidence") or 0.0),
                evidence_quality=evidence_quality,
                priority="cross_evidence",
                status=str(payload.get("status") or "RECONSTRUCTED"),
                output_path=str(artifact),
                output_sha256=payload.get("artifact_sha256"),
                output_size=payload.get("artifact_size"),
                output_entropy=validation.get("entropy"),
                output_file_type=validation.get("detected_type"),
                output_mime_type=validation.get("mime_type"),
                validation_status=validation.get("validation_status"),
                validation_details=details,
            )
        except Exception as exc:
            self._set_status(f"Artifact written but could not be recorded: {exc}")
            return None
        return reconstruction_id

    # ----------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------

    def _is_busy(self) -> bool:
        for worker in (
            self._analysis_worker,
            self._single_file_worker,
            self._recovery_worker,
        ):
            if worker is not None and worker.isRunning():
                return True
        return False

    def _update_button_states(self):
        busy = self._is_busy()
        has_folder = bool(self._evidence_folder)
        pending = any(f.get("status") in (None, "UNANALYZED") for f in self._files)
        selected = self.table.get_selected_file() is not None

        self.btn_analyze.setEnabled(has_folder and not busy and pending)
        self.btn_analyze.setText("Analyzing..." if busy else "Analyze Evidence")
        self.btn_analyze.setToolTip(
            "Run the Core Engine over every unanalyzed file in the folder"
            if has_folder else "Select an evidence folder first"
        )
        self.btn_single.setEnabled(not busy)
        self.btn_select.setEnabled(not busy)
        self.btn_recover.setEnabled(not busy and selected and len(self._files) > 1)
        self.btn_recover.setToolTip(
            "Rebuild the selected file from the other evidence files in this view"
            if selected and len(self._files) > 1
            else "Select a file, and have at least one other file to recover from"
        )

    def _set_busy(self, busy: bool):
        self._update_button_states()

    def _set_status(self, message: str):
        self.status_label.setText(message)

    def get_evidence_folder(self) -> Optional[str]:
        return self._evidence_folder

    def get_files(self) -> List[Dict[str, Any]]:
        return list(self._files)
