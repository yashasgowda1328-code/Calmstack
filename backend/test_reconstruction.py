"""
Controlled demonstration test for reconstruction engine.

This test verifies:
1. Original file -> split into fragments -> reconstructed
2. Output size matches original
3. Output SHA-256 matches original
4. Fragment ordering preserved
5. Partial reconstruction handling
"""

import hashlib
import math
import os
from pathlib import Path

from app.models.scan import Fragment
from app.core.relationships import analyze_relationships
from app.core.reconstruction import build_reconstructions
from app.reconstruction.engine import ReconstructionEngine


def calculate_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    byte_counts = [0] * 256
    for byte in data:
        byte_counts[byte] += 1
    entropy = 0.0
    data_len = len(data)
    for count in byte_counts:
        if count > 0:
            probability = count / data_len
            entropy -= probability * math.log2(probability)
    return round(entropy, 4)


def get_byte_stats(data: bytes) -> dict:
    if not data:
        return {}
    byte_counts = [0] * 256
    for byte in data:
        byte_counts[byte] += 1
    non_zero = [c for c in byte_counts if c > 0]
    return {
        "unique_bytes": len(non_zero),
        "null_bytes": byte_counts[0],
        "max_byte_freq": max(byte_counts) / len(data) if data else 0,
        "avg_byte_freq": sum(non_zero) / len(non_zero) if non_zero else 0,
    }


def create_fragments_from_content(original_content: bytes, scan_id: str) -> list[Fragment]:
    """Create fragments with proper entropy and byte_stats like the scan pipeline."""
    FRAGMENT_SIZE = 4096
    fragments = []
    total_size = len(original_content)
    fragment_count = (total_size + FRAGMENT_SIZE - 1) // FRAGMENT_SIZE
    
    for i in range(fragment_count):
        offset = i * FRAGMENT_SIZE
        chunk = original_content[offset:offset + FRAGMENT_SIZE]
        size = len(chunk)
        
        fragment = Fragment(
            fragment_id=f"F{i+1:03d}",
            scan_id=scan_id,
            offset=offset,
            size=size,
            sha256=hashlib.sha256(chunk).hexdigest(),
            entropy=calculate_entropy(chunk),
            byte_stats=get_byte_stats(chunk)
        )
        fragments.append(fragment)
    
    return fragments


def test_full_reconstruction():
    """Test full reconstruction from known fragments."""
    print("=" * 60)
    print("TEST: Full Reconstruction")
    print("=" * 60)
    
    # Create a known test file
    original_content = b"RECONSTRUCTAI_TEST_FILE_" + os.urandom(8000)
    original_size = len(original_content)
    original_sha256 = hashlib.sha256(original_content).hexdigest()
    
    print(f"Original file: {original_size} bytes")
    print(f"Original SHA-256: {original_sha256}")
    
    # Create fragments with proper metadata
    fragments = create_fragments_from_content(original_content, "TEST_SCAN_001")
    print(f"Created {len(fragments)} fragments")
    
    # Create fake evidence file in uploads
    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)
    evidence_file = upload_dir / "TEST_SCAN_001.bin"
    evidence_file.write_bytes(original_content)
    
    try:
        # Analyze relationships
        relationships = analyze_relationships(fragments)
        print(f"Generated {len(relationships)} relationships")
        
        # Build reconstruction candidates
        candidates = build_reconstructions(fragments, relationships, min_threshold=0.70)
        print(f"Generated {len(candidates)} reconstruction candidates")
        
        if not candidates:
            print("ERROR: No candidates generated")
            return False
        
        candidate = candidates[0]
        print(f"Candidate: {candidate.reconstruction_id}")
        print(f"Fragment IDs: {candidate.fragment_ids}")
        print(f"Status: {candidate.status}")
        
        # Reconstruct artifact
        engine = ReconstructionEngine(upload_dir=upload_dir)
        result = engine.reconstruct(candidate, "TEST_SCAN_001", fragments)
        
        print(f"\nReconstruction Result:")
        print(f"  Status: {result.status}")
        print(f"  Output: {result.output_path}")
        print(f"  Size: {result.output_size} bytes")
        print(f"  SHA-256: {result.sha256}")
        print(f"  File type: {result.file_type}")
        print(f"  MIME type: {result.mime_type}")
        print(f"  Entropy: {result.entropy}")
        print(f"  Validation: {result.validation}")
        
        # Verify against original
        success = True
        if result.output_size != original_size:
            print(f"FAIL: Size mismatch: {result.output_size} != {original_size}")
            success = False
        else:
            print(f"PASS: Size matches original ({original_size} bytes)")
        
        if result.sha256 != original_sha256:
            print(f"FAIL: SHA-256 mismatch")
            print(f"  Expected: {original_sha256}")
            print(f"  Got:      {result.sha256}")
            success = False
        else:
            print(f"PASS: SHA-256 matches original")
        
        if result.status != "RECONSTRUCTED":
            print(f"FAIL: Status is {result.status}, expected RECONSTRUCTED")
            success = False
        else:
            print(f"PASS: Status is RECONSTRUCTED")
        
        # Check fragment ordering
        expected_ids = [f.fragment_id for f in fragments]
        if result.fragment_ids != expected_ids:
            print(f"FAIL: Fragment ordering mismatch")
            print(f"  Expected: {expected_ids}")
            print(f"  Got:      {result.fragment_ids}")
            success = False
        else:
            print(f"PASS: Fragment ordering preserved")
        
        return success
        
    finally:
        # Cleanup
        if evidence_file.exists():
            evidence_file.unlink()


def test_partial_reconstruction():
    """Test partial reconstruction with missing fragments."""
    print("\n" + "=" * 60)
    print("TEST: Partial Reconstruction (Missing Fragments)")
    print("=" * 60)
    
    original_content = b"PARTIAL_TEST_" + os.urandom(8000)  # 3 fragments
    original_size = len(original_content)
    original_sha256 = hashlib.sha256(original_content).hexdigest()
    
    fragments = create_fragments_from_content(original_content, "TEST_SCAN_002")
    print(f"Created {len(fragments)} fragments: {[f.fragment_id for f in fragments]}")
    
    # Create evidence file
    upload_dir = Path("uploads")
    evidence_file = upload_dir / "TEST_SCAN_002.bin"
    evidence_file.write_bytes(original_content)
    
    try:
        from app.models.scan import ReconstructionCandidate
        
        # Simulate a candidate missing the middle fragment
        candidate = ReconstructionCandidate(
            reconstruction_id="R001",
            fragment_ids=["F001", "F003"],  # Skip F002
            fragment_count=2,
            integrity_score=0.8,
            confidence_score=0.75,
            evidence_quality="MEDIUM",
            priority="MEDIUM",
            status="CANDIDATE",
            total_size=8192,
            avg_relationship_score=0.8,
            validation_details={}
        )
        
        engine = ReconstructionEngine(upload_dir=upload_dir)
        result = engine.reconstruct(candidate, "TEST_SCAN_002", fragments)
        
        print(f"Result Status: {result.status}")
        print(f"Output Size: {result.output_size}")
        print(f"SHA-256: {result.sha256}")
        print(f"Missing: {result.missing_fragments}")
        print(f"Reconstructed fragments: {result.fragment_ids}")
        
        # Should be PARTIALLY_RECONSTRUCTED
        if result.status == "PARTIALLY_RECONSTRUCTED":
            print("PASS: Correctly identified as PARTIALLY_RECONSTRUCTED")
            return True
        else:
            print(f"FAIL: Expected PARTIALLY_RECONSTRUCTED, got {result.status}")
            return False
            
    finally:
        if evidence_file.exists():
            evidence_file.unlink()


def test_missing_evidence():
    """Test reconstruction with missing evidence file."""
    print("\n" + "=" * 60)
    print("TEST: Missing Evidence File")
    print("=" * 60)
    
    from app.models.scan import Fragment, ReconstructionCandidate
    
    fragments = [
        Fragment(
            fragment_id="F001",
            scan_id="NONEXISTENT_SCAN",
            offset=0,
            size=100,
            sha256="abc",
            entropy=1.0,
            byte_stats={}
        )
    ]
    
    candidate = ReconstructionCandidate(
        reconstruction_id="R001",
        fragment_ids=["F001"],
        fragment_count=1,
        integrity_score=0.8,
        confidence_score=0.75,
        evidence_quality="MEDIUM",
        priority="MEDIUM",
        status="CANDIDATE",
        total_size=100,
        avg_relationship_score=0.8,
        validation_details={}
    )
    
    engine = ReconstructionEngine()
    result = engine.reconstruct(candidate, "NONEXISTENT_SCAN", fragments)
    
    print(f"Result Status: {result.status}")
    print(f"Missing: {result.missing_fragments}")
    
    if result.status == "FAILED" and "Evidence file not found" in str(result.missing_fragments):
        print("PASS: Correctly handled missing evidence file")
        return True
    else:
        print(f"FAIL: Expected FAILED with evidence not found")
        return False


def test_empty_candidate():
    """Test reconstruction with invalid candidate."""
    print("\n" + "=" * 60)
    print("TEST: Empty/Invalid Candidate")
    print("=" * 60)
    
    from app.models.scan import Fragment, ReconstructionCandidate
    
    fragments = []
    candidate = ReconstructionCandidate(
        reconstruction_id="R001",
        fragment_ids=[],
        fragment_count=0,
        integrity_score=0.0,
        confidence_score=0.0,
        evidence_quality="LOW",
        priority="LOW",
        status="WEAK_CANDIDATE",
        total_size=0,
        avg_relationship_score=0.0,
        validation_details={}
    )
    
    engine = ReconstructionEngine()
    result = engine.reconstruct(candidate, "TEST_SCAN", fragments)
    
    print(f"Result Status: {result.status}")
    
    if result.status == "FAILED":
        print("PASS: Correctly handled empty candidate")
        return True
    else:
        print(f"FAIL: Expected FAILED")
        return False


def test_duplicate_fragments():
    """Test reconstruction with duplicate fragment IDs."""
    print("\n" + "=" * 60)
    print("TEST: Duplicate Fragment IDs")
    print("=" * 60)
    
    original_content = b"DUPLICATE_TEST_" + os.urandom(4000)
    fragments = create_fragments_from_content(original_content, "TEST_SCAN_003")
    
    upload_dir = Path("uploads")
    evidence_file = upload_dir / "TEST_SCAN_003.bin"
    evidence_file.write_bytes(original_content)
    
    try:
        from app.models.scan import ReconstructionCandidate
        
        # Candidate with duplicate
        candidate = ReconstructionCandidate(
            reconstruction_id="R001",
            fragment_ids=["F001", "F001", "F002"],  # Duplicate F001
            fragment_count=3,
            integrity_score=0.8,
            confidence_score=0.75,
            evidence_quality="MEDIUM",
            priority="MEDIUM",
            status="CANDIDATE",
            total_size=8192,
            avg_relationship_score=0.8,
            validation_details={}
        )
        
        engine = ReconstructionEngine(upload_dir=upload_dir)
        result = engine.reconstruct(candidate, "TEST_SCAN_003", fragments)
        
        print(f"Result Status: {result.status}")
        print(f"Missing: {result.missing_fragments}")
        
        if result.status == "FAILED" and any("duplicate" in m.lower() for m in result.missing_fragments):
            print("PASS: Correctly detected duplicate fragment IDs")
            return True
        else:
            print(f"FAIL: Expected FAILED with duplicate detection")
            return False
            
    finally:
        if evidence_file.exists():
            evidence_file.unlink()


def main():
    """Run all tests."""
    print("RECONSTRUCTION ENGINE - CONTROLLED DEMONSTRATION TESTS")
    print("Note: Using synthetic test data only. No forensic accuracy claimed.")
    print()
    
    results = []
    results.append(("Full Reconstruction", test_full_reconstruction()))
    results.append(("Partial Reconstruction", test_partial_reconstruction()))
    results.append(("Missing Evidence", test_missing_evidence()))
    results.append(("Empty Candidate", test_empty_candidate()))
    results.append(("Duplicate Fragments", test_duplicate_fragments()))
    
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