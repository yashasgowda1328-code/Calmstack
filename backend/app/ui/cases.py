"""
ReConstructAI - Cases Page

Case management over the real stored investigations. Each row carries the
counts the engine actually stored for that case, and selecting a case makes it
the active investigation for the rest of the workspace.
"""

import os
import sys
import uuid
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.storage.database import create_case, get_case
from app.ui import data as view
from app.ui.components import (
    DetailsPanel,
    EmptyState,
    ForensicTable,
    Page,
    StatusChip,
    Toolbar,
    format_datetime,
    make_button,
    shorten_hash,
)
from app.ui.session import SESSION


CASE_COLUMNS = [
    {
        "key": "name",
        "label": "Case",
        "stretch": True,
        "kind": "text",
        "value": lambda r: (r.get("name"), "text"),
        "tooltip": lambda r: r.get("case_id") or "",
    },
    {
        "key": "scan_count",
        "label": "Scans",
        "width": 80,
        "kind": "center",
        "value": lambda r: (r.get("scan_count"), "center"),
    },
    {
        "key": "file_count",
        "label": "Files",
        "width": 75,
        "kind": "center",
        "value": lambda r: (r.get("file_count"), "center"),
    },
    {
        "key": "fragment_count",
        "label": "Fragments",
        "width": 95,
        "kind": "center",
        "value": lambda r: (r.get("fragment_count"), "center"),
    },
    {
        "key": "reconstruction_count",
        "label": "Candidates",
        "width": 100,
        "kind": "center",
        "value": lambda r: (r.get("reconstruction_count"), "center"),
    },
    {
        "key": "last_scan_at",
        "label": "Last Scan",
        "width": 150,
        "kind": "center",
        "value": lambda r: (format_datetime(r.get("last_scan_at")), "center"),
    },
    {
        "key": "created_at",
        "label": "Created",
        "width": 150,
        "kind": "center",
        "value": lambda r: (format_datetime(r.get("created_at")), "center"),
    },
]


class CreateCaseDialog(QDialog):
    """Dialog for creating a new case."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create New Case")
        self.setMinimumWidth(480)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Create New Case")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(16)
        form.setLabelAlignment(Qt.AlignLeft)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter case name")
        self.name_edit.setMinimumHeight(40)
        form.addRow("Case Name *", self.name_edit)

        self.desc_edit = QTextEdit()
        self.desc_edit.setPlaceholderText("Optional description...")
        self.desc_edit.setMaximumHeight(100)
        form.addRow("Description", self.desc_edit)

        layout.addLayout(form)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_btn = button_box.button(QDialogButtonBox.Ok)
        ok_btn.setObjectName("primaryButton")
        ok_btn.setText("Create Case")
        button_box.button(QDialogButtonBox.Cancel).setObjectName("secondaryButton")
        button_box.accepted.connect(self._validate_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _validate_and_accept(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Validation Error", "Case name is required.")
            return
        self.accept()

    def get_case_data(self) -> Dict[str, str]:
        return {
            "name": self.name_edit.text().strip(),
            "description": self.desc_edit.toPlainText().strip(),
        }


class CasesPage(Page):
    """Cases management page."""

    case_selected = Signal(str)

    def __init__(self, parent=None):
        self._cases: List[Dict[str, Any]] = []
        self._selected_case_id: Optional[str] = None
        super().__init__(
            "Cases",
            "Stored investigations and their real evidence counts",
            parent=parent,
        )
        self._setup_body()

    # ----------------------------------------------------------------
    # Construction
    # ----------------------------------------------------------------

    def _setup_body(self):
        self.btn_create = make_button(
            "Create New Case",
            self._create_case,
            variant="primary",
            tooltip="Start a new investigation",
        )
        self.btn_refresh = make_button(
            "Refresh",
            self.refresh,
            variant="secondary",
            tooltip="Re-read cases from the database",
        )
        self.add_header_widget(self.btn_create)
        self.add_header_widget(self.btn_refresh)

        self.toolbar = Toolbar()
        self.count_label = QLabel("0 cases")
        self.count_label.setObjectName("mutedLabel")
        self.toolbar.add_widget(self.count_label)

        self.active_chip = StatusChip("No active case", "UNANALYZED")
        self.active_chip.setToolTip("The case the workspace is currently working in")
        self.toolbar.add_widget(self.active_chip)
        self.toolbar.add_spacer()
        self.add_widget(self.toolbar)

        self.workspace = QStackedWidget()

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(1)

        self.table = ForensicTable(CASE_COLUMNS, object_name="dataTable")
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemDoubleClicked.connect(lambda _r: self._on_open_case())
        self.splitter.addWidget(self.table)

        self.details = DetailsPanel("Case Details")
        self.details.clear("Select a case to view its stored evidence")
        self.splitter.addWidget(self.details)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([860, 360])
        self.workspace.addWidget(self.splitter)

        self.empty_state = EmptyState(
            "No cases yet",
            "Create your first case to start an investigation.",
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
        """Reload cases and their real counts."""
        try:
            self._cases = view.case_records()
        except Exception as exc:
            self._cases = []
            self.status_label.setText(f"Could not read cases: {exc}")

        if self._selected_case_id and not any(
            case.get("case_id") == self._selected_case_id for case in self._cases
        ):
            self._selected_case_id = None

        self._render()
        self._render_active_chip()

    def cases(self) -> List[Dict[str, Any]]:
        return list(self._cases)

    def _render(self):
        self.table.set_records(self._cases)
        self.count_label.setText(f"{len(self._cases)} cases")
        self.workspace.setCurrentIndex(0 if self.table.rowCount() else 1)
        if not self._cases:
            self.empty_state.set_state(
                "No cases yet",
                "Create your first case to start an investigation.",
            )
        if self._selected_case_id:
            self._select_record(self._selected_case_id)
        elif self._cases:
            self.table.select_first()

    def _render_active_chip(self):
        if SESSION.has_case():
            self.active_chip.set_status(SESSION.case_name or "Active case", "RECOVERED")
        elif self._selected_case_id:
            self.active_chip.set_status("Selected, not opened", "PENDING")
        else:
            self.active_chip.set_status("No active case", "UNANALYZED")

    def _select_record(self, case_id: str):
        for row, case in enumerate(self._cases):
            if case.get("case_id") == case_id:
                self.table.selectRow(row)
                return True
        return False

    # ----------------------------------------------------------------
    # Interaction
    # ----------------------------------------------------------------

    def _on_selection_changed(self):
        record = self.table.current_record()
        if not record:
            self._selected_case_id = None
            self.details.clear("Select a case to view its stored evidence")
            self._render_active_chip()
            return

        self._selected_case_id = record.get("case_id")
        identity = self.details.section("identity", "Case")
        identity.add_row("Name", record.get("name"))
        identity.add_row("Case ID", shorten_hash(record.get("case_id"), 12, 8), mono=True)
        identity.add_row("Created", format_datetime(record.get("created_at")))
        identity.add_row("Description", record.get("description") or "No description")

        evidence = self.details.section("evidence", "Stored evidence")
        evidence.add_row("Scans", str(record.get("scan_count", 0)))
        evidence.add_row("Files", str(record.get("file_count", 0)))
        evidence.add_row("Fragments", str(record.get("fragment_count", 0)))
        evidence.add_row("Relationships", str(record.get("relationship_count", 0)))
        evidence.add_row("Reconstructions", str(record.get("reconstruction_count", 0)))
        evidence.add_row("Reports", str(record.get("report_count", 0)))
        evidence.add_row("Last scan", format_datetime(record.get("last_scan_at")))

        scan_ids = record.get("scan_ids") or []
        if scan_ids:
            scans = self.details.section("scans", "Scans")
            shown = scan_ids[-8:]
            for scan_id in shown:
                scans.add_row(
                    "Scan", shorten_hash(scan_id, 12, 8), mono=True
                )
            if len(scan_ids) > len(shown):
                scans.add_row("More", f"{len(scan_ids) - len(shown)} earlier scan(s)")

        self.status_label.setText(
            f"{record.get('name')}: {record.get('scan_count', 0)} scan(s), "
            f"{record.get('file_count', 0)} file(s), "
            f"{record.get('fragment_count', 0)} fragment(s)."
        )
        self._render_active_chip()

    def _on_open_case(self):
        record = self.table.current_record()
        if not record:
            return
        case_id = record.get("case_id")
        if not case_id:
            return
        SESSION.set_case(case_id, record.get("name"))
        if record.get("scan_ids"):
            SESSION.set_scan(record["scan_ids"][0])
        SESSION.log_activity(f"Opened case {record.get('name')}", "case")
        self._render_active_chip()
        self.case_selected.emit(case_id)

    def _create_case(self):
        dialog = CreateCaseDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        data = dialog.get_case_data()
        case_id = str(uuid.uuid4())
        try:
            create_case(case_id, data["name"], data["description"])
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to create case: {exc}")
            return

        self._selected_case_id = case_id
        SESSION.set_case(case_id, data["name"])
        SESSION.log_activity(f"Created case {data['name']}", "case")
        self.refresh()
        self._select_record(case_id)
        self._on_open_case()

    # ----------------------------------------------------------------
    # Access
    # ----------------------------------------------------------------

    def get_selected_case_id(self) -> Optional[str]:
        return self._selected_case_id

    def get_selected_case(self) -> Optional[Dict[str, Any]]:
        if not self._selected_case_id:
            return None
        return get_case(self._selected_case_id)
