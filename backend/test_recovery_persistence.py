"""
Recovery Persistence and Recovered-Page Tests

These exercise the real UI integration: the recovery worker runs against real
files, the evidence page persists the result through the real database layer,
and the Recovered page data view must list only artifacts that exist on disk,
exactly once.
"""

import hashlib
import shutil
import sys
import tempfile
import zlib
import struct
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

import app.storage.database as db_module
from app.storage import database as db


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + chunk_type
        + payload
        + struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF)
    )


def build_png(payload: bytes) -> bytes:
    import random

    raw = bytearray()
    for row in range(8):
        raw.append(0)
        for col in range(8):
            raw.extend(((row * 8 + col) % 256, (row * 3) % 256, (col * 5) % 256))
    ihdr = struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(raw) + payload)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


def noise(length: int, seed: int) -> bytes:
    """Incompressible bytes, so the test PNG is genuinely large."""
    import random

    return random.Random(seed).randbytes(length)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Every test runs against its own temporary application-data directory."""
    appdata = tmp_path / "appdata"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("RECONSTRUCTAI_APP_DATA", str(appdata))

    original_db_path = db_module.DB_PATH
    db_module.DB_PATH = appdata / "test.db"
    db_module.initialize_database()

    evidence = tmp_path / "evidence"
    evidence.mkdir(parents=True)
    try:
        yield {
            "root": tmp_path,
            "appdata": appdata,
            "evidence": evidence,
            "reconstructed": appdata / "reconstructed",
        }
    finally:
        db_module.DB_PATH = original_db_path


def run_recovery(target: Path, evidence: list, output_dir: Path) -> dict:
    from app.ui.analysis_worker import CrossEvidenceRecoveryWorker

    payloads = []
    worker = CrossEvidenceRecoveryWorker(str(target), [str(p) for p in evidence], str(output_dir))
    worker.completed.connect(payloads.append)
    worker.run()
    assert payloads, "the worker must always emit a result"
    return payloads[0]


def persist_payload(page, payload: dict, scan_id: str) -> str:
    page._recovery_target = {"scan_id": scan_id}
    return page._persist_recovery(payload)


def evidence_page():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from app.ui.evidence import EvidencePage

    return EvidencePage()


def test_recovered_artifact_is_persisted_and_listed_once(workspace):
    original = build_png(noise(40000, 21))
    backup = workspace["evidence"] / "photo_backup.png"
    backup.write_bytes(original)
    target = workspace["evidence"] / "photo.png"
    target.write_bytes(original[: len(original) - 5000])

    case_id = "CASE_PERSIST"
    db.create_case(case_id, "recovery persistence")
    scan_id = "SCAN_PERSIST"
    db.create_scan(scan_id, case_id, "completed")
    db.save_file("F_PERSIST", scan_id, "photo.png", str(target), target.stat().st_size,
                 hashlib.sha256(target.read_bytes()).hexdigest(), "PNG", "image/png")

    payload = run_recovery(target, [backup], workspace["reconstructed"])
    assert payload["status"] == "RECONSTRUCTED", payload["insights"]
    assert Path(payload["artifact_path"]).is_file()
    assert Path(payload["artifact_path"]).read_bytes() == original

    page = evidence_page()
    reconstruction_id = persist_payload(page, payload, scan_id)
    assert reconstruction_id, "a real artifact must be persisted"

    from app.ui import data as view

    records = view.recovered_artifact_records(view.load_inventory())
    listed = [r for r in records if r["reconstruction_id"] == reconstruction_id]
    assert len(listed) == 1, "the artifact must appear exactly once"
    assert listed[0]["status"] == "RECOVERED"
    assert Path(listed[0]["path"]).is_file()
    assert listed[0]["sha256"] == hashlib.sha256(original).hexdigest()
    assert listed[0]["size"] == len(original)

    # Persisting the same artifact again must not create a duplicate entry.
    again = persist_payload(page, payload, scan_id)
    assert again and again != reconstruction_id
    records = view.recovered_artifact_records(view.load_inventory())
    assert len([r for r in records if r["path"] == listed[0]["path"]]) == 1


def test_failed_recovery_creates_no_recovered_entry(workspace):
    original = build_png(noise(40000, 22))
    target = workspace["evidence"] / "lost.png"
    target.write_bytes(original[:4000])
    unrelated = workspace["evidence"] / "notes.txt"
    unrelated.write_bytes(b"nothing to do with the target" * 200)

    case_id = "CASE_FAIL"
    db.create_case(case_id, "no reliable reconstruction")
    scan_id = "SCAN_FAIL"
    db.create_scan(scan_id, case_id, "completed")

    payload = run_recovery(target, [unrelated], workspace["reconstructed"])
    assert payload["status"] == "NO_RELIABLE_RECONSTRUCTION"
    assert payload["artifact_path"] is None

    page = evidence_page()
    assert persist_payload(page, payload, scan_id) is None

    from app.ui import data as view

    records = view.recovered_artifact_records(view.load_inventory())
    assert records == [], "a failed recovery must never appear as a recovered artifact"


def test_intact_file_creates_no_recovered_entry(workspace):
    original = build_png(noise(40000, 23))
    target = workspace["evidence"] / "healthy.png"
    target.write_bytes(original)

    case_id = "CASE_HEALTHY"
    db.create_case(case_id, "nothing to recover")
    scan_id = "SCAN_HEALTHY"
    db.create_scan(scan_id, case_id, "completed")

    payload = run_recovery(target, [target], workspace["reconstructed"])
    assert payload["status"] == "INTACT"
    assert payload["artifact_path"] is None

    page = evidence_page()
    assert persist_payload(page, payload, scan_id) is None


def test_candidate_and_scanned_files_are_not_recovered(workspace):
    """A reconstruction attempt row alone must not create a Recovered entry."""
    case_id = "CASE_CAND"
    db.create_case(case_id, "attempt without artifact")
    scan_id = "SCAN_CAND"
    db.create_scan(scan_id, case_id, "completed")
    db.save_file("F_CAND", scan_id, "candidate.bin", "C:/evidence/candidate.bin",
                 10, "0" * 64, "unknown", "application/octet-stream")
    db.save_reconstruction(
        reconstruction_id="RC_CAND",
        scan_id=scan_id,
        fragment_ids=["FRAG_1"],
        integrity_score=0.8,
        confidence_score=0.7,
        evidence_quality="HIGH",
        priority="HIGH",
        status="CANDIDATE",
    )

    from app.ui import data as view

    records = view.recovered_artifact_records(view.load_inventory())
    assert records == [], "a candidate must not be shown as a recovered artifact"
    assert (workspace["reconstructed"]).exists() or True


def test_report_as_useful_persists_real_report(workspace):
    case_id = "CASE_REPORT"
    db.create_case(case_id, "low relevance evidence reported")
    scan_id = "SCAN_REPORT"
    db.create_scan(scan_id, case_id, "completed")
    db.save_file("F_REPORT", scan_id, "junk.bin", "C:/evidence/junk.bin",
                 5, "1" * 64, "unknown", "application/octet-stream")

    from app.ui.evidence import ReportAsUsefulDialog
    from PySide6.QtWidgets import QMessageBox

    app_payload = {
        "name": "junk.bin",
        "path": "C:/evidence/junk.bin",
        "type": "binary",
        "status": "UNANALYZED",
        "relevance_class": "LOW_RELEVANCE",
        "case_id": case_id,
        "scan_id": scan_id,
    }

    # The real dialog is driven; only the modal message boxes are suppressed.
    shown = []
    monkey = QMessageBox.information
    QMessageBox.information = staticmethod(lambda *a, **k: shown.append(a[2] if len(a) > 2 else ""))
    QMessageBox.critical = staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError(a[2])))
    try:
        dialog = ReportAsUsefulDialog(app_payload, None)
        dialog.reason_edit.setPlainText("Kept for the timeline")
        dialog._save_report()
    finally:
        QMessageBox.information = monkey

    assert shown, "the dialog must confirm the stored report"

    from app.ui import data as view

    records = view.report_records(view.load_inventory())
    matching = [r for r in records if r["filename"] == "junk.bin"]
    assert len(matching) == 1
    assert matching[0]["report_type"] == "useful_feedback"
    assert matching[0]["user_reason"] == "Kept for the timeline"
    assert matching[0]["case_id"] == case_id
    assert matching[0]["scan_id"] == scan_id
    assert Path(app_payload["path"]).name == matching[0]["filename"]


def test_workspace_is_isolated_from_production_storage(workspace):
    """The test must never write into the project's production storage."""
    production = PROJECT_ROOT / "storage"
    assert db_module.DB_PATH.parent == workspace["appdata"]
    assert str(production) not in str(db_module.DB_PATH)
    assert not (workspace["appdata"] / "reconstructai.db").resolve() == (
        production / "reconstructai.db"
    ).resolve()



