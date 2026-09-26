"""
ReConstructAI - Recovered Artifacts Page

Displays ONLY actual reconstruction artifacts (RECOVERED or PARTIALLY RECOVERED)
that have been successfully generated and validated.
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

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
    label = QLabel(text)
    label.setObjectName("pageSubtitle")
    label.setWordWrap(True)
    return label


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
        "width": 110,
        "kind": "text",
        "value": lambda r: (r.get("detected_type") or "Unknown", "text"),
    },
    {
        "key": "size",
        "label": "Recovered Size",
        "width": 110,
        "kind": "size",
        "value": lambda r: (format_size(r.get("size")), "size"),
    },
    {
        "key": "integrity",
        "label": "Integrity",
        "width": 95,
        "kind": "center",
        "value": lambda r: (format_score(r.get("integrity"), 2), "center"),
    },
    {
        "key": "validation_status",
        "label": "Validation",
        "width": 120,
        "kind": "center",
        "value": lambda r: (status_display(r.get("validation_status")), "center"),
    },
    {
        "key": "fragments_used",
        "label": "Fragments Used",
        "width": 115,
        "kind": "center",
        "value": lambda r: (str(r.get("fragment_count", 0)), "center"),
    },
    {
        "key": "confidence",
        "label": "Confidence",
        "width": 100,
        "kind": "center",
        "value": lambda r: (format_score(r.get("confidence"), 2), "center"),
    },
    {
        "key": "status",
        "label": "Status",
        "width": 140,
        "kind": "center",
        "value": lambda r: (status_display(r.get("status")), "center"),
    },
]


class RecoveredPage(Page):
    """Recovered artifacts workspace."""

    view_evidence_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(
            "Recovered Files",
            "Artifacts successfully reconstructed from available evidence.",
            parent=parent,
        )
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

        self.link_chip = StatusChip("Recovered Artifacts", "RECOVERED")
        self.toolbar.add_widget(self.link_chip)
        self.toolbar.add_spacer()

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search recovered artifacts...")
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
        self.details.clear("Select a recovered artifact to view identity and validation metrics")
        self.splitter.addWidget(self.details)

        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([860, 380])
        self.workspace.addWidget(self.splitter)

        # Custom Empty State with View Evidence button
        self.empty_container = QWidget()
        empty_layout = QVBoxLayout(self.empty_container)
        empty_layout.setContentsMargins(32, 48, 32, 48)
        empty_layout.setSpacing(16)
        empty_layout.addStretch(1)

        self.empty_title = QLabel("No recovered artifacts")
        self.empty_title.setObjectName("emptyStateTitle")
        self.empty_title.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self.empty_title)

        self.empty_hint = QLabel("No file has been successfully reconstructed from the available evidence.")
        self.empty_hint.setObjectName("emptyStateHint")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self.empty_hint)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_view_ev = make_button("View Evidence", self.view_evidence_requested.emit, variant="primary")
        btn_row.addWidget(btn_view_ev)
        btn_row.addStretch(1)

        empty_layout.addLayout(btn_row)
        empty_layout.addStretch(1)

        self.workspace.addWidget(self.empty_container)
        self.add_widget(self.workspace, 1)

        self.status_label = caption_label("")
        self.add_widget(self.status_label)

        self.workspace.setCurrentIndex(1)
        self.refresh()

    def refresh(self):
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
            self.status_label.setText("No file has been successfully reconstructed yet.")
        else:
            self.status_label.setText(f"{len(records)} artifact(s) reconstructed in {root}")

    def _render(self):
        self.table.set_records(self._artifacts)
        self.count_label.setText(f"{len(self._artifacts)} artifacts")

        if self._artifacts:
            self.link_chip.set_status(f"{len(self._artifacts)} recovered", "RECOVERED")
        else:
            self.link_chip.set_status("No artifacts", "UNANALYZED")

        self._on_search_changed(self.search_box.text())
        if self._artifacts and self.table.rowCount() > 0:
            self.table.select_first()
            self.workspace.setCurrentIndex(0)
        else:
            self.workspace.setCurrentIndex(1)

    def _on_selection_changed(self):
        record = self.table.current_record()
        if not record:
            self.details.clear("Select an artifact to view details")
            return

        identity = self.details.section("identity", "Artifact Identity")
        identity.add_row("Name", record.get("name"))
        identity.add_row("Path", record.get("path"), mono=True)
        identity.add_row("Recovered Size", format_size(record.get("size")))
        identity.add_row("SHA-256", shorten_hash(record.get("sha256"), 16, 12), mono=True)
        identity.add_row("Type", record.get("detected_type"))
        identity.add_row("MIME", record.get("mime_type"))
        identity.add_row("Modified", format_datetime(record.get("modified")))

        recovery = self.details.section("recovery", "Reconstruction Metrics")
        recovery.add_row("Status", status_display(record.get("status")))
        recovery.add_row("Confidence", format_score(record.get("confidence")))
        recovery.add_row("Integrity", format_score(record.get("integrity")))
        recovery.add_row("Validation", record.get("validation_status"))
        recovery.add_row("Fragments Used", str(record.get("fragment_count", 0)))
        recovery.add_row("Case", record.get("case_name"))
        recovery.add_row("Reconstruction ID", record.get("reconstruction_id"), mono=True)

    def _on_search_changed(self, text: str):
        self.table.apply_search(text)
        if not self.table.rowCount() and self._artifacts:
            self.empty_title.setText("No matching recovered artifacts")
            self.empty_hint.setText("Clear the search to view all recovered artifacts.")
            self.workspace.setCurrentIndex(1)
        elif not self._artifacts:
            self.empty_title.setText("No recovered artifacts")
            self.empty_hint.setText("No file has been successfully reconstructed from the available evidence.")
            self.workspace.setCurrentIndex(1)
        else:
            self.workspace.setCurrentIndex(0)

    def artifacts(self) -> List[Dict[str, Any]]:
        return list(self._artifacts)

    def get_recovered_files(self) -> List[str]:
        return [record["path"] for record in self._artifacts if record.get("path")]
