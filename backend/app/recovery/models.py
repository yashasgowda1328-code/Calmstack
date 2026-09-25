"""
ReConstructAI - Deleted Data Recovery Models
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pathlib import Path


@dataclass
class SourceExtent:
    """A source byte range for a deleted file candidate."""
    
    offset: int
    size: int
    
    @property
    def end_offset(self) -> int:
        return self.offset + self.size


@dataclass
class DeletedDataCandidate:
    """A deleted/unallocated file candidate."""
    
    candidate_id: str
    image_path: str
    original_name: Optional[str] = None
    original_path: Optional[str] = None
    inode: Optional[int] = None
    metadata_address: Optional[int] = None
    size: int = 0
    file_type: Optional[str] = None
    mime_type: Optional[str] = None
    allocation_status: str = "unknown"
    deleted_status: bool = False
    data_availability: str = "unknown"
    source_extents: List[SourceExtent] = field(default_factory=list)
    recovery_status: str = "NOT_EXTRACTED"
    error: Optional[str] = None
    
    # Extraction results
    extracted_path: Optional[str] = None
    extracted_sha256: Optional[str] = None
    extracted_size: int = 0
    extracted_entropy: Optional[float] = None
    extracted_file_type: Optional[str] = None
    extracted_mime_type: Optional[str] = None
    extracted_signature: Optional[str] = None
    
    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_recoverable(self) -> bool:
        return self.data_availability in ("available", "partial") and self.recovery_status != "EXTRACTION_FAILED"
    
    @property
    def is_partial(self) -> bool:
        return self.data_availability == "partial"
    
    @property
    def is_unavailable(self) -> bool:
        return self.data_availability in ("unavailable", "none")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "image_path": self.image_path,
            "original_name": self.original_name,
            "original_path": self.original_path,
            "inode": self.inode,
            "metadata_address": self.metadata_address,
            "size": self.size,
            "file_type": self.file_type,
            "mime_type": self.mime_type,
            "allocation_status": self.allocation_status,
            "deleted_status": self.deleted_status,
            "data_availability": self.data_availability,
            "source_extents": [
                {"offset": e.offset, "size": e.size}
                for e in self.source_extents
            ],
            "recovery_status": self.recovery_status,
            "error": self.error,
            "extracted_path": self.extracted_path,
            "extracted_sha256": self.extracted_sha256,
            "extracted_size": self.extracted_size,
            "extracted_entropy": self.extracted_entropy,
            "extracted_file_type": self.extracted_file_type,
            "extracted_mime_type": self.extracted_mime_type,
            "extracted_signature": self.extracted_signature,
            "metadata": self.metadata,
        }


@dataclass
class RecoveryScanResult:
    """Result of scanning a storage image."""
    
    image_path: str
    filesystem_detected: bool = False
    filesystem_type: Optional[str] = None
    candidate_count: int = 0
    candidates: List[DeletedDataCandidate] = field(default_factory=list)
    error: Optional[str] = None
    warning: Optional[str] = None
    
    @property
    def recoverable_count(self) -> int:
        return sum(1 for c in self.candidates if c.is_recoverable)
    
    @property
    def unavailable_count(self) -> int:
        return sum(1 for c in self.candidates if c.is_unavailable)
    
    @property
    def partial_count(self) -> int:
        return sum(1 for c in self.candidates if c.is_partial)
