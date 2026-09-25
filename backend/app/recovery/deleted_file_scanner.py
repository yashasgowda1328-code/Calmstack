"""
ReConstructAI - Deleted File Scanner
Discovers deleted/unallocated entries in a storage image using pytsk3.
"""

from pathlib import Path
from typing import Optional, List, Dict, Any
import os
import hashlib
import math

from app.recovery.models import DeletedDataCandidate, SourceExtent, RecoveryScanResult
from app.recovery.image_reader import ImageReader


class DeletedFileScanner:
    """Scan a storage image for deleted/unallocated file entries."""
    
    def __init__(self, image_path: str):
        self.image_path = Path(image_path)
        self._reader = None
    
    def scan(self) -> RecoveryScanResult:
        """Scan the image and return candidates."""
        result = RecoveryScanResult(image_path=str(self.image_path))
        
        try:
            self._reader = ImageReader(self.image_path)
            if not self._reader.open():
                result.warning = "No supported filesystem found in image"
                # Fall back to raw signature scanning
                raw_candidates = self._scan_raw_signatures()
                if raw_candidates:
                    result.candidates.extend(raw_candidates)
                    result.filesystem_detected = False
                    result.filesystem_type = "raw"
                result.candidate_count = len(result.candidates)
                return result
            
            result.filesystem_detected = True
            result.filesystem_type = self._reader.filesystem_type
            
            # Iterate filesystem entries
            try:
                for entry in self._reader.iter_fs_entries():
                    candidate = self._analyze_entry(entry)
                    if candidate is not None:
                        result.candidates.append(candidate)
            except Exception as e:
                result.warning = f"Partial scan completed with errors: {str(e)}"
            
            # Also do raw signature scanning for deleted files
            raw_candidates = self._scan_raw_signatures()
            if raw_candidates:
                result.candidates.extend(raw_candidates)
            
            result.candidate_count = len(result.candidates)
            return result
            
        except Exception as e:
            result.error = str(e)
            return result
        finally:
            if self._reader is not None:
                self._reader.close()
    
    def _scan_raw_signatures(self) -> List[DeletedDataCandidate]:
        """Scan raw image bytes for file signatures."""
        candidates = []
        
        try:
            if self._reader is None:
                self._reader = ImageReader(self.image_path)
                if not self._reader.open():
                    # Open as raw (no filesystem)
                    pass  # We can still read raw bytes
            
            if self._reader is None:
                self._reader = ImageReader(self.image_path)
            
            extents = self._reader.scan_raw_signatures()
            for i, extent in enumerate(extents):
                data = self._reader.read_bytes(extent.offset, extent.size)
                sig = self._detect_file_signature(data)
                
                candidate = DeletedDataCandidate(
                    candidate_id=f"RAW{i:04d}",
                    image_path=str(self.image_path),
                    original_name=None,
                    original_path=None,
                    inode=None,
                    metadata_address=extent.offset,
                    size=extent.size,
                    file_type=sig,
                    mime_type=self._detect_mime_from_name(sig),
                    allocation_status="unallocated",
                    deleted_status=True,
                    data_availability="available",
                    source_extents=[extent],
                    recovery_status="NOT_EXTRACTED",
                )
                candidates.append(candidate)
        
        except Exception:
            pass
        
        return candidates
    
    def _analyze_entry(self, entry: Any) -> Optional[DeletedDataCandidate]:
        """Analyze a filesystem entry and return a candidate if deleted."""
        try:
            # Get metadata
            meta = entry
            meta_addr = int(meta.addr)
            
            # Check if deleted/unallocated
            flags = int(meta.flags)
            is_deleted = bool(flags & 0x02)  # TSK_FS_META_FLAG_UNALLOC
            is_allocated = bool(flags & 0x01)  # TSK_FS_META_FLAG_ALLOC
            
            if not is_deleted and not is_allocated:
                return None
            
            # Get name
            name = self._get_name(entry)
            
            # Get size
            size = int(getattr(meta, "size", 0) or 0)
            
            # Get type
            meta_type = int(getattr(meta, "type", 0) or 0)
            if meta_type == 0:
                meta_type = 1  # Unknown
            
            # Determine data availability
            data_availability = self._determine_data_availability(meta, size)
            
            # Build candidate
            candidate_id = f"R{len(self._reader._fs_info.info.first_inum):03d}" if False else None
            candidate_id = f"R{meta_addr:03d}"
            
            candidate = DeletedDataCandidate(
                candidate_id=candidate_id,
                image_path=str(self.image_path),
                original_name=name,
                original_path=self._get_path(entry),
                inode=meta_addr,
                metadata_address=meta_addr,
                size=size,
                file_type=self._detect_file_type_from_name(name),
                mime_type=self._detect_mime_from_name(name),
                allocation_status="deleted" if is_deleted else "unallocated",
                deleted_status=is_deleted,
                data_availability=data_availability,
                source_extents=self._get_source_extents(meta, size),
                recovery_status="NOT_EXTRACTED",
            )
            
            # Add metadata
            candidate.metadata = self._extract_metadata(meta)
            
            return candidate
            
        except Exception as e:
            # Return a candidate with error if we can still identify it
            try:
                candidate = DeletedDataCandidate(
                    candidate_id=f"ERR{int(entry.addr):03d}",
                    image_path=str(self.image_path),
                    original_name=self._get_name(entry),
                    original_path=self._get_path(entry),
                    inode=int(entry.addr),
                    metadata_address=int(entry.addr),
                    size=int(getattr(entry, "size", 0) or 0),
                    allocation_status="unknown",
                    deleted_status=False,
                    data_availability="unavailable",
                    recovery_status="EXTRACTION_FAILED",
                    error=str(e),
                )
                return candidate
            except Exception:
                return None
    
    def _get_name(self, entry: Any) -> Optional[str]:
        """Get file name from entry."""
        try:
            # Try name attribute
            if hasattr(entry, "name"):
                name = entry.name
                if name:
                    return str(name)
        except Exception:
            pass
        
        try:
            # Try meta name
            if hasattr(entry, "meta") and hasattr(entry.meta, "name"):
                name = entry.meta.name
                if name:
                    return str(name)
        except Exception:
            pass
        
        return None
    
    def _get_path(self, entry: Any) -> Optional[str]:
        """Get file path from entry."""
        try:
            if hasattr(entry, "path"):
                return str(entry.path)
        except Exception:
            pass
        return None
    
    def _determine_data_availability(self, meta: Any, size: int) -> str:
        """Determine if data is available."""
        try:
            # Check if metadata has runs
            if hasattr(meta, "attr"):
                attr = meta.attr
                if attr is not None:
                    # Try to get size
                    try:
                        attr_size = int(attr.get_size())
                        if attr_size > 0:
                            return "available"
                    except Exception:
                        pass
            
            # Check for runs
            if hasattr(meta, "runs"):
                runs = meta.runs
                if runs is not None:
                    try:
                        if len(runs) > 0:
                            return "available"
                    except Exception:
                        pass
            
            # If size is 0, no data
            if size <= 0:
                return "unavailable"
            
            # Default to partial/unknown
            return "partial"
            
        except Exception:
            return "unknown"
    
    def _get_source_extents(self, meta: Any, size: int) -> List[SourceExtent]:
        """Get source extents for the file."""
        extents = []
        
        try:
            # Try to get runs
            if hasattr(meta, "runs"):
                runs = meta.runs
                if runs is not None:
                    try:
                        for run in runs:
                            try:
                                offset = int(run.addr)
                                run_size = int(run.len)
                                extents.append(SourceExtent(offset=offset, size=run_size))
                            except Exception:
                                continue
                    except Exception:
                        pass
            
            # Try attr runs
            if hasattr(meta, "attr") and meta.attr is not None:
                attr = meta.attr
                try:
                    if hasattr(attr, "nrd"):
                        nrd = attr.nrd
                        if nrd is not None:
                            try:
                                for run in nrd.runs:
                                    try:
                                        offset = int(run.addr)
                                        run_size = int(run.len)
                                        extents.append(SourceExtent(offset=offset, size=run_size))
                                    except Exception:
                                        continue
                            except Exception:
                                pass
                except Exception:
                    pass
            
            # If no extents found but size > 0, try to get from attr
            if not extents and size > 0:
                try:
                    if hasattr(meta, "attr") and meta.attr is not None:
                        attr = meta.attr
                        try:
                            if hasattr(attr, "rd"):
                                rd = attr.rd
                                if rd is not None:
                                    extents.append(SourceExtent(offset=0, size=size))
                        except Exception:
                            pass
                except Exception:
                    pass
            
        except Exception:
            pass
        
        return extents
    
    def _extract_metadata(self, meta: Any) -> Dict[str, Any]:
        """Extract additional metadata."""
        metadata = {}
        
        try:
            metadata["flags"] = int(meta.flags)
        except Exception:
            pass
        
        try:
            metadata["type"] = int(meta.type)
        except Exception:
            pass
        
        try:
            metadata["uid"] = int(meta.uid)
        except Exception:
            pass
        
        try:
            metadata["gid"] = int(meta.gid)
        except Exception:
            pass
        
        try:
            metadata["mode"] = int(meta.mode)
        except Exception:
            pass
        
        try:
            metadata["ctime"] = int(meta.ctime)
        except Exception:
            pass
        
        try:
            metadata["mtime"] = int(meta.mtime)
        except Exception:
            pass
        
        try:
            metadata["atime"] = int(meta.atime)
        except Exception:
            pass
        
        return metadata
    
    def _detect_file_type_from_name(self, name: Optional[str]) -> Optional[str]:
        """Detect file type from name."""
        if not name:
            return None
        
        ext = Path(name).suffix.lower()
        type_map = {
            ".pdf": "PDF",
            ".jpg": "JPEG",
            ".jpeg": "JPEG",
            ".png": "PNG",
            ".gif": "GIF",
            ".zip": "ZIP",
            ".txt": "Text",
            ".doc": "Word",
            ".docx": "Word",
            ".xls": "Excel",
            ".xlsx": "Excel",
            ".exe": "PE Executable",
            ".dll": "PE Executable",
        }
        return type_map.get(ext)
    
    def _detect_mime_from_name(self, name: Optional[str]) -> Optional[str]:
        """Detect MIME type from name."""
        if not name:
            return None
        
        ext = Path(name).suffix.lower()
        mime_map = {
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".zip": "application/zip",
            ".txt": "text/plain",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xls": "application/vnd.ms-excel",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".exe": "application/x-dosexec",
            ".dll": "application/x-dosexec",
        }
        return mime_map.get(ext)
    
    def _detect_file_signature(self, data: bytes) -> Optional[str]:
        """Detect file type from data signature."""
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
