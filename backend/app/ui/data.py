"""
ReConstructAI - Read-only view layer for the UI

Builds the view models the pages render, using only the existing SQLite
schema and the existing CoreEngine semantics. Nothing here changes stored
data or re-implements any forensic logic.

The one derivation the interface needs is a file *status* token: the
`files` table has no status column, so status is recomputed from the data
the engine already persisted (fragment count, relationship scores,
reconstruction status, entropy) using the exact same rules the analysis
worker applies during a live run. Live and stored views therefore agree.
"""

import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app.storage.database as db
from app.ui.session import SESSION
from app.ui.components import NOT_AVAILABLE


#: Entropy above which a single-fragment file is treated as suspicious.
HIGH_ENTROPY_THRESHOLD = 7.5

#: Share of null bytes in a portion above which the bytes count as damaged.
DAMAGED_NULL_RATIO = 0.25

#: Relationship score above which evidence is considered strongly linked.
STRONG_RELATIONSHIP_THRESHOLD = 0.70

RECONSTRUCTED_STATUSES = ("RECONSTRUCTED", "PARTIALLY_RECONSTRUCTED")


# ====================================================================
# Status derivation
# ====================================================================

def null_ratio(byte_stats: Any, size: Any = None) -> Optional[float]:
    """Share of null bytes recorded for a portion, from persisted stats."""
    if not byte_stats:
        return None
    if isinstance(byte_stats, str):
        try:
            import json

            byte_stats = json.loads(byte_stats)
        except (TypeError, ValueError):
            return None
    if not isinstance(byte_stats, dict):
        return None

    null_bytes = byte_stats.get("null_bytes")
    if null_bytes is None:
        return None
    if size in (None, 0):
        size = byte_stats.get("size")
    if not size:
        unique = byte_stats.get("unique_bytes")
        if not unique:
            return None
        size = 256
    try:
        return max(0.0, min(1.0, float(null_bytes) / float(size)))
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def derive_file_status(
    fragment_count: int,
    relationship_scores: Optional[List[float]] = None,
    reconstruction_statuses: Optional[List[str]] = None,
    entropy: Optional[float] = None,
    null_ratios: Optional[List[float]] = None,
) -> str:
    """Derive a UI status token from persisted analysis results.

    Mirrors the rules the analysis worker applies to a live CoreEngine run
    so the Evidence table and the filtered pages classify files identically.
    """
    relationship_scores = relationship_scores or []
    reconstruction_statuses = reconstruction_statuses or []
    null_ratios = null_ratios or []

    if not fragment_count:
        return "HEALTHY"

    if reconstruction_statuses:
        if "RECONSTRUCTED" in reconstruction_statuses:
            return "RECOVERED"
        if "PARTIALLY_RECONSTRUCTED" in reconstruction_statuses:
            return "PARTIALLY_RECOVERABLE"
        return "FRAGMENTED"

    if any(ratio >= DAMAGED_NULL_RATIO for ratio in null_ratios):
        return "CORRUPTED"

    if relationship_scores:
        if any(score > STRONG_RELATIONSHIP_THRESHOLD for score in relationship_scores):
            return "SUSPICIOUS"
        return "FRAGMENTED"

    if fragment_count > 1:
        return "SUSPICIOUS"

    if entropy is not None and entropy > HIGH_ENTROPY_THRESHOLD:
        return "SUSPICIOUS"

    return "HEALTHY"


# ====================================================================
# Inventory loading
# ====================================================================

class Inventory:
    """Everything the UI reads, grouped for fast lookups."""

    def __init__(self):
        self.cases: List[Dict[str, Any]] = []
        self.scans: List[Dict[str, Any]] = []
        self.files: List[Dict[str, Any]] = []
        self.fragments: List[Dict[str, Any]] = []
        self.relationships: List[Dict[str, Any]] = []
        self.reconstructions: List[Dict[str, Any]] = []
        self.reports: List[Dict[str, Any]] = []

        self.fragments_by_scan: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.relationships_by_scan: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.reconstructions_by_scan: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.files_by_scan: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.scans_by_id: Dict[str, Dict[str, Any]] = {}
        self.cases_by_id: Dict[str, Dict[str, Any]] = {}

    # -- lookups ------------------------------------------------------
    def resolve_scan_id(self, scan_id: Optional[str] = None) -> Optional[str]:
        """Return the requested scan, else the active scan, else the newest."""
        if scan_id and scan_id in self.scans_by_id:
            return scan_id
        if SESSION.scan_id and SESSION.scan_id in self.scans_by_id:
            return SESSION.scan_id
        for scan in self.scans:
            return scan["scan_id"]
        return None

    def case_name(self, case_id: Optional[str]) -> str:
        case = self.cases_by_id.get(case_id or "")
        return case.get("name") if case else NOT_AVAILABLE


def _rows(conn, sql: str, params=()) -> List[Dict[str, Any]]:
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    except Exception:
        return []


def _decode_json(value: Any) -> Any:
    """Decode a stored JSON column, leaving anything unexpected untouched."""
    if not value or not isinstance(value, (str, bytes, bytearray)):
        return value
    import json

    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def load_inventory() -> Inventory:
    """Read the whole evidence dataset in one pass, defensively."""
    inventory = Inventory()
    try:
        with db.get_connection() as conn:
            inventory.cases = _rows(conn, "SELECT * FROM cases ORDER BY created_at DESC")
            inventory.scans = _rows(conn, "SELECT * FROM scans ORDER BY created_at DESC")
            inventory.files = _rows(conn, "SELECT * FROM files ORDER BY created_at DESC")
            inventory.fragments = _rows(conn, "SELECT * FROM fragments ORDER BY offset")
            inventory.relationships = _rows(
                conn, "SELECT * FROM relationships ORDER BY relationship_score DESC"
            )
            inventory.reconstructions = _rows(
                conn, "SELECT * FROM reconstructions ORDER BY confidence_score DESC"
            )
            inventory.reports = _rows(conn, "SELECT * FROM reports ORDER BY created_at DESC")
    except Exception:
        return inventory

    inventory.cases_by_id = {c["case_id"]: c for c in inventory.cases}
    inventory.scans_by_id = {s["scan_id"]: s for s in inventory.scans}
    for fragment in inventory.fragments:
        fragment["byte_stats"] = _decode_json(fragment.get("byte_stats"))
        inventory.fragments_by_scan[fragment.get("scan_id")].append(fragment)
    for relationship in inventory.relationships:
        inventory.relationships_by_scan[relationship.get("scan_id")].append(relationship)
    for reconstruction in inventory.reconstructions:
        reconstruction["fragment_ids"] = _decode_json(reconstruction.get("fragment_ids"))
        reconstruction["validation_details"] = _decode_json(
            reconstruction.get("validation_details")
        )
        inventory.reconstructions_by_scan[reconstruction.get("scan_id")].append(reconstruction)
    for file_row in inventory.files:
        inventory.files_by_scan[file_row.get("scan_id")].append(file_row)

    return inventory


# ====================================================================
# File records
# ====================================================================

def file_statuses(inventory: Inventory, scan_id: Optional[str] = None) -> Dict[Any, str]:
    """Derived status per file_id for one scan (or every scan)."""
    statuses: Dict[Any, str] = {}
    rows = inventory.files_by_scan.get(scan_id, []) if scan_id else inventory.files

    for row in rows:
        file_id = row.get("file_id")
        file_scan = row.get("scan_id")
        scan_fragments = inventory.fragments_by_scan.get(file_scan, [])
        file_fragments = [f for f in scan_fragments if f.get("file_id") == file_id] if file_id else scan_fragments
        fragments = file_fragments if file_fragments else scan_fragments
        relationships = inventory.relationships_by_scan.get(file_scan, [])
        reconstructions = inventory.reconstructions_by_scan.get(file_scan, [])
        null_ratios = [
            ratio
            for ratio in (
                null_ratio(f.get("byte_stats"), f.get("size")) for f in fragments
            )
            if ratio is not None
        ]
        status = derive_file_status(
            fragment_count=len(fragments),
            relationship_scores=[
                r.get("relationship_score") or 0.0 for r in relationships
            ],
            reconstruction_statuses=[
                r.get("status") for r in reconstructions if r.get("status")
            ],
            entropy=row.get("entropy"),
            null_ratios=null_ratios,
        )
        if file_id:
            statuses[file_id] = status
            statuses[(file_id, file_scan)] = status
    return statuses


def file_records(inventory: Optional[Inventory] = None, scan_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """View model for one row per analyzed file."""
    inventory = inventory or load_inventory()
    target_scan = inventory.resolve_scan_id(scan_id) if scan_id is not None else None
    rows = inventory.files_by_scan.get(target_scan, []) if target_scan else inventory.files

    statuses = file_statuses(inventory, target_scan)

    records: List[Dict[str, Any]] = []
    for row in rows:
        file_scan = row.get("scan_id")
        fragments = inventory.fragments_by_scan.get(file_scan, [])
        relationships = inventory.relationships_by_scan.get(file_scan, [])
        reconstructions = inventory.reconstructions_by_scan.get(file_scan, [])

        scores = [r.get("relationship_score") or 0.0 for r in relationships]
        recon_statuses = [r.get("status") for r in reconstructions if r.get("status")]

        best_integrity = max(
            (r.get("integrity_score") for r in reconstructions if r.get("integrity_score") is not None),
            default=None,
        )
        best_confidence = max(
            (r.get("confidence_score") for r in reconstructions if r.get("confidence_score") is not None),
            default=None,
        )
        validation = next(
            (r.get("validation_status") for r in reconstructions if r.get("validation_status")),
            None,
        )

        scan = inventory.scans_by_id.get(file_scan, {})
        records.append({
            "file_id": row.get("file_id"),
            "scan_id": file_scan,
            "case_id": row.get("case_id") or scan.get("case_id"),
            "case_name": inventory.case_name(row.get("case_id") or scan.get("case_id")),
            "name": row.get("filename") or NOT_AVAILABLE,
            "path": row.get("path") or NOT_AVAILABLE,
            "size": row.get("size"),
            "sha256": row.get("sha256"),
            "detected_type": row.get("detected_type"),
            "mime_type": row.get("mime_type"),
            "entropy": row.get("entropy"),
            "analysis": row.get("analysis_data"),
            "status": statuses.get((row.get("file_id"), file_scan)) or statuses.get(row.get("file_id")) or "UNANALYZED",
            "scan_status": scan.get("status"),
            "created_at": row.get("created_at") or scan.get("created_at"),
            "fragment_count": len(fragments),
            "relationship_count": len(relationships),
            "reconstruction_count": len(reconstructions),
            "integrity": best_integrity,
            "confidence": best_confidence,
            "validation_status": validation,
            "max_relationship_score": max(scores) if scores else None,
        })
    return records


# ====================================================================
# Fragment records
# ====================================================================

def fragment_records(inventory: Optional[Inventory] = None, scan_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """View model for one row per fragment, with real relationship counts."""
    inventory = inventory or load_inventory()
    target_scan = inventory.resolve_scan_id(scan_id)

    if not target_scan:
        return []

    relevance = SESSION.relevance_for_scan(target_scan)
    files_by_id = {f.get("file_id"): f for f in inventory.files}
    statuses = file_statuses(inventory, target_scan)

    counts: Dict[str, int] = defaultdict(int)
    best_score: Dict[str, float] = {}
    for relationship in inventory.relationships_by_scan.get(target_scan, []):
        for key in ("fragment_a", "fragment_b"):
            fragment_id = relationship.get(key)
            if not fragment_id:
                continue
            counts[fragment_id] += 1
            score = relationship.get("relationship_score")
            if score is not None:
                best_score[fragment_id] = max(best_score.get(fragment_id, 0.0), score)

    records: List[Dict[str, Any]] = []
    for fragment in inventory.fragments_by_scan.get(target_scan, []):
        fragment_id = fragment.get("fragment_id")
        file_row = files_by_id.get(fragment.get("file_id"), {})
        fragment_relevance = relevance.get(fragment_id)
        records.append({
            "fragment_id": fragment_id,
            "file_id": fragment.get("file_id"),
            "scan_id": target_scan,
            "file_name": file_row.get("filename") or NOT_AVAILABLE,
            "offset": fragment.get("offset"),
            "size": fragment.get("size"),
            "entropy": fragment.get("entropy"),
            "sha256": fragment.get("sha256"),
            "byte_stats": fragment.get("byte_stats"),
            "created_at": fragment.get("created_at"),
            "file_status": statuses.get(fragment.get("file_id")) or "UNANALYZED",
            "relationship_count": counts.get(fragment_id, 0),
            "max_relationship_score": best_score.get(fragment_id),
            "relevance_score": (fragment_relevance or {}).get("relevance_score"),
            "relevance_class": (fragment_relevance or {}).get("relevance_class"),
        })
    return records


# ====================================================================
# Reconstruction / recovered artifact records
# ====================================================================

def reconstruction_records(inventory: Optional[Inventory] = None, scan_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """View model for reconstruction candidates.

    With no scan requested every stored candidate is returned, matching
    `file_records`; pass a scan id to narrow to one scan.
    """
    inventory = inventory or load_inventory()
    target_scan = inventory.resolve_scan_id(scan_id) if scan_id is not None else None
    rows = inventory.reconstructions_by_scan.get(target_scan, []) if target_scan else inventory.reconstructions

    return [{
        "reconstruction_id": row.get("reconstruction_id"),
        "scan_id": row.get("scan_id"),
        "case_id": inventory.scans_by_id.get(row.get("scan_id"), {}).get("case_id"),
        "case_name": inventory.case_name(inventory.scans_by_id.get(row.get("scan_id"), {}).get("case_id")),
        "fragment_ids": row.get("fragment_ids"),
        "fragment_count": len(row.get("fragment_ids") or []) if isinstance(row.get("fragment_ids"), list)
        else None,
        "integrity": row.get("integrity_score"),
        "confidence": row.get("confidence_score"),
        "evidence_quality": row.get("evidence_quality"),
        "priority": row.get("priority"),
        "status": row.get("status"),
        "output_path": row.get("output_path"),
        "output_sha256": row.get("output_sha256"),
        "output_size": row.get("output_size"),
        "output_entropy": row.get("output_entropy"),
        "output_file_type": row.get("output_file_type"),
        "output_mime_type": row.get("output_mime_type"),
        "validation_status": row.get("validation_status"),
        "created_at": row.get("created_at"),
    } for row in rows]


def reconstructed_root() -> Path:
    try:
        from app.config import get_reconstructed_dir
        return get_reconstructed_dir()
    except ImportError:
        return Path("storage/reconstructed")


def recovered_artifact_records(inventory: Optional[Inventory] = None) -> List[Dict[str, Any]]:
    """View model for ONLY actual successful or partial reconstruction artifacts.

    Strictly enforces recovery state separation:
    - Only valid reconstruction records with status RECONSTRUCTED, PARTIALLY_RECONSTRUCTED,
      RECOVERED, or PARTIALLY_RECOVERABLE where the output file physically exists on disk.
    - Deduplicates redundant records pointing to the same artifact by content hash SHA-256
      and path, maintaining genuine distinct artifacts.
    """
    import hashlib

    inventory = inventory or load_inventory()
    valid_statuses = ("RECONSTRUCTED", "PARTIALLY_RECONSTRUCTED", "RECOVERED", "PARTIALLY_RECOVERABLE")

    by_hash: Dict[str, Dict[str, Any]] = {}
    for row in inventory.reconstructions:
        if row.get("status") in valid_statuses and row.get("output_sha256"):
            by_hash[row["output_sha256"]] = row

    records: List[Dict[str, Any]] = []
    seen_identities = set()

    # First collect valid reconstructions from database
    for recon in sorted(inventory.reconstructions, key=lambda r: r.get("created_at") or "", reverse=True):
        if recon.get("status") not in valid_statuses:
            continue
        out_path = Path(recon.get("output_path") or "")
        if not out_path.exists() or not out_path.is_file() or out_path.stat().st_size == 0:
            continue

        try:
            digest = recon.get("output_sha256")
            if not digest:
                digest = hashlib.sha256(out_path.read_bytes()).hexdigest()
        except OSError:
            continue

        identity = (digest, str(out_path.resolve()))
        if identity in seen_identities:
            continue
        seen_identities.add(identity)

        st = recon.get("status")
        status_norm = "PARTIALLY RECOVERED" if st in ("PARTIALLY_RECONSTRUCTED", "PARTIALLY_RECOVERABLE") else "RECOVERED"
        frag_ids = recon.get("fragment_ids") or []

        records.append({
            "artifact_id": recon.get("reconstruction_id") or out_path.stem,
            "name": out_path.name,
            "path": str(out_path),
            "size": out_path.stat().st_size,
            "sha256": digest,
            "detected_type": recon.get("output_file_type") or "Unknown",
            "mime_type": recon.get("output_mime_type") or "application/octet-stream",
            "entropy": recon.get("output_entropy"),
            "status": status_norm,
            "raw_status": st,
            "confidence": recon.get("confidence_score"),
            "integrity": recon.get("integrity_score"),
            "validation_status": recon.get("validation_status") or "Valid",
            "fragment_count": len(frag_ids) if isinstance(frag_ids, list) else 0,
            "reconstruction_id": recon.get("reconstruction_id"),
            "validation_details": recon.get("validation_details"),
            "scan_id": recon.get("scan_id"),
            "case_name": inventory.case_name(
                inventory.scans_by_id.get(recon.get("scan_id"), {}).get("case_id")
            ),
            "modified": out_path.stat().st_mtime,
            "linked": True,
        })

    # Also scan storage/reconstructed for files linked via SHA-256 to a valid reconstruction
    root = reconstructed_root()
    if root.exists():
        for path in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True):
            if not path.is_file() or path.stat().st_size == 0:
                continue
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                continue

            identity = (digest, str(path.resolve()))
            if identity in seen_identities:
                continue

            linked = by_hash.get(digest)
            if not linked:
                continue  # Strictly do NOT show unlinked/un-reconstructed files!

            seen_identities.add(identity)
            st = linked.get("status")
            status_norm = "PARTIALLY RECOVERED" if st in ("PARTIALLY_RECONSTRUCTED", "PARTIALLY_RECOVERABLE") else "RECOVERED"
            frag_ids = linked.get("fragment_ids") or []

            records.append({
                "artifact_id": linked.get("reconstruction_id") or path.stem,
                "name": path.name,
                "path": str(path),
                "size": path.stat().st_size,
                "sha256": digest,
                "detected_type": linked.get("output_file_type") or "Unknown",
                "mime_type": linked.get("output_mime_type") or "application/octet-stream",
                "entropy": linked.get("output_entropy"),
                "status": status_norm,
                "raw_status": st,
                "confidence": linked.get("confidence_score"),
                "integrity": linked.get("integrity_score"),
                "validation_status": linked.get("validation_status") or "Valid",
                "fragment_count": len(frag_ids) if isinstance(frag_ids, list) else 0,
                "reconstruction_id": linked.get("reconstruction_id"),
                "validation_details": linked.get("validation_details"),
                "scan_id": linked.get("scan_id"),
                "case_name": inventory.case_name(
                    inventory.scans_by_id.get(linked.get("scan_id"), {}).get("case_id")
                ),
                "modified": path.stat().st_mtime,
                "linked": True,
            })

    return records


# ====================================================================
# Scans, cases, reports
# ====================================================================

def scan_summaries(inventory: Optional[Inventory] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """View model for scan-level reporting."""
    inventory = inventory or load_inventory()
    summaries = []
    for scan in inventory.scans:
        scan_id = scan.get("scan_id")
        case_id = scan.get("case_id")
        files = inventory.files_by_scan.get(scan_id, [])
        reconstructions = inventory.reconstructions_by_scan.get(scan_id, [])
        confidences = [r.get("confidence_score") for r in reconstructions if r.get("confidence_score") is not None]
        summaries.append({
            "scan_id": scan_id,
            "case_id": case_id,
            "case_name": inventory.case_name(case_id),
            "status": scan.get("status"),
            "created_at": scan.get("created_at"),
            "file_count": len(files),
            "fragment_count": len(inventory.fragments_by_scan.get(scan_id, [])),
            "relationship_count": len(inventory.relationships_by_scan.get(scan_id, [])),
            "reconstruction_count": len(reconstructions),
            "best_confidence": max(confidences) if confidences else None,
            "file_name": files[0].get("filename") if files else None,
        })
    if limit:
        return summaries[:limit]
    return summaries


def case_records(inventory: Optional[Inventory] = None) -> List[Dict[str, Any]]:
    """View model for one row per case, with its real aggregated counts."""
    inventory = inventory or load_inventory()

    per_case: Dict[str, Dict[str, Any]] = {}
    for case in inventory.cases:
        per_case[case.get("case_id")] = {
            "case_id": case.get("case_id"),
            "name": case.get("name"),
            "description": case.get("description"),
            "created_at": case.get("created_at"),
            "scan_count": 0,
            "file_count": 0,
            "fragment_count": 0,
            "relationship_count": 0,
            "reconstruction_count": 0,
            "report_count": 0,
            "last_scan_at": None,
            "scan_ids": [],
        }

    def bucket(case_id: Optional[str]) -> Optional[Dict[str, Any]]:
        return per_case.get(case_id)

    for scan in inventory.scans:
        entry = bucket(scan.get("case_id"))
        if entry is None:
            continue
        scan_id = scan.get("scan_id")
        entry["scan_count"] += 1
        entry["scan_ids"].append(scan_id)
        entry["file_count"] += len(inventory.files_by_scan.get(scan_id, []))
        entry["fragment_count"] += len(inventory.fragments_by_scan.get(scan_id, []))
        entry["relationship_count"] += len(
            inventory.relationships_by_scan.get(scan_id, [])
        )
        entry["reconstruction_count"] += len(
            inventory.reconstructions_by_scan.get(scan_id, [])
        )
        created = scan.get("created_at")
        if created and (entry["last_scan_at"] is None or created > entry["last_scan_at"]):
            entry["last_scan_at"] = created

    for report in inventory.reports:
        entry = bucket(report.get("case_id"))
        if entry is not None:
            entry["report_count"] += 1

    return list(per_case.values())


def report_records(inventory: Optional[Inventory] = None) -> List[Dict[str, Any]]:
    inventory = inventory or load_inventory()
    records = []
    for row in inventory.reports:
        payload = row.get("report_data")
        if payload:
            payload = _decode_json(payload)
        if not isinstance(payload, dict):
            payload = {}

        def field(key, default=None):
            value = row.get(key)
            if value is None or value == "":
                value = payload.get(key)
            return default if value is None or value == "" else value

        records.append({
            "report_id": row.get("report_id"),
            "report_type": field("report_type", "recovery"),
            "case_id": row.get("case_id"),
            "case_name": inventory.case_name(row.get("case_id")),
            "scan_id": row.get("scan_id"),
            "reconstruction_id": row.get("reconstruction_id"),
            "filename": field("filename"),
            "file_path": field("file_path"),
            "file_type": field("file_type"),
            "mime_type": field("mime_type"),
            "relevance_score": field("relevance_score"),
            "ai_classification": field("ai_classification"),
            "detection_result": field("detection_result"),
            "user_reason": field("user_reason"),
            "report_status": field("report_status"),
            "created_at": row.get("created_at"),
            "report_path": row.get("report_path"),
            "report_data": payload or None,
        })
    return records


# ====================================================================
# Dashboard metrics
# ====================================================================

def dataset_metrics(inventory: Optional[Inventory] = None) -> Dict[str, Any]:
    """Summary metrics for the dashboard, computed from real records only."""
    inventory = inventory or load_inventory()
    files = file_records(inventory)

    by_status: Dict[str, int] = defaultdict(int)
    for record in files:
        by_status[record["status"]] += 1

    artifacts = recovered_artifact_records(inventory)
    return {
        "cases": len(inventory.cases),
        "scans": len(inventory.scans),
        "files": len(files),
        "suspicious": by_status.get("SUSPICIOUS", 0),
        "corrupted": by_status.get("CORRUPTED", 0),
        "healthy": by_status.get("HEALTHY", 0),
        "fragmented": by_status.get("FRAGMENTED", 0),
        "recovered": by_status.get("RECOVERED", 0) + by_status.get("PARTIALLY_RECOVERABLE", 0),
        "fragments": len(inventory.fragments),
        "relationships": len(inventory.relationships),
        "candidates": len(inventory.reconstructions),
        "artifacts": len(artifacts),
        "by_status": dict(by_status),
    }


def recent_evidence(inventory: Optional[Inventory] = None, limit: int = 6) -> List[Dict[str, Any]]:
    """Most recent scans with their real per-scan counts."""
    return scan_summaries(inventory, limit=limit)


def storage_state() -> Dict[str, Any]:
    """Real on-disk state of the working directories."""
    import shutil

    state: Dict[str, Any] = {}
    for name, relative in (
        ("uploads", Path("uploads")),
        ("reconstructed", reconstructed_root()),
        ("database", db.get_database_path()),
    ):
        path = Path(relative)
        exists = path.exists()
        entry = {"path": str(path), "exists": exists}
        if exists and path.is_dir():
            try:
                usage = shutil.disk_usage(path)
                entry["files"] = len([p for p in path.iterdir() if p.is_file()])
                entry["bytes"] = sum(p.stat().st_size for p in path.iterdir() if p.is_file())
                entry["free_bytes"] = usage.free
            except OSError:
                pass
        elif exists:
            try:
                entry["bytes"] = path.stat().st_size
            except OSError:
                pass
        state[name] = entry
    return state


def recovery_engine_state() -> Dict[str, Any]:
    """Verify the existing recovery engine can be constructed."""
    try:
        from app.recovery.deleted_file_scanner import DeletedFileScanner  # noqa: F401
        from app.recovery.candidate_extractor import CandidateExtractor
        from app.recovery.image_reader import ImageReader  # noqa: F401

        CandidateExtractor()
        return {"state": "ready", "message": "Ready"}
    except Exception as exc:
        return {"state": "error", "message": f"Error: {str(exc)[:40]}"}


def core_engine_state() -> Dict[str, Any]:
    """Verify the Core Engine can be constructed and reports its status."""
    try:
        from app.core_engine.engine import CoreEngine, EngineStatus

        engine = CoreEngine()
        status = engine.current_status
        if status == EngineStatus.IDLE:
            return {"state": "ready", "message": "Ready"}
        value = getattr(status, "value", status)
        return {"state": "ready", "message": str(value).replace("_", " ").title()}
    except Exception as exc:
        return {"state": "error", "message": f"Error: {str(exc)[:40]}"}


def database_state() -> Dict[str, Any]:
    """Verify the database answers a real query."""
    try:
        stats = db.get_database_stats()
        return {"state": "ready", "message": f"{stats.get('files', 0)} files"}
    except Exception as exc:
        return {"state": "error", "message": f"Error: {str(exc)[:40]}"}


def storage_state_summary() -> Dict[str, Any]:
    """Verify the working directories exist and are writable."""
    try:
        Path("uploads").mkdir(parents=True, exist_ok=True)
        reconstructed_root().mkdir(parents=True, exist_ok=True)
        state = storage_state()
        return {"state": "ready", "message": f"{state['uploads'].get('files', 0)} cached"}
    except Exception as exc:
        return {"state": "error", "message": f"Error: {str(exc)[:40]}"}
