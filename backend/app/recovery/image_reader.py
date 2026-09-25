"""
ReConstructAI - Storage Image Reader
Safe read-only interface for forensic storage images using pytsk3.
"""

from pathlib import Path
from typing import Optional, Any, List, Dict
import os

SIGNATURES = {
    b"%PDF": "PDF",
    b"\x89PNG": "PNG",
    b"\xff\xd8\xff": "JPEG",
    b"PK\x03\x04": "ZIP",
    b"MZ": "PE",
    b"\x7fELF": "ELF",
}


class ImageReader:
    """Read-only storage image reader."""
    
    SUPPORTED_EXTENSIONS = {".dd", ".img"}
    
    def __init__(self, image_path: str):
        self.image_path = Path(image_path)
        self._img = None
        self._vol = None
        self._fs = None
        self._fs_info = None
    
    def open(self) -> bool:
        """Open the image and detect filesystem."""
        try:
            import pytsk3
            
            if not self.image_path.exists():
                raise FileNotFoundError(f"Image not found: {self.image_path}")
            
            if self.image_path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                raise ValueError(f"Unsupported image format: {self.image_path.suffix}")
            
            # Open image
            self._img = pytsk3.Img_Info(str(self.image_path))
            
            # Try to open volume system
            try:
                self._vol = pytsk3.Volume_Info(self._img)
            except Exception:
                self._vol = None
            
            # Try to open filesystem
            if self._vol is not None:
                # Try each partition
                try:
                    for part in self._vol:
                        try:
                            self._fs = pytsk3.FS_Info(self._img, part.addr)
                            self._fs_info = self._fs
                            break
                        except Exception:
                            continue
                except Exception:
                    self._fs = None
            else:
                # Try direct filesystem
                try:
                    self._fs = pytsk3.FS_Info(self._img)
                    self._fs_info = self._fs
                except Exception:
                    self._fs = None
            
            return self._fs is not None
            
        except Exception as e:
            self.close()
            raise e
    
    def close(self):
        """Close the image handle."""
        self._img = None
        self._vol = None
        self._fs = None
        self._fs_info = None
    
    @property
    def is_open(self) -> bool:
        return self._fs is not None
    
    @property
    def filesystem_type(self) -> Optional[str]:
        if self._fs_info is None:
            return None
        try:
            return str(self._fs_info.info.name)
        except Exception:
            return None

    @property
    def image_size(self) -> int:
        try:
            return self.image_path.stat().st_size
        except Exception:
            return 0

    def read_bytes(self, offset: int, size: int) -> bytes:
        """Read bytes from the image at the given offset."""
        try:
            if self._img is not None:
                return self._img.read(offset, size)
            else:
                with open(self.image_path, "rb") as f:
                    f.seek(offset)
                    return f.read(size)
        except Exception as e:
            raise RuntimeError(f"Failed to read image at offset {offset}: {str(e)}")

    def read_file_bytes(self, meta: Any, fs_attr: Any = None) -> bytes:
        """Read file content using pytsk3 metadata."""
        if self._fs is None:
            raise RuntimeError("Filesystem is not open")
        
        try:
            if fs_attr is None:
                fs_attr = meta
            return bytes(fs_attr.read_random(0, fs_attr.get_size()))
        except Exception as e:
            raise RuntimeError(f"Failed to read file content: {str(e)}")

    def iter_fs_entries(self):
        """Iterate over filesystem entries."""
        if self._fs is None:
            return
        
        try:
            for entry in self._fs:
                yield entry
        except Exception as e:
            raise RuntimeError(f"Failed to iterate filesystem: {str(e)}")

    def get_filesystem_info(self) -> Dict[str, Any]:
        """Return filesystem information."""
        if self._fs_info is None:
            return {}
        
        try:
            info = self._fs_info.info
            return {
                "type": str(info.name),
                "block_size": int(info.block_size),
                "dev_block_size": int(info.dev_block_size),
                "first_inum": int(info.first_inum),
                "last_inum": int(info.last_inum),
                "root_inum": int(info.root_inum),
                "meta_inum": int(info.meta_inum),
                "num_inum": int(info.num_inum),
            }
        except Exception:
            return {}
    
    def scan_raw_signatures(self, chunk_size: int = 4096) -> "List[SourceExtent]":
        """Scan raw image bytes for file signatures and return found extents.
        
        This is a fallback for images that don't have a recognized filesystem.
        Scans the raw bytes for known file signatures.
        """
        from app.recovery.models import SourceExtent
        
        extents = []
        if not self.image_path.exists():
            return extents
        
        try:
            file_size = self.image_path.stat().st_size
            found_offsets = set()
            with open(self.image_path, "rb") as f:
                offset = 0
                while offset < file_size:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    
                    # Search for signatures within the chunk
                    for sig, name in SIGNATURES.items():
                        search_start = 0
                        while search_start < len(chunk):
                            pos = chunk.find(sig, search_start)
                            if pos == -1:
                                break
                            sig_offset = offset + pos
                            if sig_offset in found_offsets:
                                search_start = pos + len(sig)
                                continue
                            found_offsets.add(sig_offset)
                            remaining = file_size - sig_offset
                            data_size = min(len(chunk) - pos, remaining)
                            extents.append(SourceExtent(offset=sig_offset, size=data_size))
                            search_start = pos + len(sig)
                    
                    offset += len(chunk)
                    
                    offset += len(chunk)
        
        except Exception:
            pass
        
        return extents
