"""
ReConstructAI - Deleted Data Recovery Tests
Controlled test fixtures using synthetic raw images.
Note: Using synthetic test data only. No forensic accuracy claimed.
"""

import os
import sys
import hashlib
import struct
import tempfile
import random
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.recovery.models import DeletedDataCandidate, SourceExtent, RecoveryScanResult
from app.recovery.image_reader import ImageReader
from app.recovery.deleted_file_scanner import DeletedFileScanner
from app.recovery.candidate_extractor import CandidateExtractor


# File signatures
PDF_SIG = b"%PDF-1.4\n"
JPEG_SIG = b"\xff\xd8\xff\xe0"
PNG_SIG = b"\x89PNG\r\n\x1a\n"
ZIP_SIG = b"PK\x03\x04"
TEXT_SIG = b"Hello, World!"

def create_raw_image(path: str, blocks: bytes) -> None:
    """Create a raw .img file with given data blocks."""
    with open(path, "wb") as f:
        f.write(blocks)

def create_pdf_content(size: int = 100) -> bytes:
    """Create synthetic PDF content."""
    return PDF_SIG + b"Test PDF content " * (size // 20 + 1)

def create_jpeg_content(size: int = 100) -> bytes:
    """Create synthetic JPEG content."""
    return JPEG_SIG + b"JPEG data " * (size // 10 + 1)


def test_image_reader_basic():
    """Test ImageReader basic operations."""
    print("TEST: ImageReader Basic Operations")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = os.path.join(tmpdir, "test.dd")
        block_data = b"\x00" * 1024 + PDF_SIG + create_pdf_content(200) + b"\x00" * 1024
        create_raw_image(img_path, block_data)
        
        reader = ImageReader(img_path)
        
        # Image size
        assert reader.image_size == len(block_data), f"Expected {len(block_data)}, got {reader.image_size}"
        
        # Read bytes
        data = reader.read_bytes(1024, 8)
        assert data.startswith(PDF_SIG[:8]), f"Expected PDF signature, got {data[:8]}"
        
        print("  ImageReader basic operations: PASS")


def test_raw_signature_scanning():
    """Test raw signature scanning on image without filesystem."""
    print("TEST: Raw Signature Scanning")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = os.path.join(tmpdir, "test.img")
        
        # Create image with multiple signatures embedded
        blocks = b"\x00" * 512 + PDF_SIG + create_pdf_content(300) + b"\x00" * 512 + JPEG_SIG + create_jpeg_content(200) + b"\x00" * 512 + PNG_SIG + b"PNG data" + b"\x00" * 512
        create_raw_image(img_path, blocks)
        
        reader = ImageReader(img_path)
        extents = reader.scan_raw_signatures()
        
        assert len(extents) >= 3, f"Expected at least 3 signatures, got {len(extents)}"
        print(f"  Found {len(extents)} raw signatures")
        
        # Check offsets
        offsets = [e.offset for e in extents]
        assert 512 in offsets, "PDF offset not found"
        
        print("  Raw signature scanning: PASS")


def test_deleted_file_scanner_no_fs():
    """Test DeletedFileScanner fallback for images without filesystem."""
    print("TEST: Deleted File Scanner (No Filesystem)")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = os.path.join(tmpdir, "test.dd")
        
        # Create image with PDF signature
        pdf_data = PDF_SIG + create_pdf_content(500)
        block_data = b"\x00" * 1024 + pdf_data + b"\x00" * 2048
        create_raw_image(img_path, block_data)
        
        scanner = DeletedFileScanner(img_path)
        result = scanner.scan()
        
        assert result is not None
        assert len(result.candidates) >= 1, f"Expected at least 1 candidate, got {len(result.candidates)}"
        
        candidate = result.candidates[0]
        assert candidate.original_name is None
        assert candidate.file_type == "PDF"
        assert candidate.data_availability == "available"
        assert candidate.recovery_status == "NOT_EXTRACTED"
        
        print(f"  Found {len(result.candidates)} raw candidates")
        print("  No-filesystem scan: PASS")


def test_candidate_extractor():
    """Test CandidateExtractor extraction."""
    print("TEST: Candidate Extractor")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = os.path.join(tmpdir, "test.dd")
        output_dir = os.path.join(tmpdir, "recovered")
        
        # Create image with embedded PDF
        pdf_data = PDF_SIG + create_pdf_content(500)
        pdf_offset = 2048
        block_data = b"\x00" * pdf_offset + pdf_data + b"\x00" * 2048
        create_raw_image(img_path, block_data)
        
        # Create candidate
        candidate = DeletedDataCandidate(
            candidate_id="TEST001",
            image_path=img_path,
            original_name="deleted_file.pdf",
            inode=123,
            metadata_address=pdf_offset,
            size=len(pdf_data),
            file_type="PDF",
            mime_type="application/pdf",
            allocation_status="deleted",
            deleted_status=True,
            data_availability="available",
            source_extents=[SourceExtent(offset=pdf_offset, size=len(pdf_data))],
            recovery_status="NOT_EXTRACTED",
        )
        
        # Extract
        extractor = CandidateExtractor(output_dir=output_dir)
        result = extractor.extract_candidate(candidate)
        
        assert result.recovery_status == "EXTRACTED", f"Expected EXTRACTED, got {result.recovery_status}: {result.error}"
        assert result.extracted_path is not None
        assert os.path.exists(result.extracted_path), "Extracted file not found"
        
        # Verify content
        with open(result.extracted_path, "rb") as f:
            extracted_data = f.read()
        assert extracted_data[:len(PDF_SIG)] == PDF_SIG, "Extracted data signature mismatch"
        
        # Verify SHA-256
        expected_sha = hashlib.sha256(pdf_data).hexdigest()
        assert result.extracted_sha256 == expected_sha, f"SHA-256 mismatch: {result.extracted_sha256} != {expected_sha}"
        
        # Verify entropy
        assert result.extracted_entropy > 0, "Entropy should be > 0"
        
        print(f"  Extracted to: {result.extracted_path}")
        print(f"  SHA-256: {result.extracted_sha256}")
        print(f"  Entropy: {result.extracted_entropy}")
        print("  Candidate extraction: PASS")


def test_signature_detection():
    """Test file signature detection."""
    print("TEST: Signature Detection")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = os.path.join(tmpdir, "test.dd")
        create_raw_image(img_path, b"\x00" * 100)
        
        scanner = DeletedFileScanner(img_path)
        
        assert scanner._detect_file_signature(PDF_SIG + b"data") == "PDF"
        assert scanner._detect_file_signature(JPEG_SIG + b"data") == "JPEG"
        assert scanner._detect_file_signature(PNG_SIG + b"data") == "PNG"
        assert scanner._detect_file_signature(ZIP_SIG + b"data") == "ZIP"
        assert scanner._detect_file_signature(TEXT_SIG) == "Text"
        assert scanner._detect_file_signature(b"\x00\x01\x02\x03") == "Binary"
        assert scanner._detect_file_signature(b"") is None
    
    print("  PDF: PASS, JPEG: PASS, PNG: PASS, ZIP: PASS, Text: PASS, Binary: PASS")
    print("  Signature detection: PASS")


def test_candidate_model():
    """Test DeletedDataCandidate model properties."""
    print("TEST: Candidate Model Properties")
    
    # Recoverable candidate
    recoverable = DeletedDataCandidate(
        candidate_id="R001",
        image_path="/fake/path.img",
        size=1024,
        data_availability="available",
        recovery_status="NOT_EXTRACTED",
    )
    assert recoverable.is_recoverable == True
    assert recoverable.is_partial == False
    assert recoverable.is_unavailable == False
    
    # Partial candidate
    partial = DeletedDataCandidate(
        candidate_id="R002",
        image_path="/fake/path.img",
        size=1024,
        data_availability="partial",
        recovery_status="NOT_EXTRACTED",
    )
    assert partial.is_recoverable == True
    assert partial.is_partial == True
    assert partial.is_unavailable == False
    
    # Unavailable candidate
    unavailable = DeletedDataCandidate(
        candidate_id="R003",
        image_path="/fake/path.img",
        size=0,
        data_availability="unavailable",
        recovery_status="NOT_EXTRACTED",
    )
    assert unavailable.is_recoverable == False
    assert unavailable.is_partial == False
    assert unavailable.is_unavailable == True
    
    # Extracted candidate - still has available data but already extracted
    extracted = DeletedDataCandidate(
        candidate_id="R004",
        image_path="/fake/path.img",
        size=1024,
        data_availability="available",
        recovery_status="EXTRACTED",
        extracted_path="/fake/extracted.pdf",
        extracted_sha256="abc123",
        extracted_size=1024,
        extracted_entropy=5.5,
        extracted_file_type="PDF",
        extracted_mime_type="application/pdf",
    )
    # Extracted candidates still have data availability, so recoverable
    assert extracted.is_recoverable == True
    assert extracted.recovery_status == "EXTRACTED"
    
    # to_dict
    d = recoverable.to_dict()
    assert d["candidate_id"] == "R001"
    assert d["data_availability"] == "available"
    
    print("  Recoverable: PASS, Partial: PASS, Unavailable: PASS, Extracted: PASS, to_dict: PASS")
    print("  Candidate model: PASS")


def test_scan_result_model():
    """Test RecoveryScanResult model properties."""
    print("TEST: Scan Result Model")
    
    result = RecoveryScanResult(
        image_path="/fake/test.dd",
        filesystem_detected=True,
        filesystem_type="NTFS",
        candidate_count=3,
    )
    
    result.candidates = [
        DeletedDataCandidate(candidate_id="R001", image_path="/fake", data_availability="available"),
        DeletedDataCandidate(candidate_id="R002", image_path="/fake", data_availability="available"),
        DeletedDataCandidate(candidate_id="R003", image_path="/fake", data_availability="unavailable"),
    ]
    
    assert result.recoverable_count == 2
    assert result.unavailable_count == 1
    assert result.partial_count == 0
    
    print(f"  Recoverable: {result.recoverable_count}, Unavailable: {result.unavailable_count}")
    print("  Scan result model: PASS")


def test_full_raw_recovery_workflow():
    """Test full raw recovery workflow with multiple file types."""
    print("TEST: Full Raw Recovery Workflow")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = os.path.join(tmpdir, "evidence.dd")
        output_dir = os.path.join(tmpdir, "recovered")
        
        # Create a synthetic image with multiple deleted file signatures
        pdf_data = PDF_SIG + create_pdf_content(500)
        jpeg_data = JPEG_SIG + create_jpeg_content(300)
        png_data = PNG_SIG + b"PNG content " * 50
        
        # Build image: gap + PDF + gap + JPEG + gap + PNG + gap
        block_data = b"\x00" * 2048 + pdf_data + b"\x00" * 1024 + jpeg_data + b"\x00" * 1024 + png_data + b"\x00" * 2048
        create_raw_image(img_path, block_data)
        
        # Scan
        scanner = DeletedFileScanner(img_path)
        result = scanner.scan()
        
        print(f"  Found {len(result.candidates)} candidates")
        
        # Extract all
        extractor = CandidateExtractor(output_dir=output_dir)
        extracted_count = 0
        for candidate in result.candidates:
            if candidate.is_recoverable:
                extracted = extractor.extract_candidate(candidate)
                if extracted.recovery_status == "EXTRACTED":
                    extracted_count += 1
                    print(f"  Extracted {extracted.candidate_id}: {extracted.file_type} -> {extracted.extracted_path}")
        
        assert extracted_count >= 3, f"Expected at least 3 extracted files, got {extracted_count}"
        print(f"  Successfully extracted {extracted_count} files")
        print("  Full recovery workflow: PASS")


def test_missing_image():
    """Test handling of missing image file."""
    print("TEST: Missing Image Handling")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = os.path.join(tmpdir, "nonexistent.dd")
        
        scanner = DeletedFileScanner(img_path)
        result = scanner.scan()
        
        assert result.error is not None or len(result.candidates) == 0
        print("  Missing image handled gracefully: PASS")


def test_empty_image():
    """Test scanning an empty image."""
    print("TEST: Empty Image Handling")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        img_path = os.path.join(tmpdir, "empty.dd")
        create_raw_image(img_path, b"\x00" * 2048)
        
        scanner = DeletedFileScanner(img_path)
        result = scanner.scan()
        
        assert len(result.candidates) == 0 or result.warning is not None
        print("  Empty image handled gracefully: PASS")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("DELETED DATA RECOVERY - CONTROLLED TESTS")
    print("Note: Using synthetic test data only. No forensic accuracy claimed.")
    print("=" * 60 + "\n")
    
    tests = [
        test_image_reader_basic,
        test_raw_signature_scanning,
        test_deleted_file_scanner_no_fs,
        test_candidate_extractor,
        test_signature_detection,
        test_candidate_model,
        test_scan_result_model,
        test_full_raw_recovery_workflow,
        test_missing_image,
        test_empty_image,
    ]
    
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  FAILED: {e}")
    
    print("\n" + "=" * 60)
    print(f"SUMMARY: {passed}/{len(tests)} tests passed, {failed} failed")
    if failed == 0:
        print("Overall: ALL TESTS PASSED")
    else:
        print(f"Overall: {failed} TEST(S) FAILED")
    print("=" * 60 + "\n")
