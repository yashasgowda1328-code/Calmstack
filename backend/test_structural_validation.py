"""
Structural Validation Tests

Tests for the StructuralValidator module with controlled test cases.
"""

import os
import tempfile
from pathlib import Path

from app.reconstruction.validator import StructuralValidator, validate_artifact


def test_valid_text_file():
    """Test validation of a valid text file."""
    print("=" * 60)
    print("TEST: Valid Text File")
    print("=" * 60)
    
    content = b"This is a test text file.\nIt has multiple lines.\nAnd is readable."
    
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.txt', delete=False) as f:
        f.write(content)
        temp_path = Path(f.name)
    
    try:
        validator = StructuralValidator()
        result = validator.validate(temp_path, "TEST_001")
        
        print(f"File exists: {result.file_exists}")
        print(f"Readable: {result.readable}")
        print(f"Size valid: {result.size_valid}")
        print(f"Signature detected: {result.signature_detected}")
        print(f"Detected type: {result.detected_type}")
        print(f"MIME type: {result.mime_type}")
        print(f"Entropy: {result.entropy}")
        print(f"Is binary: {result.is_binary}")
        print(f"SHA-256: {result.sha256}")
        print(f"Structurally valid: {result.structurally_valid}")
        print(f"Validation status: {result.validation_status}")
        print(f"Notes: {result.validation_notes}")
        
        # Text file should be valid (even without magic bytes, it's detected as text)
        assert result.file_exists == True
        assert result.readable == True
        assert result.size_valid == True
        assert result.detected_type in ["Text file", "ASCII text"]
        assert result.mime_type == "text/plain"
        assert result.is_binary == False
        assert result.validation_status in ["VALID", "UNKNOWN"]
        
        print("PASS")
        return True
        
    finally:
        temp_path.unlink()


def test_valid_pdf_file():
    """Test validation of a PDF file with proper signature."""
    print("\n" + "=" * 60)
    print("TEST: Valid PDF File")
    print("=" * 60)
    
    # Minimal PDF structure
    content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n192\n%%EOF"
    
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.pdf', delete=False) as f:
        f.write(content)
        temp_path = Path(f.name)
    
    try:
        validator = StructuralValidator()
        result = validator.validate(temp_path, "TEST_002")
        
        print(f"File exists: {result.file_exists}")
        print(f"Readable: {result.readable}")
        print(f"Size valid: {result.size_valid}")
        print(f"Signature detected: {result.signature_detected}")
        print(f"Detected type: {result.detected_type}")
        print(f"MIME type: {result.mime_type}")
        print(f"Entropy: {result.entropy}")
        print(f"SHA-256: {result.sha256}")
        print(f"Structurally valid: {result.structurally_valid}")
        print(f"Validation status: {result.validation_status}")
        print(f"Notes: {result.validation_notes}")
        
        assert result.file_exists == True
        assert result.readable == True
        assert result.size_valid == True
        assert result.signature_detected == True
        assert "PDF" in result.detected_type
        assert result.mime_type == "application/pdf"
        assert result.structurally_valid == True
        assert result.validation_status == "VALID"
        
        print("PASS")
        return True
        
    finally:
        temp_path.unlink()


def test_valid_jpeg_file():
    """Test validation of a JPEG file with proper signature."""
    print("\n" + "=" * 60)
    print("TEST: Valid JPEG File")
    print("=" * 60)
    
    # JPEG signature + minimal data
    content = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00' + os.urandom(1000)
    
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.jpg', delete=False) as f:
        f.write(content)
        temp_path = Path(f.name)
    
    try:
        validator = StructuralValidator()
        result = validator.validate(temp_path, "TEST_003")
        
        print(f"File exists: {result.file_exists}")
        print(f"Readable: {result.readable}")
        print(f"Size valid: {result.size_valid}")
        print(f"Signature detected: {result.signature_detected}")
        print(f"Detected type: {result.detected_type}")
        print(f"MIME type: {result.mime_type}")
        print(f"Entropy: {result.entropy}")
        print(f"SHA-256: {result.sha256}")
        print(f"Structurally valid: {result.structurally_valid}")
        print(f"Validation status: {result.validation_status}")
        print(f"Notes: {result.validation_notes}")
        
        assert result.file_exists == True
        assert result.readable == True
        assert result.size_valid == True
        assert result.signature_detected == True
        assert result.detected_type == "JPEG"
        assert result.mime_type == "image/jpeg"
        assert result.structurally_valid == True
        assert result.validation_status == "VALID"
        
        print("PASS")
        return True
        
    finally:
        temp_path.unlink()


def test_valid_png_file():
    """Test validation of a PNG file with proper signature."""
    print("\n" + "=" * 60)
    print("TEST: Valid PNG File")
    print("=" * 60)
    
    content = b'\x89PNG\r\n\x1a\n' + os.urandom(1000)
    
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.png', delete=False) as f:
        f.write(content)
        temp_path = Path(f.name)
    
    try:
        validator = StructuralValidator()
        result = validator.validate(temp_path, "TEST_004")
        
        print(f"Detected type: {result.detected_type}")
        print(f"MIME type: {result.mime_type}")
        print(f"Signature detected: {result.signature_detected}")
        print(f"Structurally valid: {result.structurally_valid}")
        print(f"Validation status: {result.validation_status}")
        
        assert result.signature_detected == True
        assert result.detected_type == "PNG"
        assert result.mime_type == "image/png"
        assert result.validation_status == "VALID"
        
        print("PASS")
        return True
        
    finally:
        temp_path.unlink()


def test_valid_zip_file():
    """Test validation of a ZIP file with proper signature."""
    print("\n" + "=" * 60)
    print("TEST: Valid ZIP File")
    print("=" * 60)
    
    content = b'PK\x03\x04' + os.urandom(1000)
    
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.zip', delete=False) as f:
        f.write(content)
        temp_path = Path(f.name)
    
    try:
        validator = StructuralValidator()
        result = validator.validate(temp_path, "TEST_005")
        
        print(f"Detected type: {result.detected_type}")
        print(f"MIME type: {result.mime_type}")
        print(f"Signature detected: {result.signature_detected}")
        print(f"Structurally valid: {result.structurally_valid}")
        print(f"Validation status: {result.validation_status}")
        
        assert result.signature_detected == True
        assert result.detected_type == "ZIP"
        assert result.mime_type == "application/zip"
        assert result.validation_status == "VALID"
        
        print("PASS")
        return True
        
    finally:
        temp_path.unlink()


def test_corrupted_binary():
    """Test validation of corrupted/invalid binary data."""
    print("\n" + "=" * 60)
    print("TEST: Corrupted/Invalid Binary Data")
    print("=" * 60)
    
    # Random binary data with no recognizable signature
    content = os.urandom(2000)
    
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.bin', delete=False) as f:
        f.write(content)
        temp_path = Path(f.name)
    
    try:
        validator = StructuralValidator()
        result = validator.validate(temp_path, "TEST_006")
        
        print(f"File exists: {result.file_exists}")
        print(f"Readable: {result.readable}")
        print(f"Size valid: {result.size_valid}")
        print(f"Signature detected: {result.signature_detected}")
        print(f"Detected type: {result.detected_type}")
        print(f"MIME type: {result.mime_type}")
        print(f"Entropy: {result.entropy}")
        print(f"Is binary: {result.is_binary}")
        print(f"SHA-256: {result.sha256}")
        print(f"Structurally valid: {result.structurally_valid}")
        print(f"Validation status: {result.validation_status}")
        print(f"Notes: {result.validation_notes}")
        
        assert result.file_exists == True
        assert result.readable == True
        assert result.size_valid == True
        assert result.signature_detected == False
        assert result.detected_type in ["Unknown", "data"]
        assert result.mime_type == "application/octet-stream"
        assert result.structurally_valid == False
        assert result.validation_status == "UNKNOWN"
        
        print("PASS")
        return True
        
    finally:
        temp_path.unlink()


def test_empty_file():
    """Test validation of an empty file."""
    print("\n" + "=" * 60)
    print("TEST: Empty File")
    print("=" * 60)
    
    content = b""
    
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.bin', delete=False) as f:
        f.write(content)
        temp_path = Path(f.name)
    
    try:
        validator = StructuralValidator()
        result = validator.validate(temp_path, "TEST_007")
        
        print(f"File exists: {result.file_exists}")
        print(f"Readable: {result.readable}")
        print(f"Size valid: {result.size_valid}")
        print(f"Signature detected: {result.signature_detected}")
        print(f"Detected type: {result.detected_type}")
        print(f"Structurally valid: {result.structurally_valid}")
        print(f"Validation status: {result.validation_status}")
        print(f"Notes: {result.validation_notes}")
        
        assert result.file_exists == True
        assert result.readable == True
        assert result.size_valid == False
        assert result.structurally_valid == False
        assert result.validation_status == "INVALID"
        
        print("PASS")
        return True
        
    finally:
        temp_path.unlink()


def test_missing_file():
    """Test validation of a missing file path."""
    print("\n" + "=" * 60)
    print("TEST: Missing File")
    print("=" * 60)
    
    temp_path = Path("/nonexistent/path/file.bin")
    
    validator = StructuralValidator()
    result = validator.validate(temp_path, "TEST_008")
    
    print(f"File exists: {result.file_exists}")
    print(f"Readable: {result.readable}")
    print(f"Size valid: {result.size_valid}")
    print(f"Structurally valid: {result.structurally_valid}")
    print(f"Validation status: {result.validation_status}")
    print(f"Notes: {result.validation_notes}")
    
    assert result.file_exists == False
    assert result.readable == False
    assert result.size_valid == False
    assert result.structurally_valid == False
    assert result.validation_status == "INVALID"
    
    print("PASS")
    return True


def test_executable_file():
    """Test validation of an executable file (PE/MZ)."""
    print("\n" + "=" * 60)
    print("TEST: Executable File (PE/MZ)")
    print("=" * 60)
    
    content = b'MZ' + os.urandom(1000)
    
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.exe', delete=False) as f:
        f.write(content)
        temp_path = Path(f.name)
    
    try:
        validator = StructuralValidator()
        result = validator.validate(temp_path, "TEST_009")
        
        print(f"Detected type: {result.detected_type}")
        print(f"MIME type: {result.mime_type}")
        print(f"Signature detected: {result.signature_detected}")
        print(f"Structurally valid: {result.structurally_valid}")
        print(f"Validation status: {result.validation_status}")
        
        assert result.signature_detected == True
        assert "PE" in result.detected_type or "Executable" in result.detected_type
        assert result.validation_status == "VALID"
        
        print("PASS")
        return True
        
    finally:
        temp_path.unlink()


def main():
    """Run all tests."""
    print("STRUCTURAL VALIDATOR - CONTROLLED DEMONSTRATION TESTS")
    print("Note: Using synthetic test data only. No forensic accuracy claimed.")
    print()
    
    results = []
    results.append(("Valid Text File", test_valid_text_file()))
    results.append(("Valid PDF File", test_valid_pdf_file()))
    results.append(("Valid JPEG File", test_valid_jpeg_file()))
    results.append(("Valid PNG File", test_valid_png_file()))
    results.append(("Valid ZIP File", test_valid_zip_file()))
    results.append(("Corrupted Binary", test_corrupted_binary()))
    results.append(("Empty File", test_empty_file()))
    results.append(("Missing File", test_missing_file()))
    results.append(("Executable File", test_executable_file()))
    
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