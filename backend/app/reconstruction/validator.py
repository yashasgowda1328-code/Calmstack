"""
Structural Validation Module for Reconstructed Artifacts

Provides reusable validation for reconstructed file artifacts.
Checks basic structural validity using file signatures and metadata.
This is a Core Engine layer module - no FastAPI dependencies.
"""

import hashlib
import math
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class StructuralValidationResult:
    """Result of structural validation."""
    reconstruction_id: str
    file_exists: bool
    readable: bool
    size_valid: bool
    signature_detected: bool
    detected_type: str
    mime_type: str
    entropy: float
    is_binary: bool
    null_bytes: int
    unique_bytes: int
    header_bytes: str
    sha256: str
    structurally_valid: bool
    validation_status: str  # VALID, INVALID, UNKNOWN
    validation_notes: list[str]


class StructuralValidator:
    """
    Validates structural integrity of reconstructed artifacts.
    
    Checks:
    - File existence and readability
    - Size and hash validity
    - File signature/magic bytes detection
    - Entropy and binary/text characteristics
    """
    
    # Known file signatures (magic bytes)
    SIGNATURES = {
        # Images
        b'\xff\xd8\xff': ('JPEG', 'image/jpeg'),
        b'\x89PNG\r\n\x1a\n': ('PNG', 'image/png'),
        b'GIF87a': ('GIF', 'image/gif'),
        b'GIF89a': ('GIF', 'image/gif'),
        b'BM': ('BMP', 'image/bmp'),
        b'\x00\x00\x01\x00': ('ICO', 'image/x-icon'),
        # Documents
        b'%PDF': ('PDF', 'application/pdf'),
        b'PK\x03\x04': ('ZIP', 'application/zip'),
        b'PK\x05\x06': ('ZIP', 'application/zip'),
        b'PK\x07\x08': ('ZIP', 'application/zip'),
        b'\x1f\x8b': ('GZIP', 'application/gzip'),
        b'BZh': ('BZIP2', 'application/x-bzip2'),
        b'\xfd7zXZ\x00': ('7Z', 'application/x-7z-compressed'),
        b'Rar!\x1a\x07\x00': ('RAR', 'application/x-rar-compressed'),
        # Executables
        b'MZ': ('PE Executable', 'application/x-dosexec'),
        b'\x7fELF': ('ELF Executable', 'application/x-executable'),
        b'\xca\xfe\xba\xbe': ('Mach-O', 'application/x-mach-binary'),
        # Archives
        b'ustar': ('TAR', 'application/x-tar'),
        # Text-based (detected by content)
        b'<?xml': ('XML', 'application/xml'),
        b'<!DOCTYPE html': ('HTML', 'text/html'),
        b'<html': ('HTML', 'text/html'),
        b'{\n': ('JSON', 'application/json'),
        b'{\r\n': ('JSON', 'application/json'),
    }
    
    def __init__(self):
        pass
    
    def validate(self, file_path: Path, reconstruction_id: str = "") -> StructuralValidationResult:
        """
        Perform structural validation on a reconstructed artifact.
        
        Args:
            file_path: Path to the reconstructed artifact
            reconstruction_id: Optional reconstruction ID for tracking
            
        Returns:
            StructuralValidationResult with all validation details
        """
        notes = []
        
        # 1. File existence
        file_exists = file_path.exists() and file_path.is_file()
        if not file_exists:
            return StructuralValidationResult(
                reconstruction_id=reconstruction_id,
                file_exists=False,
                readable=False,
                size_valid=False,
                signature_detected=False,
                detected_type="Unknown",
                mime_type="application/octet-stream",
                entropy=0.0,
                is_binary=True,
                null_bytes=0,
                unique_bytes=0,
                header_bytes="",
                sha256="",
                structurally_valid=False,
                validation_status="INVALID",
                validation_notes=["File does not exist or is not a file"]
            )
        
        # 2. Readability and size
        try:
            file_size = file_path.stat().st_size
            size_valid = file_size > 0
            if not size_valid:
                notes.append("File size is zero")
            
            with open(file_path, "rb") as f:
                content = f.read()
            readable = True
        except Exception as e:
            return StructuralValidationResult(
                reconstruction_id=reconstruction_id,
                file_exists=True,
                readable=False,
                size_valid=False,
                signature_detected=False,
                detected_type="Unknown",
                mime_type="application/octet-stream",
                entropy=0.0,
                is_binary=True,
                null_bytes=0,
                unique_bytes=0,
                header_bytes="",
                sha256="",
                structurally_valid=False,
                validation_status="INVALID",
                validation_notes=[f"Cannot read file: {str(e)}"]
            )
        
        # 3. SHA-256
        sha256 = hashlib.sha256(content).hexdigest()
        
        # 4. Entropy
        entropy = self._calculate_entropy(content)
        
        # 5. Binary/text analysis
        is_binary, null_bytes, unique_bytes = self._analyze_binary(content)
        
        # 6. Header bytes (first 16 bytes)
        header_bytes = content[:16].hex() if len(content) >= 16 else content.hex()
        
        # 7. File signature detection
        detected_type, mime_type, signature_detected = self._detect_signature(content)
        if signature_detected:
            notes.append(f"Detected signature: {detected_type} ({mime_type})")
        else:
            notes.append("No recognized file signature detected")
        
        # 8. Determine structural validity
        structurally_valid = (
            file_exists and 
            readable and 
            size_valid and 
            signature_detected
        )
        
        # 9. Validation status
        if structurally_valid:
            validation_status = "VALID"
        elif not file_exists or not readable or not size_valid:
            validation_status = "INVALID"
        else:
            validation_status = "UNKNOWN"
        
        return StructuralValidationResult(
            reconstruction_id=reconstruction_id,
            file_exists=file_exists,
            readable=readable,
            size_valid=size_valid,
            signature_detected=signature_detected,
            detected_type=detected_type,
            mime_type=mime_type,
            entropy=entropy,
            is_binary=is_binary,
            null_bytes=null_bytes,
            unique_bytes=unique_bytes,
            header_bytes=header_bytes,
            sha256=sha256,
            structurally_valid=structurally_valid,
            validation_status=validation_status,
            validation_notes=notes
        )
    
    def _calculate_entropy(self, data: bytes) -> float:
        """Calculate Shannon entropy of data."""
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
    
    def _analyze_binary(self, data: bytes) -> tuple[bool, int, int]:
        """Analyze if data is binary/text and count null/unique bytes."""
        if not data:
            return True, 0, 0
        
        # Check if all bytes are printable ASCII or common whitespace
        text_chars = set(range(32, 127)) | {9, 10, 13}  # tab, newline, carriage return
        null_bytes = data.count(0)
        unique_bytes = len(set(data))
        is_binary = not all(b in text_chars for b in data[:min(100, len(data))])
        
        return is_binary, null_bytes, unique_bytes
    
    def _detect_signature(self, data: bytes) -> tuple[str, str, bool]:
        """Detect file signature from magic bytes."""
        if not data:
            return "Unknown", "application/octet-stream", False
        
        # Check known signatures
        for sig, (file_type, mime_type) in self.SIGNATURES.items():
            if data.startswith(sig):
                return file_type, mime_type, True
        
        # Fallback to python-magic if available
        try:
            import magic
            mime = magic.Magic(mime=True)
            mime_type = mime.from_buffer(data)
            file_type = magic.Magic().from_buffer(data)
            return file_type, mime_type, file_type != "data" and file_type != "Unknown"
        except Exception:
            pass
        
        # Heuristic for text files
        is_binary, _, _ = self._analyze_binary(data)
        if not is_binary:
            return "Text file", "text/plain", True
        
        return "Unknown", "application/octet-stream", False


def validate_artifact(file_path: Path, reconstruction_id: str = "") -> StructuralValidationResult:
    """
    Convenience function to validate a reconstructed artifact.
    """
    validator = StructuralValidator()
    return validator.validate(file_path, reconstruction_id)


# Integration helper for ReconstructionEngine
def add_structural_validation(
    engine,  # ReconstructionEngine instance
    result  # ReconstructionResult
) -> StructuralValidationResult:
    """
    Add structural validation to an existing reconstruction result.
    Call this after reconstruction to enhance the result.
    """
    if not result.output_path:
        return StructuralValidationResult(
            reconstruction_id=result.reconstruction_id,
            file_exists=False,
            readable=False,
            size_valid=False,
            signature_detected=False,
            detected_type="Unknown",
            mime_type="application/octet-stream",
            entropy=0.0,
            is_binary=True,
            null_bytes=0,
            unique_bytes=0,
            header_bytes="",
            sha256="",
            structurally_valid=False,
            validation_status="INVALID",
            validation_notes=["No output path available"]
        )
    
    validator = StructuralValidator()
    return validator.validate(Path(result.output_path), result.reconstruction_id)