"""
Tests for the UI data layer and the pages that were rewired onto it.

These cover the behaviour that the pages depend on: status derived from real
persisted evidence (never from a column that does not exist), per-case counts
aggregated from stored scans, the cross-evidence recovery worker producing real
bytes, and the shared widgets accepting the value types the engine stores.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

#: The database and storage paths are relative to the project root, so the UI
#: data layer is always read from there regardless of test ordering.
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def project_root():
    previous = os.getcwd()
    os.chdir(PROJECT_ROOT)
    try:
        yield PROJECT_ROOT
    finally:
        os.chdir(previous)

from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QApplication

from app.ui import data as view
from app.ui.components import DetailRow, StatusStrip, as_text
from test_cross_recovery import build_pdf


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# ====================================================================
# Status derivation from real persisted evidence
# ====================================================================

def test_null_ratio_reads_persisted_byte_stats():
    assert view.null_ratio({"null_bytes": 2048, "unique_bytes": 256}, 4096) == 0.5
    assert view.null_ratio({"null_bytes": 15}, 4096) == pytest.approx(15 / 4096)
    assert view.null_ratio('{"null_bytes": 100}', 400) == 0.25
    assert view.null_ratio(None, 4096) is None
    assert view.null_ratio({"unique_bytes": 256}, 4096) is None
    assert view.null_ratio("not json", 4096) is None


def test_status_uses_real_damage_evidence():
    assert view.derive_file_status(0) == "HEALTHY"
    assert view.derive_file_status(1, entropy=3.0) == "HEALTHY"
    assert view.derive_file_status(1, entropy=7.9) == "SUSPICIOUS"
    assert view.derive_file_status(3) == "SUSPICIOUS"
    assert view.derive_file_status(1, null_ratios=[0.9]) == "CORRUPTED"
    assert view.derive_file_status(1, null_ratios=[0.01]) == "HEALTHY"
    assert view.derive_file_status(
        1, reconstruction_statuses=["RECONSTRUCTED"], null_ratios=[0.9]
    ) == "RECOVERED"
    assert view.derive_file_status(
        1, reconstruction_statuses=["PARTIALLY_RECONSTRUCTED"]
    ) == "PARTIALLY_RECOVERABLE"
    assert view.derive_file_status(1, relationship_scores=[0.95]) == "SUSPICIOUS"
    assert view.derive_file_status(1, relationship_scores=[0.2]) == "FRAGMENTED"


def test_status_pages_read_derived_status_not_a_missing_column(qapp):
    """The filtered pages must reflect derived status, not a files.status column."""
    if not view.load_inventory().cases:
        pytest.skip("no stored cases in this workspace")
    inventory = view.load_inventory()
    records = view.file_records(inventory)
    assert records, "expected analyzed evidence records in the database"
    assert all(record["status"] for record in records)
    assert all(record["status"] != "UNANALYZED" for record in records)

    counts = {}
    for record in records:
        counts[record["status"]] = counts.get(record["status"], 0) + 1

    from app.ui.filtered_files import FilteredFilesPage

    page = FilteredFilesPage("Suspicious", "SUSPICIOUS")
    assert page.table.rowCount() == counts.get("SUSPICIOUS", 0)
    assert all(
        record["status"] == "SUSPICIOUS" for record in page.records()
    )


def test_file_statuses_are_per_file(qapp):
    inventory = view.load_inventory()
    if not inventory.fragments:
        pytest.skip("no stored fragments in this workspace")
    scan_id = inventory.resolve_scan_id(None)
    statuses = view.file_statuses(inventory, scan_id)
    fragments = inventory.fragments_by_scan.get(scan_id, [])
    for fragment in fragments:
        file_id = fragment.get("file_id")
        if file_id in statuses:
            assert statuses[file_id] in {
                "HEALTHY", "SUSPICIOUS", "CORRUPTED", "FRAGMENTED",
                "RECOVERED", "PARTIALLY_RECOVERABLE",
            }


def test_case_records_aggregate_real_scans(qapp):
    inventory = view.load_inventory()
    if not inventory.cases:
        pytest.skip("no stored cases in this workspace")
    cases = view.case_records(inventory)
    assert len(cases) == len(inventory.cases)
    total_files = sum(case["file_count"] for case in cases)
    assert total_files == len(inventory.files)
    total_fragments = sum(case["fragment_count"] for case in cases)
    assert total_fragments == len(inventory.fragments)
    for case in cases:
        if case["scan_count"] == 0:
            assert case["file_count"] == 0
            assert case["fragment_count"] == 0


def test_reconstruction_records_decode_stored_json(qapp):
    inventory = view.load_inventory()
    if not inventory.reconstructions:
        pytest.skip("no stored reconstructions in this workspace")
    records = view.reconstruction_records(inventory)
    for record in records:
        assert record["status"]
        fragment_ids = record["fragment_ids"]
        if fragment_ids is not None:
            assert isinstance(fragment_ids, list)


# ====================================================================
# Cross-evidence recovery through the UI worker
# ====================================================================

class _Collector(QObject):
    def __init__(self):
        super().__init__()
        self.payload = None

    @Slot(dict)
    def on_completed(self, payload):
        self.payload = payload


def test_recovery_worker_rebuilds_the_real_original(qapp, tmp_path):
    from app.ui.analysis_worker import CrossEvidenceRecoveryWorker

    pdf = build_pdf(40)
    container = tmp_path / "container.bin"
    container.write_bytes(pdf)
    target = tmp_path / "report.pdf"
    target.write_bytes(pdf[: len(pdf) // 2])

    collector = _Collector()
    worker = CrossEvidenceRecoveryWorker(
        str(target), [str(container)], str(tmp_path / "out")
    )
    worker.completed.connect(collector.on_completed)
    worker.run()

    payload = collector.payload
    assert payload is not None
    assert payload["status"] == "RECONSTRUCTED"
    assert payload["missing_portions"] == 0
    assert payload["damaged_portions"] == 0
    assert Path(payload["artifact_path"]).read_bytes() == pdf
    assert payload["validation"]["structurally_valid"] is True
    assert any("truncated" in line for line in payload["insights"])


def test_recovery_worker_refuses_without_matching_evidence(qapp, tmp_path):
    from app.ui.analysis_worker import CrossEvidenceRecoveryWorker

    pdf = build_pdf(40)
    target = tmp_path / "report.pdf"
    target.write_bytes(pdf[: len(pdf) // 2])
    unrelated = tmp_path / "notes.txt"
    unrelated.write_text("unrelated content\n" * 500)

    collector = _Collector()
    worker = CrossEvidenceRecoveryWorker(
        str(target), [str(unrelated)], str(tmp_path / "out")
    )
    worker.completed.connect(collector.on_completed)
    worker.run()

    payload = collector.payload
    assert payload["status"] == "NO_RELIABLE_RECONSTRUCTION_FOUND"
    assert payload["artifact_path"] is None
    assert payload["recovered_portions"] == 0


def test_recovery_worker_reports_intact_file_without_recovering(qapp, tmp_path):
    from app.ui.analysis_worker import CrossEvidenceRecoveryWorker

    pdf = build_pdf(20)
    target = tmp_path / "whole.pdf"
    target.write_bytes(pdf)
    other = tmp_path / "other.bin"
    other.write_bytes(build_pdf(10))

    collector = _Collector()
    worker = CrossEvidenceRecoveryWorker(
        str(target), [str(other)], str(tmp_path / "out")
    )
    worker.completed.connect(collector.on_completed)
    worker.run()

    payload = collector.payload
    assert payload["status"] == "INTACT"
    assert payload["artifact_path"] is None
    assert payload["integrity"] == 1.0


# ====================================================================
# Shared widgets
# ====================================================================

def test_detail_row_accepts_engine_value_types(qapp):
    assert as_text(None) == "Not available"
    assert as_text("") == "Not available"
    assert as_text(1234) == "1234"
    assert as_text(3.5) == "3.5"
    assert as_text(["a", "b"]) == "a, b"
    assert as_text({"k": 1}) == "k=1"

    row = DetailRow("Metadata address", 1234, mono=True)
    assert row.value_label.text() == "1234"
    row.set_value(9876)
    assert row.value_label.text() == "9876"
    row.set_value(None)
    assert row.value_label.text() == "Not available"


def test_status_strip_reports_its_last_state(qapp):
    strip = StatusStrip()
    strip.add_component("engine", "Core Engine")
    strip.set_state("engine", "ready", "Ready")
    assert strip.state_for("engine") == ("ready", "Ready")
    assert strip.state_for("missing") is None


def test_pages_construct_and_render_stored_data(qapp):
    from app.ui.dashboard import DashboardPage
    from app.ui.fragments_page import FragmentsPage
    from app.ui.recovered_page import RecoveredPage
    from app.ui.reports_page import ReportsPage

    inventory = view.load_inventory()
    if not inventory.scans:
        pytest.skip("no stored scans in this workspace")

    reports = ReportsPage()
    assert reports._scans_table.rowCount() == len(inventory.scans)

    fragments = FragmentsPage()
    assert fragments.scan_box.count() == len(inventory.scans)

    recovered = RecoveredPage()
    recovered.refresh()
    assert recovered.count_label.text().endswith("artifacts")

    dashboard = DashboardPage()
    dashboard.check_health()
    assert dashboard.status_strip.state_for("engine")[0] == "ready"
    assert dashboard.status_strip.state_for("database")[0] == "ready"
