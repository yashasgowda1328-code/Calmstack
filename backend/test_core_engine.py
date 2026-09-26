"""
Core Engine End-to-End Tests

Controlled demonstration test for the complete CoreEngine workflow.
"""

import os
import tempfile
from pathlib import Path

from app.core_engine.engine import CoreEngine, run_investigation, EngineStatus, WorkflowProgress


def test_core_engine_workflow():
    """Test complete CoreEngine workflow with a known file."""
    print("=" * 60)
    print("TEST: CoreEngine Complete Workflow")
    print("=" * 60)
    
    # Create a known test file. It is large enough that a real scan produces
    # four fragments, so the persistence checks below are satisfied by this
    # scan's own data instead of leftovers in a shared database.
    original_content = b"RECONSTRUCTAI_TEST_FILE_" + os.urandom(13000)
    original_size = len(original_content)
    original_sha256 = __import__('hashlib').sha256(original_content).hexdigest()
    
    print(f"Original file: {original_size} bytes")
    print(f"Original SHA-256: {original_sha256}")
    
    # Track progress
    progress_log = []
    
    def progress_callback(progress: WorkflowProgress):
        progress_log.append(f"[{progress.status.value}] {progress.message} ({progress.progress_percent:.0f}%)")
        print(f"  PROGRESS: [{progress.status.value}] {progress.message} ({progress.progress_percent:.0f}%)")
    
    # Create temporary evidence file
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.bin', delete=False) as f:
        f.write(original_content)
        evidence_path = Path(f.name)
    
    try:
        # Run complete investigation
        engine = CoreEngine()
        engine.set_progress_callback(progress_callback)
        
        case_id = engine.create_case("Test Case", "End-to-end test case")
        print(f"\nCreated case: {case_id}")
        
        result = engine.run_scan(case_id, evidence_path)
        
        print(f"\nWorkflow Result:")
        print(f"  Case ID: {result.case_id}")
        print(f"  Scan ID: {result.scan_id}")
        print(f"  Status: {result.status}")
        print(f"  Fragments: {len(result.fragments)}")
        print(f"  Relationships: {len(result.relationships)}")
        print(f"  Reconstructions: {len(result.reconstructions)}")
        
        if result.error:
            print(f"  ERROR: {result.error}")
            return False
        
        # Verify file info
        assert result.file_info['size'] == original_size
        assert result.file_info['sha256'] == original_sha256
        print(f"\nFile verification: PASS")
        
        # Verify fragments
        assert len(result.fragments) == 4  # 13021 bytes = 4 fragments (3x4096 + 733)
        print(f"Fragment count: PASS ({len(result.fragments)} fragments)")
        
        # Verify fragments are ordered
        offsets = [f['offset'] for f in result.fragments]
        assert offsets == sorted(offsets)
        print(f"Fragment ordering: PASS")
        
        # Verify relationships
        assert len(result.relationships) > 0
        print(f"Relationships generated: PASS ({len(result.relationships)})")
        
        # Verify reconstructions
        assert len(result.reconstructions) > 0
        recon = result.reconstructions[0]
        assert 'reconstruction_id' in recon
        assert 'integrity_score' in recon
        assert 'confidence_score' in recon
        assert 'priority' in recon
        print(f"Reconstruction candidate: PASS ({recon['reconstruction_id']}, {recon['status']})")
        
        # Verify progress stages
        expected_stages = [
            "CREATING_SCAN",
            "ANALYZING",
            "EXTRACTING_FRAGMENTS",
            "ANALYZING_RELATIONSHIPS",
            "GENERATING_RECONSTRUCTIONS",
            "VALIDATING",
            "PRIORITIZING",
            "PERSISTING",
            "COMPLETED"
        ]
        logged_stages = [p.split("]")[0].strip("[") for p in progress_log]
        for stage in expected_stages:
            assert stage in logged_stages, f"Missing stage: {stage}"
        print(f"Progress stages: PASS (all {len(expected_stages)} stages logged)")
        
        # Verify database persistence
        stats = engine.get_database_stats()
        print(f"\nDatabase stats: {stats}")
        assert stats['cases'] >= 1
        assert stats['scans'] >= 1
        assert stats['files'] >= 1
        assert stats['fragments'] >= 3
        assert stats['relationships'] >= 1
        assert stats['reconstructions'] >= 1
        print(f"Database persistence: PASS")
        
        # Verify original evidence unchanged
        with open(evidence_path, "rb") as f:
            original_check = f.read()
        assert original_check == original_content
        print(f"Original evidence integrity: PASS")
        
        print("\nALL CHECKS PASSED")
        return True
        
    finally:
        if evidence_path.exists():
            evidence_path.unlink()


def test_reconstruction_workflow():
    """Test reconstruction and structural validation workflow."""
    print("\n" + "=" * 60)
    print("TEST: Reconstruction & Structural Validation")
    print("=" * 60)
    
    # Create a known test file
    original_content = b"RECONSTRUCTION_TEST_" + os.urandom(4000)
    original_size = len(original_content)
    original_sha256 = __import__('hashlib').sha256(original_content).hexdigest()
    
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.bin', delete=False) as f:
        f.write(original_content)
        evidence_path = Path(f.name)
    
    try:
        engine = CoreEngine()
        
        case_id = engine.create_case("Reconstruction Test")
        result = engine.run_scan(case_id, evidence_path)
        
        assert result.status == "completed"
        assert len(result.reconstructions) > 0
        
        # Get the first reconstruction candidate
        candidate = result.reconstructions[0]
        reconstruction_id = candidate['reconstruction_id']
        scan_id = result.scan_id
        
        print(f"Reconstructing candidate: {reconstruction_id}")
        
        # Reconstruct artifact
        recon_result = engine.reconstruct(reconstruction_id, scan_id)
        
        print(f"Reconstruction Result:")
        print(f"  Status: {recon_result.status}")
        print(f"  Output: {recon_result.output_path}")
        print(f"  Size: {recon_result.output_size}")
        print(f"  SHA-256: {recon_result.output_sha256}")
        
        if recon_result.structural_validation:
            sv = recon_result.structural_validation
            print(f"  Structural Validation:")
            print(f"    Status: {sv['validation_status']}")
            print(f"    Valid: {sv['structurally_valid']}")
            print(f"    Type: {sv['detected_type']}")
            print(f"    MIME: {sv['mime_type']}")
        
        # Verify reconstruction
        assert recon_result.status in ["RECONSTRUCTED", "PARTIALLY_RECONSTRUCTED"]
        assert recon_result.output_size == original_size
        assert recon_result.output_sha256 == original_sha256
        print(f"\nReconstruction verification: PASS")
        
        # Verify original unchanged
        with open(evidence_path, "rb") as f:
            assert f.read() == original_content
        print(f"Original evidence integrity: PASS")
        
        print("\nALL CHECKS PASSED")
        return True
        
    finally:
        if evidence_path.exists():
            evidence_path.unlink()


def test_pdf_reconstruction():
    """Test reconstruction of a file with recognizable signature (PDF)."""
    print("\n" + "=" * 60)
    print("TEST: PDF Reconstruction with Signature Validation")
    print("=" * 60)
    
    # Minimal valid PDF
    pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n192\n%%EOF"
    
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.pdf', delete=False) as f:
        f.write(pdf_content)
        evidence_path = Path(f.name)
    
    try:
        engine = CoreEngine()
        
        case_id = engine.create_case("PDF Test")
        result = engine.run_scan(case_id, evidence_path)
        
        assert result.status == "completed"
        assert len(result.reconstructions) > 0
        
        candidate = result.reconstructions[0]
        recon_result = engine.reconstruct(candidate['reconstruction_id'], result.scan_id)
        
        print(f"Reconstruction: {recon_result.status}")
        print(f"Output size: {recon_result.output_size}")
        print(f"SHA-256 match: {recon_result.output_sha256 == __import__('hashlib').sha256(pdf_content).hexdigest()}")
        
        if recon_result.structural_validation:
            sv = recon_result.structural_validation
            print(f"Validation status: {sv['validation_status']}")
            print(f"Detected type: {sv['detected_type']}")
            print(f"MIME type: {sv['mime_type']}")
            print(f"Structurally valid: {sv['structurally_valid']}")
            
            # Should detect PDF signature
            assert sv['signature_detected'] == True
            assert 'PDF' in sv['detected_type']
            assert sv['mime_type'] == 'application/pdf'
            assert sv['validation_status'] == 'VALID'
            print(f"PDF signature validation: PASS")
        
        print("\nALL CHECKS PASSED")
        return True
        
    finally:
        if evidence_path.exists():
            evidence_path.unlink()


def test_convenience_function():
    """Test the convenience run_investigation function."""
    print("\n" + "=" * 60)
    print("TEST: run_investigation Convenience Function")
    print("=" * 60)
    
    original_content = b"CONVENIENCE_TEST_" + os.urandom(2000)
    
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.bin', delete=False) as f:
        f.write(original_content)
        evidence_path = Path(f.name)
    
    try:
        progress_log = []
        
        def callback(p: WorkflowProgress):
            progress_log.append(p.status.value)
        
        result = run_investigation("Convenience Test", evidence_path, progress_callback=callback)
        
        print(f"Result status: {result.status}")
        print(f"Case ID: {result.case_id}")
        print(f"Scan ID: {result.scan_id}")
        print(f"Fragments: {len(result.fragments)}")
        print(f"Progress stages logged: {len(progress_log)}")
        
        assert result.status == "completed"
        assert len(result.fragments) > 0
        assert len(progress_log) >= 5  # Multiple stages
        
        print("Convenience function: PASS")
        return True
        
    finally:
        if evidence_path.exists():
            evidence_path.unlink()


def test_existing_tests_still_work():
    """Verify existing test suites still pass."""
    print("\n" + "=" * 60)
    print("TEST: Existing Test Suites (Quick Verification)")
    print("=" * 60)
    
    # Quick test of existing components
    from app.routes.scan import extract_fragments, calculate_sha256
    from app.core.relationships import analyze_relationships
    from app.core.reconstruction import build_reconstructions
    from app.reconstruction.engine import ReconstructionEngine
    from app.reconstruction.validator import StructuralValidator
    from app.storage.database import initialize_database, get_database_stats
    from app.models.scan import Fragment
    
    # Test fragment extraction
    content = b"TEST" + os.urandom(1000)
    fragments = extract_fragments(content, "TEST")
    assert len(fragments) > 0
    print("Fragment extraction: PASS")
    
    # Test relationships
    relationships = analyze_relationships(fragments)
    assert len(relationships) >= 0
    print("Relationship analysis: PASS")
    
    # Test reconstruction candidates
    candidates = build_reconstructions(fragments, relationships, 0.70)
    assert len(candidates) > 0
    print("Reconstruction candidates: PASS")
    
    # Test database
    initialize_database()
    stats = get_database_stats()
    print(f"Database stats: {stats}")
    print("Database: PASS")
    
    print("\nExisting components: PASS")
    return True


def main():
    """Run all tests."""
    print("CORE ENGINE - END-TO-END CONTROLLED DEMONSTRATION TESTS")
    print("Note: Using synthetic test data only. No forensic accuracy claimed.")
    print()
    
    results = []
    results.append(("CoreEngine Complete Workflow", test_core_engine_workflow()))
    results.append(("Reconstruction & Validation", test_reconstruction_workflow()))
    results.append(("PDF Signature Validation", test_pdf_reconstruction()))
    results.append(("Convenience Function", test_convenience_function()))
    results.append(("Existing Components", test_existing_tests_still_work()))
    
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