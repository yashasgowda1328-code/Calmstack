"""
ReConstructAI - Filtered Files View

The All Files, Healthy, Suspicious, Corrupted and Recovered navigation pages.
Every row comes from the shared read-only view layer, so the status shown here
is the same derived status the Evidence page shows for a live run, and the same
status the status-filtered pages filter on.
"""

import os
import sys
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QLineEdit, QSplitter, QStackedWidget

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.ui import data as view
from app.ui.components import (
    EmptyState,
    Page,
    StatusChip,
    Toolbar,
    make_button,
)
from app.ui.evidence import FileDetailsPanel, FileTableWidget


#: Status token -> display name used for the page subtitle and empty state.
STATUS_LABELS = {
    "HEALTHY": "healthy",
    "SUSPICIOUS": "suspicious",
    "CORRUPTED": "corrupted",
    "FRAGMENTED": "fragmented",
    "RECOVERED": "recovered",
    "PARTIALLY_RECOVERABLE": "partially recoverable",
    "UNANALYZED": "unanalyzed",
}


class FilteredFilesPage(Page):
    """A view of real evidence records filtered by derived status."""

    def __init__(
        self,
        title: str,
        status_filter: Optional[str],
        description: str = "",
        parent=None,
    ):
        self._status_filter = status_filter
        self._files: List[Dict[str, Any]] = []
        self._dataset: List[Dict[str, Any]] = []
        label = STATUS_LABELS.get(status_filter or "", status_filter or "")
        subtitle = description or (
            f"Real evidence records classified as {label}"
            if label
            else "All analyzed evidence records across every case"
        )
        super().__init__(title, subtitle, parent=parent)
        self._setup_body()

    # ----------------------------------------------------------------
    # Construction
    # ----------------------------------------------------------------

    def _setup_body(self):
        self.btn_refresh = make_button(
            "Refresh",
            self.refresh,
            variant="secondary",
            tooltip="Re-read the analysis dataset from the database",
        )
        self.add_header_widget(self.btn_refresh)

        self.toolbar = Toolbar()
        self.count_label = QLabel("0 files")
        self.count_label.setObjectName("mutedLabel")
        self.toolbar.add_widget(self.count_label)

        self.status_chip = StatusChip("All statuses", "UNANALYZED")
        self.status_chip.setToolTip("Status filter applied to this page")
        self.toolbar.add_widget(self.status_chip)
        self.toolbar.add_spacer()

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search name or path")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setMaximumWidth(240)
        self.search_box.setMinimumWidth(140)
        self.search_box.textChanged.connect(self._on_search_changed)
        self.toolbar.add_widget(self.search_box)
        self.add_widget(self.toolbar)

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
            self._empty_title(),
            "Analyzed evidence records appear here once the engine has stored them.",
        )
        self.workspace.addWidget(self.empty_state)
        self.add_widget(self.workspace, 1)

        self.status_label = QLabel("")
        self.status_label.setObjectName("pageSubtitle")
        self.status_label.setWordWrap(True)
        self.add_widget(self.status_label)

        self.workspace.setCurrentIndex(1)
        self.refresh()

    # ----------------------------------------------------------------
    # Data
    # ----------------------------------------------------------------

    def refresh(self):
        """Reload the analyzed dataset and re-apply the status filter."""
        try:
            self._dataset = view.file_records()
        except Exception as exc:
            self._dataset = []
            self.status_label.setText(f"Could not read the analysis dataset: {exc}")

        self._apply_filter()
        self._render()

    def records(self) -> List[Dict[str, Any]]:
        """Rows currently listed by this page."""
        return list(self._files)

    # ----------------------------------------------------------------
    # Rendering
    # ----------------------------------------------------------------

    def _apply_filter(self):
        rows = self._dataset
        if self._status_filter:
            rows = [row for row in rows if row.get("status") == self._status_filter]
        self._files = rows

    def _render(self):
        self.table.set_files(self._files)
        self.count_label.setText(f"{len(self._files)} of {len(self._dataset)} files")

        if self._status_filter:
            self.status_chip.set_status(
                STATUS_LABELS.get(self._status_filter, self._status_filter),
                self._status_filter,
            )
        else:
            self.status_chip.set_status("All statuses", "UNANALYZED")

        self._on_search_changed(self.search_box.text())
        self.status_label.setText(self._summary())
        self.workspace.setCurrentIndex(0 if self.table.rowCount() else 1)

        if not self._files:
            self.empty_state.set_state(self._empty_title(), self._empty_hint())

    def _summary(self) -> str:
        if not self._dataset:
            return "No analyzed evidence records are stored yet."
        if self._status_filter:
            label = STATUS_LABELS.get(self._status_filter, self._status_filter)
            return f"{len(self._files)} of {len(self._dataset)} analyzed files are {label}."
        return f"{len(self._dataset)} analyzed evidence records across all cases."

    def _empty_title(self) -> str:
        if self._status_filter:
            label = STATUS_LABELS.get(self._status_filter, self._status_filter)
            return f"No {label} evidence"
        return "No analyzed evidence"

    def _empty_hint(self) -> str:
        if not self._dataset:
            return "Run an evidence analysis to populate the dataset."
        return (
            "No record currently has this status. Analyze more evidence or "
            "choose another status."
        )

    # ----------------------------------------------------------------
    # Interaction
    # ----------------------------------------------------------------

    def _on_file_selected(self, record: Dict[str, Any]):
        self.details_panel.set_file_data(record)

    def _on_search_changed(self, text: str):
        self.table.apply_search(text)
        self.workspace.setCurrentIndex(0 if self.table.rowCount() else 1)
