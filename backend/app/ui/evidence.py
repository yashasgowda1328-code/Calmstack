"""
ReConstructAI - Evidence Workspace

The main investigation workspace: select a source (folder or single file),
run analysis, review files, inspect identity, integrity, AI relevance,
fragment relationships, and perform cross-evidence reconstruction.
"""

import hashlib
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

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
    FragmentTimelineWidget,
    StepProgressWidget,
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

StatusBadge = StatusChip

STATUS_FILTERS = [
    ("All statuses", None),
    ("Healthy", "HEALTHY"),
    ("Suspicious", "SUSPICIOUS"),
    ("Corrupted", "CORRUPTED"),
    ("Fragmented", "FRAGMENTED"),
    ("Partially recoverable", "PARTIALLY_RECOVERABLE"),
    ("Recovered", "RECOVERED"),
    ("Unanalyzed", "UNANALYZED"),
    ("Analysis failed", "ANALYSIS_FAILED"),
]

AI_RELEVANCE_FILTERS = [
    ("All relevance", None),
    ("High Relevance", "HIGH_RELEVANCE"),
    ("Medium Relevance", "MEDIUM_RELEVANCE"),
    ("Low Relevance", "LOW_RELEVANCE"),
    ("Uncertain", "UNCERTAIN"),
]

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
        "width": 110,
        "kind": "text",
        "value": lambda r: (r.get("type") or r.get("detected_type") or "UNKNOWN", "text"),
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
        "width": 140,
        "kind": "center",
        "value": lambda r: (status_display(r.get("status")), "center"),
    },
    {
        "key": "relevance",
        "label": "AI Relevance",
        "width": 130,
        "kind": "center",
        "value": lambda r: (
            str(r.get("relevance_class") or r.get("ai_classification") or "UNANALYZED").replace("_RELEVANCE", "").title(),
            "center",
        ),
    },
    {
        "key": "fragments",
        "label": "Fragments",
        "width": 90,
        "kind": "center",
        "value": lambda r: (
            str(r.get("fragment_count") if r.get("fragment_count") is not None else (len(r.get("fragments")) if r.get("fragments") else 0)),
            "center",
        ),
    },
]


class FileTableWidget(ForensicTable):
    """Evidence file table."""

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


class ReportAsUsefulDialog(QDialog):
    """Dialog for reporting a file as useful for AI relevance feedback."""

    def __init__(self, file_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Report as Useful")
        self.setMinimumWidth(520)
        self._file_data = file_data

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("Report Evidence as Useful")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        desc = QLabel(
            "Submit investigator feedback to record that this evidence file "
            "is useful, helping refine AI recovery priority models."
        )
        desc.setObjectName("bodyLabel")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.setSpacing(6)

        fn = file_data.get("name") or file_data.get("filename") or NOT_AVAILABLE
        fp = file_data.get("path") or NOT_AVAILABLE
        ft = file_data.get("type") or file_data.get("detected_type") or NOT_AVAILABLE
        st = status_display(file_data.get("status"))
        rel = file_data.get("relevance_class") or file_data.get("ai_classification") or "LOW_RELEVANCE"

        for label, val in (
            ("Filename", fn),
            ("Path", fp),
            ("Type", ft),
            ("Scan Result", st),
            ("AI Relevance", rel),
        ):
            r = QHBoxLayout()
            l_lbl = QLabel(label)
            l_lbl.setObjectName("detailLabel")
            l_lbl.setFixedWidth(110)
            v_lbl = QLabel(str(val))
            v_lbl.setObjectName("detailValue")
            v_lbl.setWordWrap(True)
            r.addWidget(l_lbl)
            r.addWidget(v_lbl, 1)
            card_layout.addLayout(r)

        layout.addWidget(card)

        reason_lbl = QLabel("Investigator Notes / Reason (Optional):")
        reason_lbl.setObjectName("sectionTitle")
        layout.addWidget(reason_lbl)

        self.reason_edit = QTextEdit()
        self.reason_edit.setPlaceholderText("Explain why this file contains useful evidence despite its classification...")
        self.reason_edit.setMaximumHeight(90)
        layout.addWidget(self.reason_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save_report)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save_report(self):
        reason = self.reason_edit.toPlainText().strip()
        file_data = self._file_data
        report_id = f"RPT_{uuid.uuid4().hex[:12]}"
        try:
            from app.storage.database import create_report, get_scan

            case_id = file_data.get("case_id")
            if not case_id and file_data.get("scan_id"):
                scan = get_scan(file_data["scan_id"])
                case_id = (scan or {}).get("case_id")

            create_report(
                report_id=report_id,
                report_type="useful_feedback",
                case_id=case_id,
                scan_id=file_data.get("scan_id"),
                reconstruction_id=file_data.get("reconstruction_id"),
                filename=file_data.get("name") or file_data.get("filename"),
                file_path=file_data.get("path"),
                file_type=file_data.get("type") or file_data.get("detected_type"),
                mime_type=file_data.get("mime_type"),
                relevance_score=file_data.get("relevance_score"),
                ai_classification=file_data.get("relevance_class") or file_data.get("ai_classification"),
                detection_result=file_data.get("status"),
                user_reason=reason or "Reported as useful by investigator",
                report_status="SUBMITTED",
            )
            QMessageBox.information(
                self,
                "Report Stored",
                f"Successfully recorded feedback report for {file_data.get('name')}.",
            )
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Error Storing Report", f"Could not save report:\n{exc}")


class FileDetailsPanel(QWidget):
    """File detail panel with progressive disclosure: Identity, Status, Integrity, AI, Timeline, Actions."""

    analyze_requested = Signal(dict)
    reconstruct_requested = Signal(dict)
    open_recovered_requested = Signal(dict)
    report_useful_requested = Signal(dict)

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

        self.panel = DetailsPanel("File Details", min_width=320, max_width=440)
        layout.addWidget(self.panel)

        # -- Identity
        self.identity = self.panel.section("identity", "Identity")
        self._row_filename = self.identity.add_row("Filename")
        self._row_path = self.identity.add_row("Path", mono=True)
        self._row_type = self.identity.add_row("Type")
        self._row_size = self.identity.add_row("Size")

        # -- Status
        self.status_section = self.panel.section("status", "Status")
        self._row_status = self.status_section.add_row("Classification")

        # -- Integrity
        self.integrity = self.panel.section("integrity", "Integrity")
        self._row_sha256 = self.integrity.add_row("SHA-256", mono=True)
        self._row_entropy = self.integrity.add_row("Entropy", mono=True)
        self._row_validation = self.integrity.add_row("Validation")

        # -- AI Recovery Analysis
        self.ai_section = self.panel.section("ai_recovery", "AI Recovery Analysis")
        self._row_ai_rating = self.ai_section.add_row("Priority Class")
        self._row_ai_explanation = self.ai_section.add_row("Explanation")

        # -- Recovery & Fragment Timeline
        self.recovery_section = self.panel.section("recovery", "Recovery State")
        self._row_fragments_count = self.recovery_section.add_row("Fragments Found")
        self._row_reconstruction_state = self.recovery_section.add_row("Reconstruction")

        self.timeline_section = self.panel.section("timeline", "Fragment Sequence")
        self.timeline_widget = FragmentTimelineWidget()
        self.timeline_section._layout.addWidget(self.timeline_widget)

        # -- Actions
        self.actions_section = self.panel.section("actions", "Actions")
        self.actions_widget = QWidget()
        act_layout = QVBoxLayout(self.actions_widget)
        act_layout.setContentsMargins(0, 4, 0, 4)
        act_layout.setSpacing(6)

        self.btn_analyze_file = make_button("Analyze File", self._on_analyze_file, variant="primary")
        self.btn_reconstruct_file = make_button("Attempt Reconstruction", self._on_reconstruct_file, variant="secondary")
        self.btn_open_recovered = make_button("Open Recovered File", self._on_open_recovered, variant="ghost")
        self.btn_report_useful = make_button("Report as Useful", self._on_report_useful, variant="secondary")

        act_layout.addWidget(self.btn_analyze_file)
        act_layout.addWidget(self.btn_reconstruct_file)
        act_layout.addWidget(self.btn_open_recovered)
        act_layout.addWidget(self.btn_report_useful)
        self.actions_section._layout.addWidget(self.actions_widget)

    def set_file_data(self, file_data: Dict[str, Any]):
        self._current_file_data = file_data
        for name in ("identity", "status", "integrity", "ai_recovery", "recovery", "timeline", "actions"):
            self.panel.section(name)
        self.panel.hide_empty_hint()

        # Identity
        self._row_filename.set_value(file_data.get("name") or file_data.get("filename"))
        self._row_path.set_value(file_data.get("path"))
        self._row_type.set_value(file_data.get("type") or file_data.get("detected_type") or "UNKNOWN")
        size = file_data.get("size")
        self._row_size.set_value(format_bytes_exact(size) if size is not None else None)

        # Status
        status = file_data.get("status") or "UNANALYZED"
        self._row_status.set_value(status_display(status), color=status_palette(status)[0])

        # Integrity
        sha256 = file_data.get("sha256")
        self._row_sha256.set_value(sha256)
        self._row_sha256.value_label.setToolTip(sha256 or "")
        self._row_entropy.set_value(format_entropy(file_data.get("entropy")) if file_data.get("entropy") is not None else None)
        validation = file_data.get("validation_status") or "Not checked"
        self._row_validation.set_value(status_display(validation))

        # AI Recovery Analysis
        ai_class = file_data.get("relevance_class") or file_data.get("ai_classification") or "UNCERTAIN"
        rating_text = str(ai_class).replace("_RELEVANCE", "").title()
        self._row_ai_rating.set_value(rating_text, color=RELEVANCE_PALETTE.get(ai_class, COLORS["text_secondary"]))

        explanation = self._get_ai_explanation(ai_class, status, file_data)
        self._row_ai_explanation.set_value(explanation)

        # Recovery & Timeline
        fragments = file_data.get("fragments") or []
        frag_cnt = len(fragments) if fragments else (file_data.get("fragment_count") or 0)
        self._row_fragments_count.set_value(f"{frag_cnt} fragment(s)")

        reconstructions = file_data.get("reconstructions") or []
        if reconstructions:
            best = max(reconstructions, key=lambda r: r.get("confidence_score") or 0.0)
            self._row_reconstruction_state.set_value(
                f"{len(reconstructions)} candidate(s), best {status_display(best.get('status'))}",
                color=status_palette(best.get("status"))[0],
            )
        elif status in ("RECOVERED", "RECONSTRUCTED"):
            self._row_reconstruction_state.set_value("Reconstructed successfully", color=COLORS["accent_primary"])
        else:
            self._row_reconstruction_state.set_value("Available for reconstruction" if frag_cnt > 0 or status == "CORRUPTED" else "None")

        self.timeline_widget.set_fragments(fragments)

        # Button visibility
        output_path = file_data.get("output_path") or next((r.get("output_path") for r in reconstructions if r.get("output_path")), None)
        self.btn_open_recovered.setVisible(bool(output_path and Path(output_path).exists()))
        self.btn_reconstruct_file.setEnabled(status in ("CORRUPTED", "FRAGMENTED", "PARTIALLY_RECOVERABLE", "SUSPICIOUS") or frag_cnt > 0)

    @staticmethod
    def _get_ai_explanation(ai_class: str, status: str, file_data: Dict[str, Any]) -> str:
        if "HIGH" in ai_class:
            return "High recovery priority. Structural validation and fragment scoring indicate strong reconstruction potential."
        elif "MEDIUM" in ai_class:
            return "Moderate recovery priority. File contains recoverable data structures."
        elif "LOW" in ai_class:
            return "Lower recovery priority. File structural header intact or low fragmentation detected. AI prioritizes recovery focus."
        return "Uncertain relevance. Requires further fragment relationship evaluation."

    def clear_details(self):
        for row in (
            self._row_filename, self._row_path, self._row_type, self._row_size,
            self._row_status, self._row_sha256, self._row_entropy, self._row_validation,
            self._row_ai_rating, self._row_ai_explanation, self._row_fragments_count,
            self._row_reconstruction_state,
        ):
            row.set_value(None)
        self._current_file_data = None
        self.timeline_widget.set_fragments([])
        self.panel.clear("Select a file to view identity, integrity, and AI recovery details")

    def _on_analyze_file(self):
        if self._current_file_data:
            self.analyze_requested.emit(self._current_file_data)

    def _on_reconstruct_file(self):
        if self._current_file_data:
            self.reconstruct_requested.emit(self._current_file_data)

    def _on_open_recovered(self):
        if self._current_file_data:
            self.open_recovered_requested.emit(self._current_file_data)

    def _on_report_useful(self):
        if self._current_file_data:
            self.report_useful_requested.emit(self._current_file_data)


class AnalysisProgressPanel(QFrame):
    """Explicit analysis state panel."""

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


class ReconstructionFlowDialog(QDialog):
    """Step-by-step reconstruction dialog with real worker state progression."""

    def __init__(self, target_path: str, candidate_count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("File Reconstruction Workstation")
        self.setMinimumWidth(560)
        self._target_path = target_path
        self._payload: Optional[Dict[str, Any]] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        title = QLabel("Reconstruct File")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        fn = Path(target_path).name
        target_info = QLabel(f"Target: {fn}  │  Candidates: {candidate_count} file(s)")
        target_info.setObjectName("monoValue")
        layout.addWidget(target_info)

        self.step_widget = StepProgressWidget()
        layout.addWidget(self.step_widget)

        self.result_card = QFrame()
        self.result_card.setObjectName("card")
        res_layout = QVBoxLayout(self.result_card)
        res_layout.setContentsMargins(14, 12, 14, 12)
        res_layout.setSpacing(6)

        self.result_title = QLabel("RECOVERY RESULT")
        self.result_title.setObjectName("sectionTitle")
        res_layout.addWidget(self.result_title)

        self.result_details = QLabel("Reconstruction in progress...")
        self.result_details.setObjectName("bodyLabel")
        self.result_details.setWordWrap(True)
        res_layout.addWidget(self.result_details)

        self.result_card.hide()
        layout.addWidget(self.result_card)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)

        self.btn_open_file = make_button("Open Recovered File", self._on_open_file, variant="primary")
        self.btn_open_file.hide()
        btn_layout.addWidget(self.btn_open_file)

        self.btn_close = make_button("Close", self.accept, variant="secondary")
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    def update_stage(self, stage_idx: int):
        self.step_widget.set_step(stage_idx)

    def show_result(self, payload: Dict[str, Any]):
        self._payload = payload
        self.step_widget.set_step(5)
        self.result_card.show()

        status = payload.get("status") or "UNKNOWN"
        artifact = payload.get("artifact_path")
        confidence = payload.get("confidence")
        integrity = payload.get("integrity")
        artifact_size = payload.get("artifact_size")

        st_display = status_display(status)
        self.result_title.setText(f"RECOVERY RESULT: {st_display.upper()}")

        details_lines = [
            f"Artifact: {Path(artifact).name if artifact else 'None'}",
            f"Reconstructed Size: {format_size(artifact_size)}",
            f"Confidence Score: {format_score(confidence, 3)}",
            f"Integrity Score: {format_score(integrity, 3)}",
            f"Damaged Portions: {payload.get('damaged_portions', 0)}",
            f"Missing Portions: {payload.get('missing_portions', 0)}",
        ]

        insights = payload.get("insights") or []
        if insights:
            details_lines.append("\nFindings:")
            for line in insights[:4]:
                details_lines.append(f"• {line}")

        self.result_details.setText("\n".join(details_lines))

        if artifact and Path(artifact).exists():
            self.btn_open_file.show()

    def _on_open_file(self):
        if self._payload and self._payload.get("artifact_path"):
            path = self._payload["artifact_path"]
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))


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
        self._mode = "empty"

        self.recovered_page_ref = None

        super().__init__("Evidence", "No evidence source selected", parent=parent)
        self._setup_body()

    def _setup_body(self):
        self.btn_select_file = make_button(
            "Select File", self._on_analyze_single_clicked,
            variant="secondary",
            tooltip="Select and analyze a single desktop file",
        )
        self.btn_select_folder = make_button(
            "Select Folder", self._on_select_folder_clicked,
            variant="secondary",
            tooltip="Select an evidence folder to analyze",
        )
        self.btn_analyze = make_button(
            "Analyze", self._on_analyze_clicked,
            variant="primary",
            tooltip="Run evidence analysis over the selected evidence source",
        )
        self.btn_recover = make_button(
            "Reconstruct File", self._on_cross_recovery_clicked,
            variant="secondary",
            tooltip="Attempt cross-evidence reconstruction for the selected file",
        )

        for button in (
            self.btn_select_file,
            self.btn_select_folder,
            self.btn_analyze,
            self.btn_recover,
        ):
            self.add_header_widget(button)

        # Toolbar
        self.toolbar = Toolbar()
        self.count_label = QLabel("0 files")
        self.count_label.setObjectName("mutedLabel")
        self.toolbar.add_widget(self.count_label)

        self.source_chip = StatusChip("No selection", "UNANALYZED")
        self.toolbar.add_widget(self.source_chip)
        self.toolbar.add_spacer()

        # Status filter
        self.status_filter = QComboBox()
        for label, token in STATUS_FILTERS:
            self.status_filter.addItem(label, token)
        self.status_filter.setMinimumWidth(150)
        self.status_filter.currentIndexChanged.connect(self._on_filter_changed)
        self.toolbar.add_widget(self.status_filter)

        # AI Relevance filter
        self.relevance_filter = QComboBox()
        for label, token in AI_RELEVANCE_FILTERS:
            self.relevance_filter.addItem(label, token)
        self.relevance_filter.setMinimumWidth(140)
        self.relevance_filter.currentIndexChanged.connect(self._on_filter_changed)
        self.toolbar.add_widget(self.relevance_filter)

        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search evidence...")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setMaximumWidth(220)
        self.search_box.setMinimumWidth(140)
        self.search_box.textChanged.connect(self._on_search_changed)
        self.toolbar.add_widget(self.search_box)
        self.add_widget(self.toolbar)

        # Workspace stack
        self.workspace = QStackedWidget()

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(1)

        self.table = FileTableWidget()
        self.table.file_selected.connect(self._on_file_selected)
        self.splitter.addWidget(self.table)

        self.details_panel = FileDetailsPanel()
        self.details_panel.analyze_requested.connect(lambda f: self._analyze_single_file(f["path"]))
        self.details_panel.reconstruct_requested.connect(lambda f: self._start_reconstruction_for_file(f))
        self.details_panel.open_recovered_requested.connect(self._open_recovered_file)
        self.details_panel.report_useful_requested.connect(self._open_report_useful_dialog)
        self.splitter.addWidget(self.details_panel)

        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([860, 380])
        self.workspace.addWidget(self.splitter)

        # Empty State with direct action buttons
        self.empty_state_container = QWidget()
        empty_layout = QVBoxLayout(self.empty_state_container)
        empty_layout.setContentsMargins(32, 48, 32, 48)
        empty_layout.setSpacing(16)
        empty_layout.addStretch(1)

        self.empty_title = QLabel("No evidence source selected")
        self.empty_title.setObjectName("emptyStateTitle")
        self.empty_title.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self.empty_title)

        self.empty_hint = QLabel("Select a file or evidence folder to begin analysis.")
        self.empty_hint.setObjectName("emptyStateHint")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self.empty_hint)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch(1)

        btn_empty_file = make_button("Select File", self._on_analyze_single_clicked, variant="secondary")
        btn_empty_folder = make_button("Select Folder", self._on_select_folder_clicked, variant="primary")
        btn_row.addWidget(btn_empty_file)
        btn_row.addWidget(btn_empty_folder)
        btn_row.addStretch(1)

        empty_layout.addLayout(btn_row)
        empty_layout.addStretch(1)

        self.workspace.addWidget(self.empty_state_container)
        self.add_widget(self.workspace, 1)

        # Progress Panel
        self.progress_panel = AnalysisProgressPanel()
        self.add_widget(self.progress_panel)

        self.status_label = QLabel("Select a file or evidence folder to begin")
        self.status_label.setObjectName("pageSubtitle")
        self.status_label.setWordWrap(True)
        self.add_widget(self.status_label)

        self._update_button_states()
        self.workspace.setCurrentIndex(1)

    def refresh(self):
        """Keep current active selection; do not force auto-load if empty."""
        if self._mode == "folder" and self._evidence_folder:
            pass
        elif self._mode == "single" and self._files:
            pass
        else:
            self._mode = "empty"
            self.set_subtitle("No evidence source selected")
            self.source_chip.set_status("No selection", "UNANALYZED")
            self.workspace.setCurrentIndex(1)
            self._update_button_states()

    def set_folder_records(self, files: List[Dict[str, Any]], folder: str):
        self._mode = "folder"
        self._evidence_folder = folder
        self.source_chip.set_status("Folder scan", "PENDING")
        self.set_subtitle(folder)
        self._apply_records(files)

    def _apply_records(self, records: List[Dict[str, Any]]):
        self._files = list(records)
        self.table.set_files(self._files)
        self.count_label.setText(f"{len(self._files)} file(s)")
        self._update_button_states()
        self._apply_filter()

        visible = self._visible_count()
        if visible:
            self.workspace.setCurrentIndex(0)
            self.table.select_first()
        else:
            self.details_panel.clear_details()
            if self._files:
                self.empty_title.setText("No matching evidence found")
                self.empty_hint.setText("Clear search or filter options to view files.")
                self.workspace.setCurrentIndex(1)
            else:
                self.empty_title.setText("No evidence source selected")
                self.empty_hint.setText("Select a file or evidence folder to begin analysis.")
                self.workspace.setCurrentIndex(1)

    def _visible_count(self) -> int:
        count = 0
        for row in range(self.table.rowCount()):
            if not self.table.isRowHidden(row):
                count += 1
        return count

    # ----------------------------------------------------------------
    # Selection & Folder Discovery
    # ----------------------------------------------------------------

    def _on_select_folder_clicked(self):
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
        self._evidence_folder = folder_path
        SESSION.set_evidence_folder(folder_path)
        self.set_subtitle(folder_path)
        self._set_status("Discovering files...")
        self._update_button_states()
        QTimer.singleShot(0, lambda: self._discover_files(folder_path))

    def _discover_files(self, folder_path: str):
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
                    discovered.append({
                        "name": filename,
                        "path": file_path,
                        "rel_path": os.path.relpath(file_path, folder_path),
                        "size": size,
                        "type": extension[1:].upper() if extension else "UNKNOWN",
                        "sha256": self._calculate_sha256(file_path),
                        "detected_type": self._detect_type(file_path),
                        "mime_type": self._get_mime_type(extension[1:].lower()),
                        "entropy": None,
                        "status": "UNANALYZED",
                    })
        except Exception as exc:
            QMessageBox.critical(self, "Discovery Failed", f"Could not read folder:\n{exc}")
            self._set_status(f"Failed to discover files: {exc}")
            return

        self.set_folder_records(discovered, folder_path)
        self.folder_selected.emit(folder_path)
        SESSION.log_activity(f"Selected evidence folder {folder_path}")
        self._set_status(f"Discovered {len(discovered)} file(s)")

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
        if header.startswith(b"PK\x03\x04"):
            return "ZIP"
        if header.startswith(b"MZ"):
            return "PE Executable"
        if header.startswith(b"\x7fELF"):
            return "ELF Executable"
        if all(32 <= b <= 126 or b in (9, 10, 13) for b in header):
            return "Text"
        return "Binary"

    @staticmethod
    def _get_mime_type(ext: str) -> str:
        return {
            "pdf": "application/pdf",
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "txt": "text/plain",
            "zip": "application/zip",
            "py": "text/x-python",
        }.get(ext, "application/octet-stream")

    # ----------------------------------------------------------------
    # Filtering & Search
    # ----------------------------------------------------------------

    def _on_filter_changed(self):
        self._apply_filter()

    def _on_search_changed(self, text: str):
        self._apply_filter()

    def _apply_filter(self):
        status_token = self.status_filter.currentData()
        relevance_token = self.relevance_filter.currentData()
        needle = (self.search_box.text() or "").strip().lower()

        def keep(record):
            if status_token is not None and record.get("status") != status_token:
                return False
            rel_class = record.get("relevance_class") or record.get("ai_classification")
            if relevance_token is not None and rel_class != relevance_token:
                return False
            if not needle:
                return True
            haystack = " ".join(
                str(record.get(field) or "")
                for field in ("name", "path", "detected_type", "type", "sha256", "status")
            ).lower()
            return needle in haystack

        self.table.apply_filter(keep)
        visible = self._visible_count()
        if visible:
            self.workspace.setCurrentIndex(0)
        else:
            self.details_panel.clear_details()
            if self._files:
                self.empty_title.setText("No matching evidence found")
                self.empty_hint.setText("Clear search or filter options to view files.")
                self.workspace.setCurrentIndex(1)

    def _on_file_selected(self, file_data: Dict[str, Any]):
        self.details_panel.set_file_data(file_data)
        self._update_button_states()

    # ----------------------------------------------------------------
    # Single File & Analysis Workflow
    # ----------------------------------------------------------------

    def _on_analyze_single_clicked(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Evidence File",
            str(Path.home()),
            "All Files (*)",
        )
        if file_path:
            self._analyze_single_file(file_path)

    def _analyze_single_file(self, file_path: str):
        if self._is_busy():
            self._set_status("An analysis is already running")
            return

        name = os.path.basename(file_path)
        self._mode = "single"
        self.source_chip.set_status("Single File", "PENDING")
        self.set_subtitle(file_path)

        worker = SingleFileAnalysisWorker(file_path, SESSION.case_id)
        self._single_file_worker = worker
        worker.progress.connect(self._on_single_file_progress)
        worker.stage_changed.connect(self._on_analysis_stage)
        worker.completed.connect(self._on_single_file_completed)

        self.progress_panel.start(1, title="Analyzing file")
        self.progress_panel.set_counter(1, 1)
        self.progress_panel.set_current_file(name)
        self._set_status(f"Analyzing {name}")
        self._set_busy(True)
        worker.start()

    def _on_single_file_progress(self, message: str, percent: int):
        self._set_status(message)
        self.progress_panel.set_progress(percent)

    def _on_analysis_stage(self, stage_token: str, label: str):
        token = "COMPLETED" if stage_token == "completed" else "ANALYZING"
        self.progress_panel.set_stage(label, token)

    def _on_single_file_completed(self, success: bool, analysis_data: Dict[str, Any], error: str):
        self._set_busy(False)
        if not success:
            msg = f"Analysis failed: {error}"
            self.progress_panel.finish(False, msg)
            self._set_status(msg)
            QMessageBox.warning(self, "Analysis Failed", msg)
            return

        file_path = analysis_data.get("file_path", "")
        name = os.path.basename(file_path)
        file_info = analysis_data.get("file_info", {}) or {}

        merged = {
            "name": name,
            "path": file_path,
            "size": file_info.get("size"),
            "type": file_info.get("file_type") or "UNKNOWN",
            "sha256": file_info.get("sha256"),
            "detected_type": file_info.get("file_type"),
            "mime_type": file_info.get("mime_type"),
            "entropy": file_info.get("entropy"),
            "status": analysis_data.get("status"),
            "scan_id": analysis_data.get("scan_id"),
            "case_id": analysis_data.get("case_id"),
            "file_id": analysis_data.get("file_id"),
            "fragments": analysis_data.get("fragments", []),
            "reconstructions": analysis_data.get("reconstructions", []),
            "relationships": analysis_data.get("relationships", []),
            "fragment_count": len(analysis_data.get("fragments", [])),
        }

        relevance_scores = analysis_data.get("relevance_scores") or {}
        if relevance_scores:
            SESSION.set_scan(analysis_data.get("scan_id"))
            SESSION.record_relevance(analysis_data.get("scan_id"), relevance_scores)
            classes = [r.get("relevance_class") for r in relevance_scores.values()]
            for candidate in ("HIGH_RELEVANCE", "UNCERTAIN", "LOW_RELEVANCE"):
                if candidate in classes:
                    merged["relevance_class"] = candidate
                    break

        self.update_file_analysis(file_path, merged)
        self.progress_panel.finish(True, f"Analysis complete: {name}")
        self._set_status(f"Analysis complete: {name}")
        SESSION.log_activity(f"Analyzed {name}", "analysis")

    def _on_analyze_clicked(self):
        if self._is_busy():
            return
        if not self._evidence_folder:
            self._select_folder()
            return
        if not self._files:
            return

        self.analyze_requested.emit(self._evidence_folder)
        self.start_folder_analysis()

    def start_folder_analysis(self, case_id: str = None, case_name: str = "Evidence Analysis"):
        if not self._evidence_folder or not self._files:
            return
        if self._is_busy():
            return

        file_paths = [f["path"] for f in self._files if f.get("status") in (None, "UNANALYZED")]
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
        worker.progress.connect(self._on_single_file_progress)
        worker.stage_changed.connect(self._on_analysis_stage)
        worker.file_started.connect(self._on_file_started)
        worker.file_completed.connect(self.update_file_analysis)
        worker.file_failed.connect(lambda fp, err: self.update_file_analysis(fp, {"status": "ANALYSIS_FAILED", "error": err}))
        worker.analysis_complete.connect(self._on_folder_analysis_complete)

        self._total_files = len(file_paths)
        self._done_files = 0
        self.progress_panel.start(self._total_files)
        self._set_status("Analyzing evidence folder")
        self._set_busy(True)
        worker.start()

    def _on_file_started(self, file_path: str):
        self._done_files += 1
        self.progress_panel.set_counter(self._done_files, self._total_files)
        self.progress_panel.set_current_file(os.path.basename(file_path))

    def _on_folder_analysis_complete(self, success: bool, message: str):
        self._set_busy(False)
        self.progress_panel.finish(success, message)
        self._set_status(message)

    def update_file_analysis(self, file_path: str, analysis_data: Dict[str, Any]):
        target = None
        for record in self._files:
            if record.get("path") == file_path:
                target = record
                break

        if target is None:
            target = {"path": file_path, "name": os.path.basename(file_path)}
            self._files.append(target)

        for key, value in analysis_data.items():
            target[key] = value

        self._apply_records(self._files)
        self.table.select_by_path(file_path)

    # ----------------------------------------------------------------
    # Cross-Evidence Reconstruction Flow
    # ----------------------------------------------------------------

    def _on_cross_recovery_clicked(self):
        record = self.table.get_selected_file()
        if not record:
            self._set_status("Select a file to reconstruct")
            return
        self._start_reconstruction_for_file(record)

    def _start_reconstruction_for_file(self, record: Dict[str, Any]):
        if self._is_busy():
            return
        target = record.get("path")
        if not target or not Path(target).is_file():
            self._set_status("Target file is not readable")
            return

        evidence = [
            p for p in (other.get("path") for other in self._files if other is not record)
            if p and Path(p).is_file()
        ]
        if not evidence:
            self._set_status("No other evidence files available to reconstruct from")
            return

        from app.ui.data import reconstructed_root

        dialog = ReconstructionFlowDialog(target, len(evidence), self)
        
        worker = CrossEvidenceRecoveryWorker(
            target_path=target,
            evidence_paths=evidence,
            output_dir=str(reconstructed_root()),
        )
        self._recovery_worker = worker
        self._recovery_target = record

        def on_stage(token, label):
            stage_map = {"analyzing": 0, "evaluating": 1, "ordering": 2, "reconstructing": 3, "validating": 4, "complete": 5}
            dialog.update_stage(stage_map.get(token, 2))

        def on_complete(payload):
            self._set_busy(False)
            dialog.show_result(payload)
            self._persist_recovery(payload)
            if self.recovered_page_ref:
                try:
                    self.recovered_page_ref.refresh()
                except Exception:
                    pass

        worker.stage_changed.connect(on_stage)
        worker.completed.connect(on_complete)
        self._set_busy(True)
        worker.start()
        dialog.exec()

    def _persist_recovery(self, payload: Dict[str, Any]) -> Optional[str]:
        """Store a real artifact only: a file that exists and actually validated."""
        artifact = payload.get("artifact_path")
        if not artifact or not Path(artifact).is_file():
            return None

        raw_status = str(payload.get("status") or "")
        if raw_status == "RECONSTRUCTED":
            status = "RECONSTRUCTED"
        elif raw_status in ("PARTIALLY_RECONSTRUCTED", "PARTIALLY_RECOVERED"):
            status = "PARTIALLY_RECONSTRUCTED"
        else:
            # INTACT / NO_RELIABLE_RECONSTRUCTION / anything else is not an artifact.
            return None

        validation = payload.get("validation") or {}
        if raw_status == "RECONSTRUCTED" and not validation.get("structurally_valid"):
            # A full recovery must be backed by a successful validation.
            return None
        if raw_status == "PARTIALLY_RECONSTRUCTED" and not payload.get("recovered_portions"):
            # A partial artifact is only real when bytes were actually restored.
            return None

        record = self._recovery_target or {}
        scan_id = record.get("scan_id") or SESSION.scan_id
        if not scan_id:
            return None

        recovered = payload.get("recovered_portions") or []
        fragment_ids = [
            f"portion:{item.get('portion_index')}" for item in recovered if item.get("portion_index") is not None
        ]
        reconstruction_id = f"XREC_{uuid.uuid4().hex[:12]}"
        try:
            from app.storage.database import save_reconstruction
            save_reconstruction(
                reconstruction_id=reconstruction_id,
                scan_id=scan_id,
                fragment_ids=fragment_ids,
                integrity_score=float(payload.get("integrity") or 0.0),
                confidence_score=float(payload.get("confidence") or 0.0),
                evidence_quality="cross_evidence",
                priority="cross_evidence",
                status=status,
                output_path=str(artifact),
                output_sha256=payload.get("artifact_sha256"),
                output_size=payload.get("artifact_size"),
                output_entropy=validation.get("entropy"),
                output_file_type=validation.get("detected_type"),
                output_mime_type=validation.get("mime_type"),
                validation_status=validation.get("validation_status"),
                validation_details={
                    "source": "cross_evidence_recovery",
                    "target_path": payload.get("target_path"),
                    "target_sha256": payload.get("target_sha256"),
                    "detected_type": payload.get("detected_type"),
                    "expected_portions": payload.get("expected_portions"),
                    "intact_portions": payload.get("intact_portions"),
                    "damaged_portions": payload.get("damaged_portions"),
                    "missing_portions": payload.get("missing_portions"),
                    "missing_bytes": payload.get("missing_bytes"),
                    "recovered_portions": recovered,
                    "evidence": payload.get("evidence") or [],
                    "damage": payload.get("damage") or [],
                    "validation": validation,
                },
            )
        except Exception:
            return None
        return reconstruction_id

    def _open_recovered_file(self, file_data: Dict[str, Any]):
        reconstructions = file_data.get("reconstructions") or []
        output_path = file_data.get("output_path") or next((r.get("output_path") for r in reconstructions if r.get("output_path")), None)
        if output_path and Path(output_path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(output_path))
        else:
            QMessageBox.information(self, "Recovered File", "No recovered file artifact on disk yet.")

    def _open_report_useful_dialog(self, file_data: Dict[str, Any]):
        dialog = ReportAsUsefulDialog(file_data, self)
        dialog.exec()

    # ----------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------

    def _is_busy(self) -> bool:
        for worker in (self._analysis_worker, self._single_file_worker, self._recovery_worker):
            if worker is not None and worker.isRunning():
                return True
        return False

    def _update_button_states(self):
        busy = self._is_busy()
        selected = self.table.get_selected_file() is not None
        self.btn_select_file.setEnabled(not busy)
        self.btn_select_folder.setEnabled(not busy)
        self.btn_analyze.setEnabled(not busy and bool(self._files))
        self.btn_recover.setEnabled(not busy and selected)

    def _set_busy(self, busy: bool):
        self._update_button_states()

    def _set_status(self, message: str):
        self.status_label.setText(message)

    def get_evidence_folder(self) -> Optional[str]:
        return self._evidence_folder
