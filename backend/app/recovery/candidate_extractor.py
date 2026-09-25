"""
ReConstructAI - Deleted Data Candidate Extraction
"""

from pathlib import Path
from typing import Optional, List, Dict, Any
import os
import hashlib
import math
import shutil

from app.recovery.models import DeletedDataCandidate, SourceExtent
from app.recovery.image_reader import ImageReader


class CandidateExtractor:
    """Extract deleted data candidates from storage images."""
    
    def __init__(self, output_dir: str = "storage/recovered_candidates"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def extract_candidate(self, candidate: DeletedDataCandidate) -> DeletedDataCandidate:
        """Extract a candidate to the recovery area."""
        try:
            reader = ImageReader(candidate.image_path)
            try:
                if not reader.open():
                    pass  # Fall through to raw extraction
            except Exception:
                pass  # Fall through to raw extraction
            
            # Determine output filename
            output_filename = self._safe_filename(candidate)
            output_path = self.output_dir / output_filename
            
            # Ensure no overwrite
            output_path = self._unique_path(output_path)
            
            # Read data
            data = self._read_candidate_data(reader, candidate)
            
            if not data:
                candidate.recovery_status = "EXTRACTION_FAILED"
                candidate.error = "No data available"
                reader.close()
                return candidate
            
            # Write output
            with open(output_path, "wb") as f:
                f.write(data)
            
            # Calculate metadata
            candidate.extracted_path = str(output_path)
            candidate.extracted_size = len(data)
            candidate.extracted_sha256 = self._calculate_sha256(data)
            candidate.extracted_entropy = self._calculate_entropy(data)
            candidate.extracted_file_type = self._detect_file_type(output_path)
            candidate.extracted_mime_type = self._detect_mime_type(output_path)
            candidate.extracted_signature = self._detect_signature(data)
            candidate.recovery_status = "EXTRACTED"
            
            reader.close()
            return candidate
            
        except Exception as e:
            candidate.recovery_status = "EXTRACTION_FAILED"
            candidate.error = str(e)
            return candidate
    
    def _safe_filename(self, candidate: DeletedDataCandidate) -> str:
        """Create a safe output filename."""
        original_name = candidate.original_name or "deleted_file"
        base_name = Path(original_name).name
        if not base_name or base_name in (".", ".."):
            base_name = "deleted_file"
        
        # Sanitize
        safe_name = "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in base_name)
        if not safe_name:
            safe_name = "deleted_file"
        
        return f"candidate_{candidate.candidate_id}_{safe_name}"
    
    def _unique_path(self, path: Path) -> Path:
        """Ensure path does not overwrite existing file."""
        if not path.exists():
            return path
        
        counter = 1
        while True:
            new_path = path.with_name(f"{path.stem}_{counter}{path.suffix}")
            if not new_path.exists():
                return new_path
            counter += 1
    
    def _read_candidate_data(self, reader: ImageReader, candidate: DeletedDataCandidate) -> bytes:
        """Read candidate data from source extents."""
        data = bytearray()
        
        # If no extents, try direct read
        if not candidate.source_extents:
            try:
                # Try to read using pytsk3 metadata
                if hasattr(candidate, "_meta"):
                    data.extend(reader.read_file_bytes(candidate._meta))
            except Exception:
                pass
            return bytes(data)
        
        # Read each extent
        for extent in candidate.source_extents:
            try:
                chunk = reader.read_bytes(extent.offset, extent.size)
                if chunk:
                    data.extend(chunk)
            except Exception:
                # Skip unavailable extents
                continue
        
        return bytes(data)
    
    def _calculate_sha256(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()
    
    def _calculate_entropy(self, data: bytes) -> float:
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
    
    def _detect_file_type(self, path: Path) -> str:
        try:
            import magic
            return magic.Magic().from_file(str(path))
        except Exception:
            return "Unknown"
    
    def _detect_mime_type(self, path: Path) -> str:
        try:
            import magic
            return magic.Magic(mime=True).from_file(str(path))
        except Exception:
            return "application/octet-stream"
    
    def _detect_signature(self, data: bytes) -> str:
        """Detect file signature from first bytes."""
        if not data:
            return None
        
        header = data[:16]
        if header.startswith(b"%PDF"):
            return "PDF"
        elif header.startswith(b"\x89PNG"):
            return "PNG"
        elif header.startswith(b"\xff\xd8\xff"):
            return "JPEG"
        elif header.startswith(b"PK\x03\x04"):
            return "ZIP"
        elif header.startswith(b"MZ"):
            return "PE"
        elif header.startswith(b"\x7fELF"):
            return "ELF"
        elif all(32 <= b <= 126 or b in (9, 10, 13) for b in header):
            return "Text"
        else:
            return "Binary"
