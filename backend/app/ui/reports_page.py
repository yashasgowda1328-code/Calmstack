"""
ReConstructAI - Reports Page

Recovery summary built from the shared read-only view layer: one metric row for
the whole dataset, one row per stored scan with its real counts, and the
reports and feedback the engine actually stored. No value here is computed
from a second, private query path.
"""

import os
import sys
from typing import Any, Dict, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QStackedWidget, QTabWidget, QVBoxLayout, QWidget

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.ui import data as view
from app.ui.components import (
    EmptyState,
    ForensicTable,
    MetricBlock,
    Page,
    SectionCard,
    StatusChip,
    Toolbar,
    format_datetime,
    format_score,
    format_size,
    make_button,
    status_display,
    shorten_hash,
)


SCAN_COLUMNS = [
    {
        "key": "scan_id",
        "label": "Scan",
        "width": 190,
        "kind": "mono",
        "value": lambda r: (r.get("scan_id"), "mono"),
    },
    {
        "key": "case_name",
        "label": "Case",
        "width": 170,
        "kind": "text",
        "value": lambda r: (r.get("case_name"), "text"),
    },
    {
        "key": "file_name",
        "label": "Evidence Source",
        "stretch": True,
        "kind": "text",
        "value": lambda r: (r.get("file_name"), "text"),
    },
    {
        "key": "file_count",
        "label": "Files",
        "width": 70,
        "kind": "center",
        "value": lambda r: (r.get("file_count"), "center"),
    },
    {
        "key": "fragment_count",
        "label": "Fragments",
        "width": 90,
        "kind": "center",
        "value": lambda r: (r.get("fragment_count"), "center"),
    },
    {
        "key": "relationship_count",
        "label": "Links",
        "width": 70,
        "kind": "center",
        "value": lambda r: (r.get("relationship_count"), "center"),
    },
    {
        "key": "reconstruction_count",
        "label": "Candidates",
        "width": 95,
        "kind": "center",
        "value": lambda r: (r.get("reconstruction_count"), "center"),
    },
    {
        "key": "best_confidence",
        "label": "Best Confidence",
        "width": 110,
        "kind": "center",
        "value": lambda r: (format_score(r.get("best_confidence"), 2), "center"),
    },
    {
        "key": "status",
        "label": "Scan Status",
        "width": 130,
        "kind": "center",
        "value": lambda r: (status_display(r.get("status")), "center"),
    },
    {
        "key": "created_at",
        "label": "Created",
        "width": 140,
        "kind": "center",
        "value": lambda r: (format_datetime(r.get("created_at")), "center"),
    },
]


REPORT_COLUMNS = [
    {
        "key": "filename",
        "label": "Evidence",
        "stretch": True,
        "kind": "text",
        "value": lambda r: (r.get("filename"), "text"),
        "tooltip": lambda r: r.get("file_path") or r.get("filename") or "",
    },
    {
        "key": "report_type",
        "label": "Type",
        "width": 130,
        "kind": "text",
        "value": lambda r: (r.get("report_type"), "text"),
    },
    {
        "key": "case_name",
        "label": "Case",
        "width": 170,
        "kind": "text",
        "value": lambda r: (r.get("case_name"), "text"),
    },
    {
        "key": "relevance_score",
        "label": "Relevance",
        "width": 100,
        "kind": "center",
        "value": lambda r: (format_score(r.get("relevance_score"), 2), "center"),
    },
    {
        "key": "ai_classification",
        "label": "AI Class",
        "width": 150,
        "kind": "center",
        "value": lambda r: (r.get("ai_classification"), "center"),
    },
    {
        "key": "report_status",
        "label": "Status",
        "width": 120,
        "kind": "center",
        "value": lambda r: (status_display(r.get("report_status")), "center"),
    },
    {
        "key": "user_reason",
        "label": "Investigator Note",
        "stretch": True,
        "kind": "text",
        "value": lambda r: (r.get("user_reason"), "text"),
    },
    {
        "key": "created_at",
        "label": "Created",
        "width": 140,
        "kind": "center",
        "value": lambda r: (format_datetime(r.get("created_at")), "center"),
    },
]


CANDIDATE_COLUMNS = [
    {
        "key": "reconstruction_id",
        "label": "Reconstruction",
        "width": 200,
        "kind": "mono",
        "value": lambda r: (r.get("reconstruction_id"), "mono"),
    },
    {
        "key": "scan_id",
        "label": "Scan",
        "width": 180,
        "kind": "mono",
        "value": lambda r: (r.get("scan_id"), "mono"),
    },
    {
        "key": "status",
        "label": "Status",
        "width": 165,
        "kind": "center",
        "value": lambda r: (status_display(r.get("status")), "center"),
    },
    {
        "key": "fragment_count",
        "label": "Fragments",
        "width": 90,
        "kind": "center",
        "value": lambda r: (r.get("fragment_count"), "center"),
    },
    {
        "key": "integrity",
        "label": "Integrity",
        "width": 95,
        "kind": "center",
        "value": lambda r: (format_score(r.get("integrity"), 2), "center"),
    },
    {
        "key": "confidence",
        "label": "Confidence",
        "width": 105,
        "kind": "center",
        "value": lambda r: (format_score(r.get("confidence"), 2), "center"),
    },
    {
        "key": "output_size",
        "label": "Output Size",
        "width": 100,
        "kind": "size",
        "value": lambda r: (format_size(r.get("output_size")), "size"),
    },
    {
        "key": "output_sha256",
        "label": "Output SHA-256",
        "width": 190,
        "kind": "mono",
        "value": lambda r: (shorten_hash(r.get("output_sha256"), 10, 8), "mono"),
        "tooltip": lambda r: r.get("output_sha256") or "",
    },
    {
        "key": "validation_status",
        "label": "Validation",
        "stretch": True,
        "kind": "text",
        "value": lambda r: (r.get("validation_status"), "text"),
    },
]


class ReportsPage(Page):
    """Recovery summary backed entirely by real stored results."""

    def __init__(self, parent=None):
        self._inventory = None
        self._metrics: Dict[str, Any] = {}
        self._scans: List[Dict[str, Any]] = []
        self._candidates: List[Dict[str, Any]] = []
        self._reports: List[Dict[str, Any]] = []
        super().__init__(
            "Reports",
            "Recovery summary from stored scans, candidates and reports",
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
            tooltip="Re-read the stored results",
        )
        self.add_header_widget(self.btn_refresh)

        self.toolbar = Toolbar()
        self.count_label = QLabel("0 scans")
        self.count_label.setObjectName("mutedLabel")
        self.toolbar.add_widget(self.count_label)

        self.candidate_chip = StatusChip("0 candidates", "UNANALYZED")
        self.candidate_chip.setToolTip("Reconstruction candidates stored in the database")
        self.toolbar.add_widget(self.candidate_chip)

        self.report_chip = StatusChip("0 reports", "UNANALYZED")
        self.report_chip.setToolTip("Recovery reports and investigator feedback")
        self.toolbar.add_widget(self.report_chip)
        self.toolbar.add_spacer()
        self.add_widget(self.toolbar)

        self.metrics_card = SectionCard("Investigation Summary")
        self._blocks: Dict[str, MetricBlock] = {}
        for key, label, hint in (
            ("cases", "Cases", "Stored investigations"),
            ("scans", "Scans", "Completed and running"),
            ("files", "Files", "Analyzed evidence"),
            ("fragments", "Fragments", "Fixed-size portions"),
            ("candidates", "Candidates", "Reconstructions"),
            ("artifacts", "Artifacts", "Files on disk"),
        ):
            block = MetricBlock(label, "0", hint)
            self._blocks[key] = block
            self.metrics_card.body_layout().addWidget(block)
        self.add_widget(self.metrics_card)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("contentTabs")

        self.tabs.addTab(self._build_table_tab(SCAN_COLUMNS, "scans"), "Scans")
        self.tabs.addTab(self._build_table_tab(CANDIDATE_COLUMNS, "candidates"), "Candidates")
        self.tabs.addTab(self._build_table_tab(REPORT_COLUMNS, "reports"), "Reports")
        self.add_widget(self.tabs, 1)

        self.status_label = QLabel("")
        self.status_label.setObjectName("pageSubtitle")
        self.status_label.setWordWrap(True)
        self.add_widget(self.status_label)

        self.refresh()

    def _build_table_tab(self, columns, key: str) -> QWidget:
        tab = QWidget()
        stack = QStackedWidget()

        table = ForensicTable(columns, object_name="dataTable")
        stack.addWidget(table)

        empty = EmptyState(
            "No stored data",
            "Run an evidence analysis to populate this report.",
        )
        stack.addWidget(empty)

        holder = QWidget()
        holder_layout = QVBoxLayout(holder)
        holder_layout.setContentsMargins(0, 0, 0, 0)
        holder_layout.addWidget(stack)

        tab.setLayout(holder_layout)
        setattr(self, f"_{key}_table", table)
        setattr(self, f"_{key}_empty", empty)
        setattr(self, f"_{key}_stack", stack)
        return tab

    # ----------------------------------------------------------------
    # Data
    # ----------------------------------------------------------------

    def refresh(self):
        self._inventory = view.load_inventory()
        try:
            self._metrics = view.dataset_metrics(self._inventory)
        except Exception as exc:
            self._metrics = {}
            self.status_label.setText(f"Could not compute metrics: {exc}")

        self._scans = view.scan_summaries(self._inventory)
        self._candidates = view.reconstruction_records(self._inventory)
        self._reports = view.report_records(self._inventory)

        self._render_metrics()
        self._render_table("scans", self._scans)
        self._render_table("candidates", self._candidates)
        self._render_table("reports", self._reports)
        self._render_status()

    def _render_metrics(self):
        for key, block in self._blocks.items():
            value = self._metrics.get(key, 0)
            block.set_value(value if value is not None else 0)

    def _render_table(self, key: str, records: List[Dict[str, Any]]):
        table = getattr(self, f"_{key}_table")
        empty = getattr(self, f"_{key}_empty")
        stack = getattr(self, f"_{key}_stack")
        table.set_records(records)
        stack.setCurrentIndex(0 if table.rowCount() else 1)

    def _render_status(self):
        self.count_label.setText(f"{len(self._scans)} scans")
        self.candidate_chip.set_status(
            f"{len(self._candidates)} candidates",
            "RECOVERED" if self._candidates else "UNANALYZED",
        )
        self.report_chip.set_status(
            f"{len(self._reports)} reports",
            "RECOVERED" if self._reports else "UNANALYZED",
        )

        by_status = self._metrics.get("by_status") or {}
        if by_status:
            summary = ", ".join(
                f"{count} {status.lower().replace('_', ' ')}"
                for status, count in sorted(by_status.items())
            )
            self.status_label.setText(f"File status distribution: {summary}")
        else:
            self.status_label.setText("No analyzed evidence records are stored yet.")

    # ----------------------------------------------------------------
    # Access
    # ----------------------------------------------------------------

    def metrics(self) -> Dict[str, Any]:
        return dict(self._metrics)

    def scan_rows(self) -> List[Dict[str, Any]]:
        return list(self._scans)

    def candidate_rows(self) -> List[Dict[str, Any]]:
        return list(self._candidates)

    def report_rows(self) -> List[Dict[str, Any]]:
        return list(self._reports)
