"""
Reconstruction Engine Module

Creates reconstructed artifacts from reconstruction candidates.
This is a reusable Python module for the Core Engine layer.
"""

import hashlib
import os
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

from app.models.scan import Fragment, ReconstructionCandidate
from app.core.reconstruction import build_reconstructions
from app.reconstruction.validator import StructuralValidator, StructuralValidationResult


@dataclass
class ReconstructionResult:
    """Result of a reconstruction operation."""
    reconstruction_id: str
    output_path: str
    fragment_ids: list[str]
    output_size: int
    sha256: str
    status: str
    reconstructed_at: datetime
    file_type: str
    mime_type: str
    entropy: float
    missing_fragments: list[str]
    validation: dict
    structural_validation: Optional[StructuralValidationResult] = None


class ReconstructionEngine:
    """
    Reconstructs artifacts from ordered fragment sequences.
    
    Reads fragment bytes from the evidence file, concatenates them in order,
    and writes the result to storage/reconstructed/.
    """

    def __init__(
        self,
        upload_dir: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        fragment_size: int = 4096
    ):
        try:
            from app.config import get_uploads_dir, get_reconstructed_dir
            upload_dir = upload_dir or get_uploads_dir()
            output_dir = output_dir or get_reconstructed_dir()
        except ImportError:
            upload_dir = upload_dir or Path("uploads")
            output_dir = output_dir or Path("storage/reconstructed")

        self.upload_dir = Path(upload_dir)
        self.output_dir = Path(output_dir)
        self.fragment_size = fragment_size
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _find_evidence_file(self, scan_id: str) -> Optional[Path]:
        """Locate the uploaded evidence file for a scan."""
        for file_path in self.upload_dir.iterdir():
            if file_path.is_file() and file_path.stem == scan_id:
                return file_path
        return None

    def _read_fragment(self, evidence_file: Path, fragment: Fragment) -> bytes:
        """Read a single fragment's bytes from the evidence file."""
        with open(evidence_file, "rb") as f:
            f.seek(fragment.offset)
            return f.read(fragment.size)

    def _calculate_sha256(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _calculate_entropy(self, data: bytes) -> float:
        import math
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

    def _detect_file_type(self, file_path: Path) -> tuple[str, str]:
        """Detect file type using python-magic if available."""
        try:
            import magic
            mime = magic.Magic(mime=True)
            mime_type = mime.from_file(str(file_path))
            file_type = magic.Magic().from_file(str(file_path))
            return file_type, mime_type
        except Exception:
            extension = file_path.suffix.lower()
            mime_map = {
                ".exe": ("application/x-dosexec", "application/x-dosexec"),
                ".dll": ("application/x-dosexec", "application/x-dosexec"),
                ".pdf": ("PDF document", "application/pdf"),
                ".jpg": ("JPEG image", "image/jpeg"),
                ".jpeg": ("JPEG image", "image/jpeg"),
                ".png": ("PNG image", "image/png"),
                ".gif": ("GIF image", "image/gif"),
                ".zip": ("ZIP archive", "application/zip"),
                ".tar": ("TAR archive", "application/x-tar"),
                ".gz": ("GZIP archive", "application/gzip"),
                ".txt": ("Text file", "text/plain"),
                ".py": ("Python script", "text/x-python"),
                ".json": ("JSON file", "application/json"),
                ".xml": ("XML file", "application/xml"),
                ".html": ("HTML document", "text/html"),
            }
            return mime_map.get(extension, ("Unknown", "application/octet-stream"))

    def _validate_candidate(
        self,
        candidate: ReconstructionCandidate,
        fragments: list[Fragment]
    ) -> tuple[list[str], list[str]]:
        """Validate candidate fragments.
        
        Returns:
            available_fids: List of fragment IDs that exist
            missing_fids: List of fragment IDs that are missing or duplicate
        """
        frag_map = {f.fragment_id: f for f in fragments}
        available = []
        missing = []
        
        for fid in candidate.fragment_ids:
            if fid in frag_map:
                available.append(fid)
            else:
                missing.append(fid)
            # Check for duplicates
            if candidate.fragment_ids.count(fid) > 1:
                # Only report duplicate once
                if f"{fid} (duplicate)" not in missing:
                    missing.append(f"{fid} (duplicate)")
        
        return available, missing

    def reconstruct(
        self,
        candidate: ReconstructionCandidate,
        scan_id: str,
        fragments: list[Fragment]
    ) -> ReconstructionResult:
        """
        Reconstruct an artifact from a candidate.
        
        Args:
            candidate: The reconstruction candidate with ordered fragment IDs
            scan_id: The scan ID to locate the evidence file
            fragments: All fragments from the scan
            
        Returns:
            ReconstructionResult with artifact metadata
        """
        # Validate candidate - separate available from missing
        available_fids, missing_fids = self._validate_candidate(candidate, fragments)
        
        # Check for critical errors (duplicates only, not missing)
        duplicate_errors = [m for m in missing_fids if "(duplicate)" in m]
        if duplicate_errors:
            return ReconstructionResult(
                reconstruction_id=candidate.reconstruction_id,
                output_path="",
                fragment_ids=candidate.fragment_ids,
                output_size=0,
                sha256="",
                status="FAILED",
                reconstructed_at=datetime.utcnow(),
                file_type="Unknown",
                mime_type="application/octet-stream",
                entropy=0.0,
                missing_fragments=missing_fids,
                validation={"error": "Duplicate fragment IDs in candidate"}
            )

        # Find evidence file
        evidence_file = self._find_evidence_file(scan_id)
        if not evidence_file:
            return ReconstructionResult(
                reconstruction_id=candidate.reconstruction_id,
                output_path="",
                fragment_ids=candidate.fragment_ids,
                output_size=0,
                sha256="",
                status="FAILED",
                reconstructed_at=datetime.utcnow(),
                file_type="Unknown",
                mime_type="application/octet-stream",
                entropy=0.0,
                missing_fragments=[f"Evidence file not found for scan {scan_id}"],
                validation={"error": "Evidence file not found"}
            )

        # Read and concatenate available fragments
        frag_map = {f.fragment_id: f for f in fragments}
        output_data = bytearray()
        read_fragments = []
        
        for fid in candidate.fragment_ids:
            if fid not in frag_map:
                # Fragment not available - skip but track as missing
                continue
            try:
                fragment = frag_map[fid]
                fragment_data = self._read_fragment(evidence_file, fragment)
                output_data.extend(fragment_data)
                read_fragments.append(fid)
            except Exception as e:
                return ReconstructionResult(
                    reconstruction_id=candidate.reconstruction_id,
                    output_path="",
                    fragment_ids=candidate.fragment_ids,
                    output_size=0,
                    sha256="",
                    status="FAILED",
                    reconstructed_at=datetime.utcnow(),
                    file_type="Unknown",
                    mime_type="application/octet-stream",
                    entropy=0.0,
                    missing_fragments=[f"{fid}: {str(e)}"],
                    validation={"error": f"Failed to read fragment {fid}"}
                )

        # No fragments could be read
        if not read_fragments:
            return ReconstructionResult(
                reconstruction_id=candidate.reconstruction_id,
                output_path="",
                fragment_ids=candidate.fragment_ids,
                output_size=0,
                sha256="",
                status="FAILED",
                reconstructed_at=datetime.utcnow(),
                file_type="Unknown",
                mime_type="application/octet-stream",
                entropy=0.0,
                missing_fragments=missing_fids,
                validation={"error": "No fragments could be read"}
            )

        # Write artifact
        output_filename = f"{candidate.reconstruction_id}_{scan_id[:8]}.bin"
        output_path = self.output_dir / output_filename
        
        with open(output_path, "wb") as f:
            f.write(output_data)

        output_bytes = bytes(output_data)
        output_size = len(output_bytes)
        output_sha256 = self._calculate_sha256(output_bytes)
        output_entropy = self._calculate_entropy(output_bytes)
        file_type, mime_type = self._detect_file_type(output_path)

        # Determine status
        if len(read_fragments) < len(candidate.fragment_ids):
            status = "PARTIALLY_RECONSTRUCTED"
        else:
            status = "RECONSTRUCTED"

        validation = {
            "fragment_count": len(read_fragments),
            "expected_fragments": len(candidate.fragment_ids),
            "contiguous": self._check_contiguous(frag_map, read_fragments),
            "recognized_signature": file_type != "Unknown",
            "file_type_detected": file_type,
            "mime_type_detected": mime_type
        }

        # Perform structural validation
        validator = StructuralValidator()
        structural_validation = validator.validate(output_path, candidate.reconstruction_id)

        return ReconstructionResult(
            reconstruction_id=candidate.reconstruction_id,
            output_path=str(output_path),
            fragment_ids=read_fragments,
            output_size=output_size,
            sha256=output_sha256,
            status=status,
            reconstructed_at=datetime.utcnow(),
            file_type=file_type,
            mime_type=mime_type,
            entropy=output_entropy,
            missing_fragments=missing_fids,
            validation=validation,
            structural_validation=structural_validation
        )

    def _check_contiguous(self, frag_map: dict, fragment_ids: list[str]) -> bool:
        """Check if fragments are contiguous in the original file."""
        sorted_frags = sorted([frag_map[fid] for fid in fragment_ids], key=lambda f: f.offset)
        for i in range(len(sorted_frags) - 1):
            if sorted_frags[i].offset + sorted_frags[i].size != sorted_frags[i + 1].offset:
                return False
        return True

    def reconstruct_all(
        self,
        scan_id: str,
        fragments: list[Fragment],
        relationships: list,
        min_threshold: float = 0.70
    ) -> list[ReconstructionResult]:
        """
        Reconstruct all candidates for a scan.
        
        Returns list of ReconstructionResult objects.
        """
        candidates = build_reconstructions(fragments, relationships, min_threshold)
        results = []
        
        for candidate in candidates:
            result = self.reconstruct(candidate, scan_id, fragments)
            results.append(result)
        
        return results


def reconstruct_artifact(
    candidate: ReconstructionCandidate,
    scan_id: str,
    fragments: list[Fragment],
    upload_dir: Path = Path("uploads"),
    output_dir: Path = Path("storage/reconstructed")
) -> ReconstructionResult:
    """
    Convenience function to reconstruct a single artifact.
    """
    engine = ReconstructionEngine(upload_dir, output_dir)
    return engine.reconstruct(candidate, scan_id, fragments)