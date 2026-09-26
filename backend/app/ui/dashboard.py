"""
ReConstructAI - Dashboard Page

Landing view built from the shared read-only view layer: real dataset metrics,
real engine/database/storage health, the most recent stored scans, and the
activity this session actually produced. Quick actions reuse the shell's
existing signals so navigation stays in one place.
"""

import os
import sys
from typing import Any, Dict, List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QStackedWidget

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.ui import data as view
from app.ui.components import (
    EmptyState,
    ForensicTable,
    MetricBlock,
    Page,
    SectionCard,
    StatusStrip,
    format_datetime,
    format_score,
    make_button,
)
from app.ui.session import SESSION


RECENT_COLUMNS = [
    {
        "key": "file_name",
        "label": "Evidence Source",
        "stretch": True,
        "kind": "text",
        "value": lambda r: (r.get("file_name") or r.get("scan_id"), "text"),
        "tooltip": lambda r: r.get("scan_id") or "",
    },
    {
        "key": "case_name",
        "label": "Case",
        "width": 170,
        "kind": "text",
        "value": lambda r: (r.get("case_name"), "text"),
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
        "key": "reconstruction_count",
        "label": "Candidates",
        "width": 95,
        "kind": "center",
        "value": lambda r: (r.get("reconstruction_count"), "center"),
    },
    {
        "key": "best_confidence",
        "label": "Best Confidence",
        "width": 115,
        "kind": "center",
        "value": lambda r: (format_score(r.get("best_confidence"), 2), "center"),
    },
    {
        "key": "created_at",
        "label": "Scanned",
        "width": 145,
        "kind": "center",
        "value": lambda r: (format_datetime(r.get("created_at")), "center"),
    },
]


class DashboardPage(Page):
    """Metrics, system health, recent evidence and quick actions."""

    create_case_requested = Signal()
    open_case_requested = Signal()
    analyze_evidence_requested = Signal()
    analyze_single_requested = Signal()
    recover_deleted_requested = Signal()

    def __init__(self, parent=None):
        self._metrics: Dict[str, Any] = {}
        self._recent: List[Dict[str, Any]] = []
        super().__init__(
            "Dashboard",
            "Recover. Reconstruct. Understand.",
            parent=parent,
        )
        self._setup_body()

    # ----------------------------------------------------------------
    # Construction
    # ----------------------------------------------------------------

    def _setup_body(self):
        self.btn_analyze_folder = make_button(
            "Analyze Evidence Folder",
            self.analyze_evidence_requested.emit,
            variant="primary",
            tooltip="Select an evidence folder and run the Core Engine",
        )
        self.btn_analyze_single = make_button(
            "Analyze Single File",
            self.analyze_single_requested.emit,
            variant="secondary",
            tooltip="Analyze one file without selecting a folder",
        )
        self.btn_recover_deleted = make_button(
            "Recover Deleted Data",
            self.recover_deleted_requested.emit,
            variant="secondary",
            tooltip="Scan a .dd or .img storage image for deleted entries",
        )
        self.btn_create_case = make_button(
            "Create New Case",
            self.create_case_requested.emit,
            variant="ghost",
            tooltip="Start a new investigation",
        )
        for button in (
            self.btn_analyze_folder,
            self.btn_analyze_single,
            self.btn_recover_deleted,
            self.btn_create_case,
        ):
            self.add_header_widget(button)

        self.btn_open_case = make_button(
            "Open a Case",
            self.open_case_requested.emit,
            variant="ghost",
            tooltip="Browse stored cases",
        )
        self.add_header_widget(self.btn_open_case)

        self.metrics_card = SectionCard("Investigation Summary")
        self._blocks: Dict[str, MetricBlock] = {}
        for key, label, hint in (
            ("cases", "Cases", "Stored investigations"),
            ("scans", "Scans", "Evidence scans"),
            ("files", "Files", "Analyzed evidence"),
            ("fragments", "Fragments", "Fixed-size portions"),
            ("candidates", "Candidates", "Reconstructions"),
            ("artifacts", "Artifacts", "Recovered on disk"),
        ):
            block = MetricBlock(label, "0", hint)
            self._blocks[key] = block
            self.metrics_card.body_layout().addWidget(block)
        self.add_widget(self.metrics_card)

        self.health_card = SectionCard("System Status")
        self.status_strip = StatusStrip()
        for key, title in (
            ("engine", "Core Engine"),
            ("database", "Database"),
            ("storage", "Local Storage"),
            ("recovery", "Deleted Recovery"),
        ):
            self.status_strip.add_component(key, title)
        self.health_card.body_layout().addWidget(self.status_strip)
        self.add_widget(self.health_card)

        self.recent_card = SectionCard("Recent Evidence")
        self.recent_stack = QStackedWidget()
        self.recent_table = ForensicTable(RECENT_COLUMNS, object_name="dataTable")
        self.recent_stack.addWidget(self.recent_table)
        self.recent_empty = EmptyState(
            "No evidence analyzed yet",
            "Analyze an evidence folder or a single file to begin.",
        )
        self.recent_stack.addWidget(self.recent_empty)
        self.recent_card.body_layout().addWidget(self.recent_stack)
        self.add_widget(self.recent_card, 1)

        self.activity_card = SectionCard("Session Activity")
        self.activity_label = QLabel("No activity recorded in this session yet.")
        self.activity_label.setObjectName("bodyLabel")
        self.activity_label.setWordWrap(True)
        self.activity_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.activity_card.body_layout().addWidget(self.activity_label)
        self.add_widget(self.activity_card)

        self.status_label = QLabel("")
        self.status_label.setObjectName("pageSubtitle")
        self.status_label.setWordWrap(True)
        self.add_widget(self.status_label)

        self.refresh()

    # ----------------------------------------------------------------
    # Data
    # ----------------------------------------------------------------

    def refresh(self):
        self.refresh_metrics()
        self.refresh_recent()

    def refresh_metrics(self):
        """Recompute dataset metrics from the real database."""
        try:
            self._metrics = view.dataset_metrics()
        except Exception as exc:
            self._metrics = {}
            self.status_label.setText(f"Could not compute metrics: {exc}")

        for key, block in self._blocks.items():
            value = self._metrics.get(key, 0)
            block.set_value(value if value is not None else 0)

        by_status = self._metrics.get("by_status") or {}
        if by_status:
            summary = ", ".join(
                f"{count} {status.lower().replace('_', ' ')}"
                for status, count in sorted(by_status.items())
            )
            self.status_label.setText(f"File status distribution: {summary}")
        elif not self.status_label.text():
            self.status_label.setText("No analyzed evidence records are stored yet.")

    def refresh_recent(self):
        try:
            self._recent = view.recent_evidence(limit=8)
        except Exception:
            self._recent = []

        self.recent_table.set_records(self._recent)
        self.recent_stack.setCurrentIndex(0 if self.recent_table.rowCount() else 1)
        self._render_activity()

    def _render_activity(self):
        entries = SESSION.recent_activity(limit=8)
        if not entries:
            self.activity_label.setText("No activity recorded in this session yet.")
            return
        self.activity_label.setText(
            "\n".join(f"{e['timestamp']}   {e['text']}" for e in entries)
        )

    # ----------------------------------------------------------------
    # Status
    # ----------------------------------------------------------------

    def update_status(self, component: str, status: str, message: str = ""):
        """Update one system health entry (engine, database, storage)."""
        mapping = {
            "engine": "engine",
            "database": "database",
            "storage": "storage",
            "recovery": "recovery",
        }
        key = mapping.get(component)
        if key:
            self.status_strip.set_state(key, status, message)

    def check_health(self):
        """Verify the real subsystems and record their state."""
        for key, probe in (
            ("engine", view.core_engine_state),
            ("database", view.database_state),
            ("storage", view.storage_state_summary),
            ("recovery", view.recovery_engine_state),
        ):
            try:
                state = probe()
            except Exception as exc:  # pragma: no cover - defensive
                state = {"state": "error", "message": f"Error: {str(exc)[:40]}"}
            self.status_strip.set_state(key, state.get("state", "error"), state.get("message", ""))

    def metrics(self) -> Dict[str, Any]:
        return dict(self._metrics)

    def recent_rows(self) -> List[Dict[str, Any]]:
        return list(self._recent)
