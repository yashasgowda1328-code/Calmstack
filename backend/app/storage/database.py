"""
SQLite Persistence Layer for ReConstructAI

Provides database storage for cases, scans, files, fragments,
relationships, reconstructions, and reports.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from dataclasses import dataclass

try:
    from app.config import get_db_path
    DB_PATH = get_db_path()
except ImportError:
    DB_PATH = Path("storage/reconstructai.db")

DB_PATH.parent.mkdir(parents=True, exist_ok=True)


SCHEMA = """
-- Cases table
CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Scans table
CREATE TABLE IF NOT EXISTS scans (
    scan_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (case_id) REFERENCES cases (case_id)
);

-- Files table
CREATE TABLE IF NOT EXISTS files (
    file_id TEXT PRIMARY KEY,
    scan_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    path TEXT NOT NULL,
    size INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    detected_type TEXT,
    mime_type TEXT,
    entropy REAL,
    analysis_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (scan_id) REFERENCES scans (scan_id)
);

-- Fragments table
CREATE TABLE IF NOT EXISTS fragments (
    fragment_id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    scan_id TEXT NOT NULL,
    offset INTEGER NOT NULL,
    size INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    entropy REAL NOT NULL,
    byte_stats TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files (file_id),
    FOREIGN KEY (scan_id) REFERENCES scans (scan_id)
);

-- Relationships table
CREATE TABLE IF NOT EXISTS relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fragment_a TEXT NOT NULL,
    fragment_b TEXT NOT NULL,
    scan_id TEXT NOT NULL,
    relationship_score REAL NOT NULL,
    score_details TEXT,
    scoring_method TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (fragment_a) REFERENCES fragments (fragment_id),
    FOREIGN KEY (fragment_b) REFERENCES fragments (fragment_id),
    FOREIGN KEY (scan_id) REFERENCES scans (scan_id)
);

-- Reconstructions table
CREATE TABLE IF NOT EXISTS reconstructions (
    reconstruction_id TEXT PRIMARY KEY,
    scan_id TEXT NOT NULL,
    fragment_ids TEXT NOT NULL,
    integrity_score REAL NOT NULL,
    confidence_score REAL NOT NULL,
    evidence_quality TEXT,
    priority TEXT,
    status TEXT NOT NULL,
    output_path TEXT,
    output_sha256 TEXT,
    output_size INTEGER,
    output_entropy REAL,
    output_file_type TEXT,
    output_mime_type TEXT,
    validation_status TEXT,
    validation_details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (scan_id) REFERENCES scans (scan_id)
);

-- Reports table
CREATE TABLE IF NOT EXISTS reports (
    report_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    scan_id TEXT,
    reconstruction_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    report_path TEXT,
    report_data TEXT,
    FOREIGN KEY (case_id) REFERENCES cases (case_id),
    FOREIGN KEY (scan_id) REFERENCES scans (scan_id),
    FOREIGN KEY (reconstruction_id) REFERENCES reconstructions (reconstruction_id)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_scans_case_id ON scans (case_id);
CREATE INDEX IF NOT EXISTS idx_files_scan_id ON files (scan_id);
CREATE INDEX IF NOT EXISTS idx_fragments_file_id ON fragments (file_id);
CREATE INDEX IF NOT EXISTS idx_fragments_scan_id ON fragments (scan_id);
CREATE INDEX IF NOT EXISTS idx_relationships_scan_id ON relationships (scan_id);
CREATE INDEX IF NOT EXISTS idx_reconstructions_scan_id ON reconstructions (scan_id);
CREATE INDEX IF NOT EXISTS idx_reports_case_id ON reports (case_id);
"""


def get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_transaction():
    """Context manager for database transactions."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_database():
    """Initialize the database with schema."""
    with db_transaction() as conn:
        conn.executescript(SCHEMA)
    return True


# ============================================================
# Case Operations
# ============================================================

def create_case(case_id: str, name: str, description: str = "") -> bool:
    """Create a new case."""
    with db_transaction() as conn:
        conn.execute(
            "INSERT INTO cases (case_id, name, description) VALUES (?, ?, ?)",
            (case_id, name, description)
        )
    return True


def get_case(case_id: str) -> Optional[Dict]:
    """Get a case by ID."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    return dict(row) if row else None


def list_cases() -> List[Dict]:
    """List all cases."""
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM cases ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


# ============================================================
# Scan Operations
# ============================================================

def create_scan(scan_id: str, case_id: str, status: str = "pending") -> bool:
    """Create a new scan (or update if exists)."""
    with db_transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO scans (scan_id, case_id, status) VALUES (?, ?, ?)",
            (scan_id, case_id, status)
        )
    return True


def update_scan_status(scan_id: str, status: str) -> bool:
    """Update scan status."""
    with db_transaction() as conn:
        conn.execute("UPDATE scans SET status = ? WHERE scan_id = ?", (status, scan_id))
    return True


def get_scan(scan_id: str) -> Optional[Dict]:
    """Get a scan by ID."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM scans WHERE scan_id = ?", (scan_id,)).fetchone()
    return dict(row) if row else None


def list_scans(case_id: Optional[str] = None) -> List[Dict]:
    """List scans, optionally filtered by case."""
    with get_connection() as conn:
        if case_id:
            rows = conn.execute(
                "SELECT * FROM scans WHERE case_id = ? ORDER BY created_at DESC",
                (case_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM scans ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


# ============================================================
# File Operations
# ============================================================

def save_file(
    file_id: str,
    scan_id: str,
    filename: str,
    path: str,
    size: int,
    sha256: str,
    detected_type: Optional[str] = None,
    mime_type: Optional[str] = None,
    entropy: Optional[float] = None,
    analysis_data: Optional[Dict] = None
) -> bool:
    """Save analyzed file metadata (or update if exists)."""
    with db_transaction() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO files 
               (file_id, scan_id, filename, path, size, sha256, detected_type, mime_type, entropy, analysis_data)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                file_id, scan_id, filename, path, size, sha256,
                detected_type, mime_type, entropy,
                json.dumps(analysis_data) if analysis_data else None
            )
        )
    return True


def get_file(file_id: str) -> Optional[Dict]:
    """Get file by ID."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM files WHERE file_id = ?", (file_id,)).fetchone()
    if row:
        result = dict(row)
        if result.get('analysis_data'):
            result['analysis_data'] = json.loads(result['analysis_data'])
        return result
    return None


def get_files_by_scan(scan_id: str) -> List[Dict]:
    """Get all files for a scan."""
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM files WHERE scan_id = ?", (scan_id,)).fetchall()
    results = []
    for row in rows:
        result = dict(row)
        if result.get('analysis_data'):
            result['analysis_data'] = json.loads(result['analysis_data'])
        results.append(result)
    return results


# ============================================================
# Fragment Operations
# ============================================================

def save_fragment(
    fragment_id: str,
    file_id: str,
    scan_id: str,
    offset: int,
    size: int,
    sha256: str,
    entropy: float,
    byte_stats: Optional[Dict] = None
) -> bool:
    """Save a fragment."""
    with db_transaction() as conn:
        conn.execute(
            """INSERT INTO fragments
               (fragment_id, file_id, scan_id, offset, size, sha256, entropy, byte_stats)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fragment_id, file_id, scan_id, offset, size,
                sha256, entropy, json.dumps(byte_stats) if byte_stats else None
            )
        )
    return True


def save_fragments_bulk(fragments: List[Dict]) -> bool:
    """Save multiple fragments efficiently."""
    with db_transaction() as conn:
        for frag in fragments:
            conn.execute(
                """INSERT INTO fragments
                   (fragment_id, file_id, scan_id, offset, size, sha256, entropy, byte_stats)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    frag['fragment_id'], frag['file_id'], frag['scan_id'],
                    frag['offset'], frag['size'], frag['sha256'],
                    frag['entropy'],
                    json.dumps(frag.get('byte_stats')) if frag.get('byte_stats') else None
                )
            )
    return True


def get_fragments_by_scan(scan_id: str) -> List[Dict]:
    """Get all fragments for a scan."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM fragments WHERE scan_id = ? ORDER BY offset",
            (scan_id,)
        ).fetchall()
    results = []
    for row in rows:
        result = dict(row)
        if result.get('byte_stats'):
            result['byte_stats'] = json.loads(result['byte_stats'])
        results.append(result)
    return results


def get_fragments_by_file(file_id: str) -> List[Dict]:
    """Get all fragments for a file."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM fragments WHERE file_id = ? ORDER BY offset",
            (file_id,)
        ).fetchall()
    results = []
    for row in rows:
        result = dict(row)
        if result.get('byte_stats'):
            result['byte_stats'] = json.loads(result['byte_stats'])
        results.append(result)
    return results


# ============================================================
# Relationship Operations
# ============================================================

def save_relationship(
    fragment_a: str,
    fragment_b: str,
    scan_id: str,
    relationship_score: float,
    score_details: Optional[Dict] = None,
    scoring_method: str = "baseline"
) -> int:
    """Save a fragment relationship. Returns the row ID."""
    with db_transaction() as conn:
        cursor = conn.execute(
            """INSERT INTO relationships
               (fragment_a, fragment_b, scan_id, relationship_score, score_details, scoring_method)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                fragment_a, fragment_b, scan_id, relationship_score,
                json.dumps(score_details) if score_details else None,
                scoring_method
            )
        )
        return cursor.lastrowid


def save_relationships_bulk(relationships: List[Dict]) -> bool:
    """Save multiple relationships efficiently."""
    with db_transaction() as conn:
        for rel in relationships:
            conn.execute(
                """INSERT INTO relationships
                   (fragment_a, fragment_b, scan_id, relationship_score, score_details, scoring_method)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    rel['fragment_a'], rel['fragment_b'], rel['scan_id'],
                    rel['relationship_score'],
                    json.dumps(rel.get('score_details')) if rel.get('score_details') else None,
                    rel.get('scoring_method', 'baseline')
                )
            )
    return True


def get_relationships_by_scan(scan_id: str) -> List[Dict]:
    """Get all relationships for a scan."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM relationships WHERE scan_id = ? ORDER BY relationship_score DESC",
            (scan_id,)
        ).fetchall()
    results = []
    for row in rows:
        result = dict(row)
        if result.get('score_details'):
            result['score_details'] = json.loads(result['score_details'])
        results.append(result)
    return results


# ============================================================
# Reconstruction Operations
# ============================================================

def save_reconstruction(
    reconstruction_id: str,
    scan_id: str,
    fragment_ids: List[str],
    integrity_score: float,
    confidence_score: float,
    evidence_quality: str,
    priority: str,
    status: str,
    output_path: Optional[str] = None,
    output_sha256: Optional[str] = None,
    output_size: Optional[int] = None,
    output_entropy: Optional[float] = None,
    output_file_type: Optional[str] = None,
    output_mime_type: Optional[str] = None,
    validation_status: Optional[str] = None,
    validation_details: Optional[Dict] = None
) -> bool:
    """Save a reconstruction result (or update if exists)."""
    with db_transaction() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO reconstructions
               (reconstruction_id, scan_id, fragment_ids, integrity_score, confidence_score,
                evidence_quality, priority, status, output_path, output_sha256, output_size,
                output_entropy, output_file_type, output_mime_type, validation_status, validation_details)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                reconstruction_id, scan_id, json.dumps(fragment_ids),
                integrity_score, confidence_score, evidence_quality, priority, status,
                output_path, output_sha256, output_size, output_entropy,
                output_file_type, output_mime_type, validation_status,
                json.dumps(validation_details) if validation_details else None
            )
        )
    return True


def update_reconstruction_result(
    reconstruction_id: str,
    status: str,
    output_path: Optional[str] = None,
    output_sha256: Optional[str] = None,
    output_size: Optional[int] = None,
    output_entropy: Optional[float] = None,
    output_file_type: Optional[str] = None,
    output_mime_type: Optional[str] = None,
    validation_status: Optional[str] = None,
    validation_details: Optional[Dict] = None
) -> bool:
    """Record the outcome of a reconstruction run on an existing candidate row.

    Only the artifact columns are touched, so the candidate scores and its
    original `created_at` are preserved.
    """
    with db_transaction() as conn:
        conn.execute(
            """UPDATE reconstructions
               SET status = ?, output_path = ?, output_sha256 = ?, output_size = ?,
                   output_entropy = ?, output_file_type = ?, output_mime_type = ?,
                   validation_status = ?, validation_details = ?
               WHERE reconstruction_id = ?""",
            (
                status, output_path, output_sha256, output_size, output_entropy,
                output_file_type, output_mime_type, validation_status,
                json.dumps(validation_details) if validation_details else None,
                reconstruction_id
            )
        )
    return True


def get_reconstruction(reconstruction_id: str) -> Optional[Dict]:
    """Get a reconstruction by ID."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM reconstructions WHERE reconstruction_id = ?",
            (reconstruction_id,)
        ).fetchone()
    if row:
        result = dict(row)
        result['fragment_ids'] = json.loads(result['fragment_ids']) if result['fragment_ids'] else []
        if result.get('validation_details'):
            result['validation_details'] = json.loads(result['validation_details'])
        return result
    return None


def get_reconstructions_by_scan(scan_id: str) -> List[Dict]:
    """Get all reconstructions for a scan."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM reconstructions WHERE scan_id = ? ORDER BY confidence_score DESC",
            (scan_id,)
        ).fetchall()
    results = []
    for row in rows:
        result = dict(row)
        result['fragment_ids'] = json.loads(result['fragment_ids']) if result['fragment_ids'] else []
        if result.get('validation_details'):
            result['validation_details'] = json.loads(result['validation_details'])
        results.append(result)
    return results


# ============================================================
# Report Operations
# ============================================================

def save_report(
    report_id: str,
    case_id: str,
    scan_id: Optional[str] = None,
    reconstruction_id: Optional[str] = None,
    report_path: Optional[str] = None,
    report_data: Optional[Dict] = None
) -> bool:
    """Save a report."""
    with db_transaction() as conn:
        conn.execute(
            """INSERT INTO reports
               (report_id, case_id, scan_id, reconstruction_id, report_path, report_data)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                report_id, case_id, scan_id, reconstruction_id, report_path,
                json.dumps(report_data) if report_data else None
            )
        )
    return True


def create_report(
    report_id: str,
    case_id: str,
    report_type: str = "recovery",
    scan_id: Optional[str] = None,
    reconstruction_id: Optional[str] = None,
    filename: Optional[str] = None,
    file_path: Optional[str] = None,
    file_type: Optional[str] = None,
    mime_type: Optional[str] = None,
    relevance_score: Optional[float] = None,
    ai_classification: Optional[str] = None,
    detection_result: Optional[str] = None,
    user_reason: Optional[str] = None,
    report_status: str = "SUBMITTED",
    report_path: Optional[str] = None,
    report_data: Optional[Dict] = None
) -> bool:
    """Save a report with its descriptive fields.

    The `reports` table stores the identifying columns; every additional
    descriptive field is kept inside the `report_data` JSON payload so the
    schema stays unchanged for existing databases.
    """
    payload: Dict[str, Any] = dict(report_data or {})
    for key, value in (
        ("report_type", report_type),
        ("filename", filename),
        ("file_path", file_path),
        ("file_type", file_type),
        ("mime_type", mime_type),
        ("relevance_score", relevance_score),
        ("ai_classification", ai_classification),
        ("detection_result", detection_result),
        ("user_reason", user_reason),
        ("report_status", report_status),
    ):
        if value is not None:
            payload[key] = value

    with db_transaction() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO reports
               (report_id, case_id, scan_id, reconstruction_id, report_path, report_data)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                report_id, case_id, scan_id, reconstruction_id, report_path,
                json.dumps(payload)
            )
        )
    return True


def get_reports_by_case(case_id: str) -> List[Dict]:
    """Get all reports for a case."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM reports WHERE case_id = ? ORDER BY created_at DESC",
            (case_id,)
        ).fetchall()
    results = []
    for row in rows:
        result = dict(row)
        if result.get('report_data'):
            result['report_data'] = json.loads(result['report_data'])
        results.append(result)
    return results


# ============================================================
# Integration: Persist Full Scan Result
# ============================================================

def persist_scan_result(
    case_id: str,
    scan_id: str,
    scan_result: Any,  # ScanResult from models
    fragments: List[Any],
    relationships: List[Any],
    reconstructions: List[Any]
) -> Dict[str, Any]:
    """
    Persist a complete scan result including all related entities.
    
    Returns a summary of what was persisted.
    """
    # Create scan
    create_scan(scan_id, case_id, status=scan_result.status)
    
    # Save file
    file_id = f"file_{scan_id}"
    save_file(
        file_id=file_id,
        scan_id=scan_id,
        filename=scan_result.filename,
        path=f"uploads/{scan_result.filename}",
        size=scan_result.size,
        sha256=scan_result.sha256,
        detected_type=scan_result.file_type,
        mime_type=scan_result.mime_type,
        entropy=scan_result.entropy,
        analysis_data=scan_result.analysis
    )
    
    # Save fragments
    fragment_data = []
    for frag in fragments:
        fragment_data.append({
            'fragment_id': frag.fragment_id,
            'file_id': file_id,
            'scan_id': scan_id,
            'offset': frag.offset,
            'size': frag.size,
            'sha256': frag.sha256,
            'entropy': frag.entropy,
            'byte_stats': frag.byte_stats
        })
    save_fragments_bulk(fragment_data)
    
    # Save relationships
    relationship_data = []
    for rel in relationships:
        relationship_data.append({
            'fragment_a': rel.fragment_a,
            'fragment_b': rel.fragment_b,
            'scan_id': scan_id,
            'relationship_score': rel.relationship_score,
            'score_details': rel.score_details,
            'scoring_method': rel.score_details.get('scoring_method', 'baseline') if rel.score_details else 'baseline'
        })
    save_relationships_bulk(relationship_data)
    
    # Save reconstructions
    for recon in reconstructions:
        # Extract structural validation if present
        validation_status = None
        validation_details = None
        if hasattr(recon, 'structural_validation') and recon.structural_validation:
            sv = recon.structural_validation
            validation_status = sv.validation_status
            validation_details = {
                'file_exists': sv.file_exists,
                'readable': sv.readable,
                'size_valid': sv.size_valid,
                'signature_detected': sv.signature_detected,
                'detected_type': sv.detected_type,
                'mime_type': sv.mime_type,
                'entropy': sv.entropy,
                'is_binary': sv.is_binary,
                'null_bytes': sv.null_bytes,
                'unique_bytes': sv.unique_bytes,
                'header_bytes': sv.header_bytes,
                'sha256': sv.sha256,
                'structurally_valid': sv.structurally_valid,
                'validation_notes': sv.validation_notes
            }
        
        save_reconstruction(
            reconstruction_id=recon.reconstruction_id,
            scan_id=scan_id,
            fragment_ids=recon.fragment_ids,
            integrity_score=recon.integrity_score,
            confidence_score=recon.confidence_score,
            evidence_quality=recon.evidence_quality,
            priority=recon.priority,
            status=recon.status,
            output_path=recon.output_path if hasattr(recon, 'output_path') else None,
            output_sha256=recon.sha256 if hasattr(recon, 'sha256') else None,
            output_size=recon.total_size if hasattr(recon, 'total_size') else None,
            output_entropy=recon.entropy if hasattr(recon, 'entropy') else None,
            output_file_type=recon.file_type if hasattr(recon, 'file_type') else None,
            output_mime_type=recon.mime_type if hasattr(recon, 'mime_type') else None,
            validation_status=validation_status,
            validation_details=validation_details
        )
    
    return {
        'case_id': case_id,
        'scan_id': scan_id,
        'file_id': file_id,
        'fragments_saved': len(fragment_data),
        'relationships_saved': len(relationship_data),
        'reconstructions_saved': len(reconstructions)
    }


# ============================================================
# Utility
# ============================================================

def get_database_path() -> Path:
    """Get the database file path."""
    return DB_PATH


def database_exists() -> bool:
    """Check if database file exists."""
    return DB_PATH.exists()


def get_database_stats() -> Dict:
    """Get database statistics."""
    with get_connection() as conn:
        stats = {}
        for table in ['cases', 'scans', 'files', 'fragments', 'relationships', 'reconstructions', 'reports']:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            stats[table] = count
    return stats