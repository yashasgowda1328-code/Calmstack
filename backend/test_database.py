"""
Database Persistence Layer Tests

Controlled tests for SQLite storage of ReConstructAI results.
"""

import tempfile
import os
from pathlib import Path

from app.storage.database import (
    initialize_database, get_database_path, database_exists, get_database_stats,
    create_case, get_case, list_cases,
    create_scan, get_scan, list_scans, update_scan_status,
    save_file, get_file, get_files_by_scan,
    save_fragment, save_fragments_bulk, get_fragments_by_scan, get_fragments_by_file,
    save_relationship, save_relationships_bulk, get_relationships_by_scan,
    save_reconstruction, get_reconstruction, get_reconstructions_by_scan,
    save_report, get_reports_by_case,
    persist_scan_result
)

from app.models.scan import Fragment, Relationship, ReconstructionCandidate, ScanResult
from datetime import datetime


def setup_test_db():
    """Initialize a fresh test database."""
    # Use a test database path
    import app.storage.database as db_module
    test_db = Path("storage/test_reconstructai.db")
    if test_db.exists():
        test_db.unlink()
    db_module.DB_PATH = test_db
    initialize_database()
    return test_db


def test_case_operations():
    """Test case CRUD operations."""
    print("=" * 60)
    print("TEST: Case Operations")
    print("=" * 60)
    
    # Create case
    create_case("CASE_001", "Test Case", "A test case for demonstration")
    print("Created case CASE_001")
    
    # Get case
    case = get_case("CASE_001")
    assert case is not None
    assert case['case_id'] == "CASE_001"
    assert case['name'] == "Test Case"
    print(f"Retrieved case: {case['name']}")
    
    # List cases
    cases = list_cases()
    assert len(cases) >= 1
    print(f"Listed {len(cases)} cases")
    
    print("PASS")
    return True


def test_scan_operations():
    """Test scan CRUD operations."""
    print("\n" + "=" * 60)
    print("TEST: Scan Operations")
    print("=" * 60)
    
    create_case("CASE_002", "Scan Test Case")
    
    # Create scan
    create_scan("SCAN_001", "CASE_002", "pending")
    print("Created scan SCAN_001")
    
    # Get scan
    scan = get_scan("SCAN_001")
    assert scan is not None
    assert scan['scan_id'] == "SCAN_001"
    assert scan['case_id'] == "CASE_002"
    assert scan['status'] == "pending"
    print(f"Retrieved scan: {scan['status']}")
    
    # Update status
    update_scan_status("SCAN_001", "completed")
    scan = get_scan("SCAN_001")
    assert scan['status'] == "completed"
    print("Updated scan status to completed")
    
    # List scans
    scans = list_scans("CASE_002")
    assert len(scans) >= 1
    print(f"Listed {len(scans)} scans for case")
    
    print("PASS")
    return True


def test_file_operations():
    """Test file operations."""
    print("\n" + "=" * 60)
    print("TEST: File Operations")
    print("=" * 60)
    
    create_case("CASE_003", "File Test Case")
    create_scan("SCAN_002", "CASE_003", "completed")
    
    # Save file
    save_file(
        file_id="FILE_001",
        scan_id="SCAN_002",
        filename="test.pdf",
        path="uploads/test.pdf",
        size=1024,
        sha256="abc123",
        detected_type="PDF document",
        mime_type="application/pdf",
        entropy=4.5,
        analysis_data={"header_bytes": "25504446", "null_bytes": 0}
    )
    print("Saved file FILE_001")
    
    # Get file
    file = get_file("FILE_001")
    assert file is not None
    assert file['filename'] == "test.pdf"
    assert file['size'] == 1024
    assert file['analysis_data']['header_bytes'] == "25504446"
    print(f"Retrieved file: {file['filename']} ({file['size']} bytes)")
    
    # Get files by scan
    files = get_files_by_scan("SCAN_002")
    assert len(files) >= 1
    print(f"Listed {len(files)} files for scan")
    
    print("PASS")
    return True


def test_fragment_operations():
    """Test fragment operations."""
    print("\n" + "=" * 60)
    print("TEST: Fragment Operations")
    print("=" * 60)
    
    create_case("CASE_004", "Fragment Test Case")
    create_scan("SCAN_003", "CASE_004", "completed")
    save_file("FILE_002", "SCAN_003", "test.bin", "uploads/test.bin", 8192, "def456", "data", "application/octet-stream", 7.8)
    
    # Save fragments bulk
    fragments = [
        {
            'fragment_id': 'F001',
            'file_id': 'FILE_002',
            'scan_id': 'SCAN_003',
            'offset': 0,
            'size': 4096,
            'sha256': 'frag1_hash',
            'entropy': 7.5,
            'byte_stats': {'unique_bytes': 256, 'null_bytes': 10}
        },
        {
            'fragment_id': 'F002',
            'file_id': 'FILE_002',
            'scan_id': 'SCAN_003',
            'offset': 4096,
            'size': 4096,
            'sha256': 'frag2_hash',
            'entropy': 7.6,
            'byte_stats': {'unique_bytes': 256, 'null_bytes': 12}
        }
    ]
    save_fragments_bulk(fragments)
    print("Saved 2 fragments")
    
    # Get fragments by scan
    scan_fragments = get_fragments_by_scan("SCAN_003")
    assert len(scan_fragments) == 2
    assert scan_fragments[0]['fragment_id'] == 'F001'
    assert scan_fragments[0]['byte_stats']['unique_bytes'] == 256
    print(f"Retrieved {len(scan_fragments)} fragments for scan")
    
    # Get fragments by file
    file_fragments = get_fragments_by_file("FILE_002")
    assert len(file_fragments) == 2
    print(f"Retrieved {len(file_fragments)} fragments for file")
    
    print("PASS")
    return True


def test_relationship_operations():
    """Test relationship operations."""
    print("\n" + "=" * 60)
    print("TEST: Relationship Operations")
    print("=" * 60)
    
    create_case("CASE_005", "Relationship Test Case")
    create_scan("SCAN_004", "CASE_005", "completed")
    save_file("FILE_003", "SCAN_004", "test.bin", "uploads/test.bin", 8192, "def456", "data", "application/octet-stream", 7.8)
    
    # Create fragments first (required for foreign key) - use unique IDs
    fragments = [
        {
            'fragment_id': 'REL_F001',
            'file_id': 'FILE_003',
            'scan_id': 'SCAN_004',
            'offset': 0,
            'size': 4096,
            'sha256': 'frag1_hash',
            'entropy': 7.5,
            'byte_stats': {'unique_bytes': 256, 'null_bytes': 10}
        },
        {
            'fragment_id': 'REL_F002',
            'file_id': 'FILE_003',
            'scan_id': 'SCAN_004',
            'offset': 4096,
            'size': 4096,
            'sha256': 'frag2_hash',
            'entropy': 7.6,
            'byte_stats': {'unique_bytes': 256, 'null_bytes': 12}
        },
        {
            'fragment_id': 'REL_F003',
            'file_id': 'FILE_003',
            'scan_id': 'SCAN_004',
            'offset': 8192,
            'size': 100,
            'sha256': 'frag3_hash',
            'entropy': 7.7,
            'byte_stats': {'unique_bytes': 200, 'null_bytes': 5}
        }
    ]
    save_fragments_bulk(fragments)
    print("Created 3 fragments for relationship test")
    
    # Save relationships bulk
    relationships = [
        {
            'fragment_a': 'REL_F001',
            'fragment_b': 'REL_F002',
            'scan_id': 'SCAN_004',
            'relationship_score': 0.95,
            'score_details': {'entropy_similarity': 0.99, 'size_similarity': 1.0},
            'scoring_method': 'random_forest'
        },
        {
            'fragment_a': 'REL_F001',
            'fragment_b': 'REL_F003',
            'scan_id': 'SCAN_004',
            'relationship_score': 0.72,
            'score_details': {'entropy_similarity': 0.85, 'size_similarity': 1.0},
            'scoring_method': 'baseline'
        }
    ]
    save_relationships_bulk(relationships)
    print("Saved 2 relationships")
    
    # Get relationships by scan
    scan_rels = get_relationships_by_scan("SCAN_004")
    assert len(scan_rels) == 2
    assert scan_rels[0]['relationship_score'] == 0.95  # Ordered by score desc
    assert scan_rels[0]['score_details']['entropy_similarity'] == 0.99
    assert scan_rels[0]['scoring_method'] == 'random_forest'
    print(f"Retrieved {len(scan_rels)} relationships for scan")
    
    print("PASS")
    return True


def test_reconstruction_operations():
    """Test reconstruction operations."""
    print("\n" + "=" * 60)
    print("TEST: Reconstruction Operations")
    print("=" * 60)
    
    create_case("CASE_006", "Reconstruction Test Case")
    create_scan("SCAN_005", "CASE_006", "completed")
    
    # Save reconstruction
    save_reconstruction(
        reconstruction_id="R001",
        scan_id="SCAN_005",
        fragment_ids=["F001", "F002", "F003"],
        integrity_score=0.92,
        confidence_score=0.88,
        evidence_quality="HIGH",
        priority="HIGH",
        status="STRONG_CANDIDATE",
        output_path="storage/reconstructed/R001_SCAN_005.bin",
        output_sha256="output_hash_123",
        output_size=12288,
        output_entropy=7.7,
        output_file_type="data",
        output_mime_type="application/octet-stream",
        validation_status="VALID",
        validation_details={
            'file_exists': True,
            'signature_detected': True,
            'structurally_valid': True
        }
    )
    print("Saved reconstruction R001")
    
    # Get reconstruction
    recon = get_reconstruction("R001")
    assert recon is not None
    assert recon['reconstruction_id'] == "R001"
    assert recon['fragment_ids'] == ["F001", "F002", "F003"]
    assert recon['integrity_score'] == 0.92
    assert recon['confidence_score'] == 0.88
    assert recon['validation_status'] == "VALID"
    assert recon['validation_details']['signature_detected'] == True
    print(f"Retrieved reconstruction: {recon['reconstruction_id']} ({recon['status']})")
    
    # Get reconstructions by scan
    scan_recons = get_reconstructions_by_scan("SCAN_005")
    assert len(scan_recons) == 1
    print(f"Retrieved {len(scan_recons)} reconstructions for scan")
    
    print("PASS")
    return True


def test_report_operations():
    """Test report operations."""
    print("\n" + "=" * 60)
    print("TEST: Report Operations")
    print("=" * 60)
    
    create_case("CASE_007", "Report Test Case")
    
    # Save report
    save_report(
        report_id="REPORT_001",
        case_id="CASE_007",
        scan_id="SCAN_001",
        reconstruction_id="R001",
        report_path="reports/report_001.json",
        report_data={
            'summary': 'Test report',
            'findings': ['Fragment 1', 'Fragment 2']
        }
    )
    print("Saved report REPORT_001")
    
    # Get reports by case
    reports = get_reports_by_case("CASE_007")
    assert len(reports) >= 1
    report = reports[0]
    assert report['report_id'] == "REPORT_001"
    assert report['report_data']['summary'] == "Test report"
    print(f"Retrieved {len(reports)} reports for case")
    
    print("PASS")
    return True


def test_full_scan_persistence():
    """Test persisting a complete scan result."""
    print("\n" + "=" * 60)
    print("TEST: Full Scan Result Persistence")
    print("=" * 60)
    
    create_case("CASE_008", "Full Persistence Test")
    
    # Create mock scan result
    scan_result = ScanResult(
        scan_id="SCAN_006",
        filename="evidence.pdf",
        size=5120,
        sha256="evidence_sha256_hash",
        file_type="PDF document",
        mime_type="application/pdf",
        entropy=4.8,
        status="completed",
        scanned_at=datetime.utcnow(),
        analysis={"header_bytes": "25504446", "null_bytes": 5},
        fragments=[],
        fragment_count=2,
        relationships=[],
        reconstructions=[]
    )
    
    # Create fragments - use unique IDs for this test
    fragments = [
        Fragment(
            fragment_id="PERSIST_F001",
            scan_id="SCAN_006",
            offset=0,
            size=4096,
            sha256="frag1_hash",
            entropy=4.7,
            byte_stats={'unique_bytes': 200, 'null_bytes': 2}
        ),
        Fragment(
            fragment_id="PERSIST_F002",
            scan_id="SCAN_006",
            offset=4096,
            size=1024,
            sha256="frag2_hash",
            entropy=4.9,
            byte_stats={'unique_bytes': 180, 'null_bytes': 3}
        )
    ]
    
    # Create relationships
    relationships = [
        Relationship(
            fragment_a="PERSIST_F001",
            fragment_b="PERSIST_F002",
            relationship_score=0.89,
            score_details={'entropy_similarity': 0.97, 'scoring_method': 'random_forest'}
        )
    ]
    
    # Create reconstruction
    recon = ReconstructionCandidate(
        reconstruction_id="PERSIST_R001",
        fragment_ids=["PERSIST_F001", "PERSIST_F002"],
        fragment_count=2,
        integrity_score=0.89,
        confidence_score=0.85,
        evidence_quality="MEDIUM",
        priority="MEDIUM",
        status="CANDIDATE",
        total_size=5120,
        avg_relationship_score=0.89,
        validation_details={}
    )
    
    # Persist everything
    result = persist_scan_result(
        case_id="CASE_008",
        scan_id="SCAN_006",
        scan_result=scan_result,
        fragments=fragments,
        relationships=relationships,
        reconstructions=[recon]
    )
    
    print(f"Persistence result: {result}")
    
    # Verify by reading back
    scan = get_scan("SCAN_006")
    assert scan is not None
    assert scan['case_id'] == "CASE_008"
    print(f"Scan verified: {scan['scan_id']}")
    
    files = get_files_by_scan("SCAN_006")
    assert len(files) == 1
    assert files[0]['filename'] == "evidence.pdf"
    print(f"File verified: {files[0]['filename']}")
    
    scan_fragments = get_fragments_by_scan("SCAN_006")
    assert len(scan_fragments) == 2
    assert scan_fragments[0]['fragment_id'] == "PERSIST_F001"
    print(f"Fragments verified: {len(scan_fragments)}")
    
    scan_rels = get_relationships_by_scan("SCAN_006")
    assert len(scan_rels) == 1
    assert scan_rels[0]['fragment_a'] == "PERSIST_F001"
    print(f"Relationships verified: {len(scan_rels)}")
    
    scan_recons = get_reconstructions_by_scan("SCAN_006")
    assert len(scan_recons) == 1
    assert scan_recons[0]['reconstruction_id'] == "PERSIST_R001"
    print(f"Reconstructions verified: {len(scan_recons)}")
    
    print("PASS")
    return True


def test_database_initialization():
    """Test database initialization and stats."""
    print("\n" + "=" * 60)
    print("TEST: Database Initialization")
    print("=" * 60)
    
    # Check database exists
    assert database_exists()
    print(f"Database exists: {database_exists()}")
    print(f"Database path: {get_database_path()}")
    
    # Get stats
    stats = get_database_stats()
    print(f"Database stats: {stats}")
    
    # Verify tables exist
    for table in ['cases', 'scans', 'files', 'fragments', 'relationships', 'reconstructions', 'reports']:
        assert table in stats
    
    print("PASS")
    return True


def test_repeated_initialization():
    """Test that repeated initialization doesn't destroy data."""
    print("\n" + "=" * 60)
    print("TEST: Repeated Initialization")
    print("=" * 60)
    
    # Get initial stats
    initial_stats = get_database_stats()
    
    # Re-initialize
    initialize_database()
    
    # Get stats again
    new_stats = get_database_stats()
    
    # Data should be preserved
    for table in initial_stats:
        assert new_stats[table] == initial_stats[table], f"Data lost in {table}"
    
    print(f"Initial stats: {initial_stats}")
    print(f"After re-init: {new_stats}")
    print("PASS: Data preserved after re-initialization")
    return True


def main():
    """Run all tests."""
    print("SQLITE PERSISTENCE LAYER - CONTROLLED DEMONSTRATION TESTS")
    print("Note: Using synthetic test data only. No forensic accuracy claimed.")
    print()
    
    # Setup test database
    setup_test_db()
    
    results = []
    results.append(("Database Initialization", test_database_initialization()))
    results.append(("Repeated Initialization", test_repeated_initialization()))
    results.append(("Case Operations", test_case_operations()))
    results.append(("Scan Operations", test_scan_operations()))
    results.append(("File Operations", test_file_operations()))
    results.append(("Fragment Operations", test_fragment_operations()))
    results.append(("Relationship Operations", test_relationship_operations()))
    results.append(("Reconstruction Operations", test_reconstruction_operations()))
    results.append(("Report Operations", test_report_operations()))
    results.append(("Full Scan Persistence", test_full_scan_persistence()))
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")
    
    all_passed = all(passed for _, passed in results)
    print(f"\nOverall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    
    return all_passed


if __name__ == "__main__":
    main()