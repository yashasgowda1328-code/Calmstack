"""
ReConstructAI - Fragments Page

Fragment-level view of the evidence already stored by the engine. Rows come
from the shared read-only view layer, so fragment counts, relationship scores
and file status are the values the engine actually persisted, and the live AI
relevance from the current session is shown when it exists.
"""

import os
import sys
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit, QSplitter, QStackedWidget

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.ui import data as view
from app.ui.components import (
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
    status_display,
    shorten_hash,
)
from app.ui.session import SESSION


FRAGMENT_COLUMNS = [
    {
        "key": "fragment_id",
        "label": "Fragment",
        "width": 170,
        "kind": "mono",
        "value": lambda r: (r.get("fragment_id"), "mono"),
        "tooltip": lambda r: r.get("sha256") or "",
    },
    {
        "key": "file_name",
        "label": "File",
        "stretch": True,
        "kind": "text",
        "value": lambda r: (r.get("file_name"), "text"),
    },
    {
        "key": "offset",
        "label": "Offset",
        "width": 110,
        "kind": "mono",
        "value": lambda r: (format_offset(r.get("offset")), "mono"),
    },
    {
        "key": "size",
        "label": "Size",
        "width": 96,
        "kind": "size",
        "value": lambda r: (format_size(r.get("size")), "size"),
    },
    {
        "key": "entropy",
        "label": "Entropy",
        "width": 90,
        "kind": "center",
        "value": lambda r: (format_entropy(r.get("entropy")), "center"),
    },
    {
        "key": "file_status",
        "label": "File Status",
        "width": 150,
        "kind": "center",
        "value": lambda r: (status_display(r.get("file_status")), "center"),
    },
    {
        "key": "relevance_score",
        "label": "AI Relevance",
        "width": 110,
        "kind": "center",
        "value": lambda r: (format_score(r.get("relevance_score"), 2), "center"),
        "tooltip": "Live relevance from the current session; not persisted to SQLite.",
    },
    {
        "key": "relationship_count",
        "label": "Links",
        "width": 70,
        "kind": "center",
        "value": lambda r: (r.get("relationship_count"), "center"),
        "tooltip": lambda r: (
            f"Best relationship score: {format_score(r.get('max_relationship_score'), 3)}"
        ),
    },
]


class FragmentsPage(Page):
    """Fragment-level view for a selectable scan."""

    def __init__(self, parent=None):
        self._inventory = None
        self._records: List[Dict[str, Any]] = []
        self._scan_id: Optional[str] = None
        self._scans: List[Dict[str, Any]] = []
        super().__init__(
            "Fragments",
            "Fragment evidence stored for the selected scan",
            parent=parent,
        )
        self._setup_body()

    # ----------------------------------------------------------------
    # Construction
    # ----------------------------------------------------------------

    def _setup_body(self):
        self.btn_refresh = make_button(
            "Refresh",
            self.refresh,
            variant="secondary",
            tooltip="Re-read fragments from the database",
        )
        self.add_header_widget(self.btn_refresh)

        self.toolbar = Toolbar()
        self.count_label = QLabel("0 fragments")
        self.count_label.setObjectName("mutedLabel")
        self.toolbar.add_widget(self.count_label)

        self.relevance_chip = StatusChip("No live relevance", "UNANALYZED")
        self.relevance_chip.setToolTip(
            "AI relevance is produced by a live run and is not stored in SQLite"
        )
        self.toolbar.add_widget(self.relevance_chip)
        self.toolbar.add_spacer()

        self.scan_label = QLabel("Scan")
        self.scan_label.setObjectName("mutedLabel")
        self.toolbar.add_widget(self.scan_label)

        self.scan_box = QComboBox()
        self.scan_box.setMinimumWidth(280)
        self.scan_box.setToolTip("Choose which stored scan to inspect")
        self.scan_box.currentIndexChanged.connect(self._on_scan_changed)
        self.toolbar.add_widget(self.scan_box)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search fragments")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setMaximumWidth(220)
        self.search_box.setMinimumWidth(140)
        self.search_box.textChanged.connect(self._on_search_changed)
        self.toolbar.add_widget(self.search_box)
        self.add_widget(self.toolbar)

        self.workspace = QStackedWidget()

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(1)

        self.table = ForensicTable(FRAGMENT_COLUMNS, object_name="dataTable")
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.splitter.addWidget(self.table)

        self.details = self._build_details()
        self.splitter.addWidget(self.details)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([860, 360])
        self.workspace.addWidget(self.splitter)

        self.empty_state = EmptyState(
            "No fragments available",
            "Fragments appear here once an evidence analysis has stored them.",
        )
        self.workspace.addWidget(self.empty_state)
        self.add_widget(self.workspace, 1)

        self.status_label = QLabel("")
        self.status_label.setObjectName("pageSubtitle")
        self.status_label.setWordWrap(True)
        self.add_widget(self.status_label)

        self.workspace.setCurrentIndex(1)
        self.refresh()

    def _build_details(self):
        from app.ui.components import DetailsPanel

        panel = DetailsPanel("Fragment Details")
        panel.clear("Select a fragment to view its stored evidence")
        return panel

    # ----------------------------------------------------------------
    # Data
    # ----------------------------------------------------------------

    def refresh(self):
        """Reload scans and fragments from the database."""
        self._inventory = view.load_inventory()
        self._scans = view.scan_summaries(self._inventory)

        self._reload_scan_choices()
        self._reload_fragments()

    def _reload_scan_choices(self):
        previous = self._scan_id
        self.scan_box.blockSignals(True)
        self.scan_box.clear()

        for summary in self._scans:
            label = (
                f"{summary['scan_id']}  -  {summary.get('file_name') or 'no file'}  -  "
                f"{summary.get('fragment_count', 0)} fragments"
            )
            self.scan_box.addItem(label, summary.get("scan_id"))

        target = None
        if previous and any(s.get("scan_id") == previous for s in self._scans):
            target = previous
        elif SESSION.scan_id and any(s.get("scan_id") == SESSION.scan_id for s in self._scans):
            target = SESSION.scan_id
        elif self._scans:
            target = self._scans[0].get("scan_id")

        if target:
            index = self.scan_box.findData(target)
            if index >= 0:
                self.scan_box.setCurrentIndex(index)
        self.scan_box.blockSignals(False)
        self._scan_id = self.scan_box.currentData()

    def _reload_fragments(self):
        self._scan_id = self.scan_box.currentData()
        if not self._scan_id:
            self._records = []
        else:
            try:
                self._records = view.fragment_records(self._inventory, self._scan_id)
            except Exception as exc:
                self._records = []
                self.status_label.setText(f"Could not read fragments: {exc}")

        self._render()

    def records(self) -> List[Dict[str, Any]]:
        return list(self._records)

    # ----------------------------------------------------------------
    # Rendering
    # ----------------------------------------------------------------

    def _render(self):
        self.table.set_records(self._records)
        self.count_label.setText(f"{len(self._records)} fragments")

        scored = sum(1 for r in self._records if r.get("relevance_score") is not None)
        if scored:
            self.relevance_chip.set_status(
                f"Live relevance for {scored}", "COMPLETED"
            )
        else:
            self.relevance_chip.set_status("No live relevance", "UNANALYZED")

        summary = next(
            (s for s in self._scans if s.get("scan_id") == self._scan_id), None
        )
        if summary:
            self.set_subtitle(
                f"{summary['scan_id']}  -  {summary.get('file_name') or 'no file'}"
            )
            self.status_label.setText(
                f"{summary.get('fragment_count', 0)} fragments, "
                f"{summary.get('relationship_count', 0)} relationships, "
                f"{summary.get('reconstruction_count', 0)} reconstructions, "
                f"scan status {summary.get('status') or 'unknown'}, "
                f"{format_datetime(summary.get('created_at'))}"
            )
        else:
            self.status_label.setText("No scan is selected.")

        self._on_search_changed(self.search_box.text())
        self.workspace.setCurrentIndex(0 if self.table.rowCount() else 1)
        if not self._records:
            self.empty_state.set_state(
                "No fragments for this scan",
                "Choose another stored scan, or run an evidence analysis.",
            )
        else:
            self.table.select_first()

    # ----------------------------------------------------------------
    # Interaction
    # ----------------------------------------------------------------

    def _on_scan_changed(self, _index: int):
        self._reload_fragments()

    def _on_search_changed(self, text: str):
        self.table.apply_search(text)
        self.workspace.setCurrentIndex(0 if self.table.rowCount() else 1)

    def _on_selection_changed(self):
        record = self.table.current_record()
        if not record:
            self.details.clear("Select a fragment to view its stored evidence")
            return

        self.details.clear()
        identity = self.details.section("identity", "Identity")
        identity.add_row("Fragment", record.get("fragment_id"), mono=True)
        identity.add_row("File", record.get("file_name"))
        identity.add_row("Scan", record.get("scan_id"), mono=True)
        identity.add_row("SHA-256", shorten_hash(record.get("sha256"), 16, 12), mono=True)

        metrics = self.details.section("metrics", "Content")
        metrics.add_row("Offset", format_offset(record.get("offset")), mono=True)
        metrics.add_row("Size", format_size(record.get("size")))
        metrics.add_row("Entropy", format_entropy(record.get("entropy")))

        evidence = self.details.section("evidence", "Evidence")
        evidence.add_row("File status", status_display(record.get("file_status")))
        evidence.add_row(
            "Relationships",
            f"{record.get('relationship_count', 0)}"
            f"  (best {format_score(record.get('max_relationship_score'))})",
        )
        evidence.add_row("AI relevance", format_score(record.get("relevance_score")))
        evidence.add_row("Relevance class", record.get("relevance_class"))

        stats = record.get("byte_stats")
        if isinstance(stats, dict) and stats:
            byte_section = self.details.section("bytes", "Byte statistics")
            for key in ("unique_bytes", "null_bytes", "max_byte_freq", "avg_byte_freq"):
                if key in stats:
                    byte_section.add_row(
                        key.replace("_", " ").title(), str(stats[key]), mono=True
                    )
