"""
ReConstructAI - Recovered Artifacts Page

Lists the artifacts that actually exist in `storage/reconstructed/`, i.e.
real recovery outputs rather than internal records. Metadata comes from the
artifact on disk, enriched with the reconstruction record that produced it
when the stored output hash matches.
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QLineEdit, QSplitter, QStackedWidget

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.ui import data as view
from app.ui.components import (
    DetailsPanel,
    EmptyState,
    ForensicTable,
    Page,
    StatusChip,
    Toolbar,
    format_datetime,
    format_entropy,
    format_offset,
    format_score,
    format_size,
    make_button,
    shorten_hash,
    status_display,
)


def caption_label(text: str):
    """Muted single-line caption used for counts and status text."""
    from PySide6.QtWidgets import QLabel

    label = QLabel(text)
    label.setObjectName("pageSubtitle")
    label.setWordWrap(True)
    return label


#: Same columns as before the refactor: what an artifact *is*, not internals.
RECOVERED_COLUMNS = [
    {
        "key": "name",
        "label": "Filename",
        "stretch": True,
        "kind": "text",
        "value": lambda r: (r.get("name"), "text"),
        "tooltip": lambda r: r.get("path") or r.get("name") or "",
    },
    {
        "key": "detected_type",
        "label": "Type",
        "width": 150,
        "kind": "text",
        "value": lambda r: (r.get("detected_type"), "text"),
    },
    {
        "key": "size",
        "label": "Size",
        "width": 100,
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
        "key": "sha256",
        "label": "SHA-256",
        "width": 190,
        "kind": "mono",
        "value": lambda r: (shorten_hash(r.get("sha256"), 10, 8), "mono"),
        "tooltip": lambda r: r.get("sha256") or "",
    },
    {
        "key": "confidence",
        "label": "Confidence",
        "width": 105,
        "kind": "center",
        "value": lambda r: (format_score(r.get("confidence"), 2), "center"),
        "tooltip": "Stored confidence for the reconstruction that produced this file",
    },
    {
        "key": "path",
        "label": "Path",
        "stretch": True,
        "kind": "mono",
        "value": lambda r: (r.get("path"), "mono"),
    },
]


class RecoveredPage(Page):
    """Recovered artifacts workspace."""

    def __init__(self, parent=None):
        super().__init__("Recovered Artifacts", "No recovered artifacts", parent=parent)
        self._artifacts: List[Dict[str, Any]] = []
        self._setup_body()

    def _setup_body(self):
        self.btn_refresh = make_button(
            "Refresh",
            self.refresh,
            variant="secondary",
            tooltip="Re-read storage/reconstructed",
        )
        self.add_header_widget(self.btn_refresh)

        self.toolbar = Toolbar()
        self.count_label = caption_label("0 artifacts")
        self.toolbar.add_widget(self.count_label)

        self.link_chip = StatusChip("No linked records", "UNANALYZED")
        self.link_chip.setToolTip(
            "Artifacts whose hash matches a stored reconstruction record"
        )
        self.toolbar.add_widget(self.link_chip)
        self.toolbar.add_spacer()

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search artifacts")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setMaximumWidth(240)
        self.search_box.setMinimumWidth(150)
        self.search_box.textChanged.connect(self._on_search_changed)
        self.toolbar.add_widget(self.search_box)
        self.add_widget(self.toolbar)

        self.workspace = QStackedWidget()

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(1)

        self.table = ForensicTable(RECOVERED_COLUMNS, object_name="dataTable")
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.splitter.addWidget(self.table)

        self.details = DetailsPanel("Artifact Details")
        self.details.clear("Select an artifact to view how it was recovered")
        self.splitter.addWidget(self.details)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([860, 380])
        self.workspace.addWidget(self.splitter)

        self.empty_state = EmptyState(
            "No recovered artifacts yet",
            "Reconstructed artifacts are written to storage/reconstructed.",
        )
        self.workspace.addWidget(self.empty_state)
        self.add_widget(self.workspace, 1)

        self.status_label = caption_label("")
        self.add_widget(self.status_label)

        self.workspace.setCurrentIndex(1)
        self.refresh()

    # ----------------------------------------------------------------
    # Data
    # ----------------------------------------------------------------

    def refresh(self):
        """Re-read the reconstructed artifact directory."""
        try:
            records = view.recovered_artifact_records()
        except Exception as exc:
            self._artifacts = []
            self.status_label.setText(f"Could not read recovered artifacts: {exc}")
            self._render()
            return

        self._artifacts = records
        self._render()

        root = view.reconstructed_root()
        if not records:
            self.status_label.setText(f"Output directory: {root}")
        else:
            self.status_label.setText(f"{len(records)} artifact(s) in {root}")

    def _render(self):
        self.table.set_records(self._artifacts)
        self.count_label.setText(f"{len(self._artifacts)} artifacts")

        linked = sum(1 for record in self._artifacts if record.get("linked"))
        if not self._artifacts:
            self.link_chip.set_status("No linked records", "UNANALYZED")
        elif linked:
            self.link_chip.set_status(f"{linked} linked", "RECOVERED")
        else:
            self.link_chip.set_status("Unlinked on disk", "UNANALYZED")

        self._on_search_changed(self.search_box.text())
        if not self._artifacts:
            self.empty_state.set_state(
                "No recovered artifacts yet",
                "Reconstructed artifacts are written to storage/reconstructed.",
            )
        else:
            self.table.select_first()
        self.workspace.setCurrentIndex(0 if self.table.rowCount() else 1)

    def _on_selection_changed(self):
        record = self.table.current_record()
        if not record:
            self.details.clear("Select an artifact to view how it was recovered")
            return

        identity = self.details.section("identity", "Artifact")
        identity.add_row("Name", record.get("name"))
        identity.add_row("Path", record.get("path"), mono=True)
        identity.add_row("Size", format_size(record.get("size")))
        identity.add_row("SHA-256", shorten_hash(record.get("sha256"), 16, 12), mono=True)
        identity.add_row("Type", record.get("detected_type"))
        identity.add_row("MIME", record.get("mime_type"))
        identity.add_row("Modified", format_datetime(record.get("modified")))

        recovery = self.details.section("recovery", "Recovery")
        recovery.add_row("Status", status_display(record.get("status")))
        recovery.add_row("Confidence", format_score(record.get("confidence")))
        recovery.add_row("Integrity", format_score(record.get("integrity")))
        recovery.add_row("Validation", record.get("validation_status"))
        recovery.add_row("Entropy", format_entropy(record.get("entropy")))
        recovery.add_row("Case", record.get("case_name"))
        recovery.add_row("Scan", record.get("scan_id"), mono=True)
        recovery.add_row(
            "Reconstruction", record.get("reconstruction_id"), mono=True
        )
        if not record.get("linked"):
            recovery.add_row(
                "Provenance",
                "No stored reconstruction matches this file's hash; it was "
                "recovered but not recorded against a scan.",
            )

        details = self._cross_recovery_details(record)
        if details:
            findings = self.details.section("findings", "Recovery findings")
            for line in (details.get("insights") or [])[:6]:
                findings.add_row("", line)

            damage = details.get("damage") or []
            if damage:
                damage_section = self.details.section("damage", "Damage found")
                for finding in damage[:5]:
                    damage_section.add_row(
                        str(finding.get("kind")),
                        f"offset {format_offset(finding.get('offset'))}, "
                        f"length {finding.get('length')}",
                        mono=True,
                    )

            portions = details.get("portions") or []
            if portions:
                recovered = [p for p in portions if p.get("state") == "RECOVERED"]
                portion_section = self.details.section("portions", "Portions")
                portion_section.add_row("Total", str(len(portions)))
                portion_section.add_row("Recovered from evidence", str(len(recovered)))

    def _cross_recovery_details(self, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Stored cross-recovery detail for a linked artifact, if any."""
        details = record.get("validation_details")
        if isinstance(details, dict) and details.get("source") == "cross_evidence_recovery":
            return details
        return None

    def _on_search_changed(self, text: str):
        self.table.apply_search(text)
        if not self.table.rowCount() and self._artifacts:
            self.empty_state.set_state(
                "No artifacts match the search",
                "Clear the search to see every recovered artifact.",
            )
        elif self._artifacts:
            self.empty_state.set_state(
                "No recovered artifacts yet",
                "Reconstructed artifacts are written to storage/reconstructed.",
            )
        self.workspace.setCurrentIndex(0 if self.table.rowCount() else 1)

    # ----------------------------------------------------------------
    # Access
    # ----------------------------------------------------------------

    def artifacts(self) -> List[Dict[str, Any]]:
        return list(self._artifacts)

    def get_recovered_files(self) -> List[str]:
        """Paths of every artifact currently listed."""
        return [record["path"] for record in self._artifacts if record.get("path")]
