import hashlib
import math
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException
from app.models.scan import ScanResult, Fragment
from app.core.relationships import analyze_relationships
from app.core.reconstruction import build_reconstructions

router = APIRouter()

UPLOAD_DIR = Path("uploads")
FRAGMENT_SIZE = 4096
RECONSTRUCTION_THRESHOLD = 0.70


def calculate_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def detect_file_type(file_path: Path) -> tuple[str, str]:
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
            ".doc": ("Microsoft Word", "application/msword"),
            ".docx": ("Microsoft Word", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            ".xls": ("Microsoft Excel", "application/vnd.ms-excel"),
            ".xlsx": ("Microsoft Excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        }
        return mime_map.get(extension, ("Unknown", "application/octet-stream"))


def find_uploaded_file(scan_id: str) -> Path | None:
    for file_path in UPLOAD_DIR.iterdir():
        if file_path.is_file() and file_path.stem == scan_id:
            return file_path
    return None


def extract_fragments(content: bytes, scan_id: str) -> list[Fragment]:
    fragments = []
    total_size = len(content)
    fragment_count = (total_size + FRAGMENT_SIZE - 1) // FRAGMENT_SIZE
    
    for i in range(fragment_count):
        offset = i * FRAGMENT_SIZE
        chunk = content[offset:offset + FRAGMENT_SIZE]
        size = len(chunk)
        
        fragment = Fragment(
            fragment_id=f"F{i+1:03d}",
            scan_id=scan_id,
            offset=offset,
            size=size,
            sha256=calculate_sha256(chunk),
            entropy=calculate_entropy(chunk),
            byte_stats=get_byte_stats(chunk)
        )
        fragments.append(fragment)
    
    return fragments


@router.post("/scan/{scan_id}", response_model=ScanResult)
async def scan_evidence(scan_id: str):
    file_path = find_uploaded_file(scan_id)
    
    if not file_path:
        raise HTTPException(status_code=404, detail=f"Evidence with scan_id {scan_id} not found")
    
    with open(file_path, "rb") as f:
        content = f.read()
    
    size = len(content)
    sha256 = calculate_sha256(content)
    file_type, mime_type = detect_file_type(file_path)
    entropy = calculate_entropy(content)
    
    fragments = extract_fragments(content, scan_id)
    
    relationships = analyze_relationships(fragments)
    
    reconstructions = build_reconstructions(fragments, relationships, min_threshold=RECONSTRUCTION_THRESHOLD)
    
    analysis = {
        "header_bytes": content[:16].hex() if len(content) >= 16 else content.hex(),
        "is_binary": not all(32 <= b <= 126 or b in (9, 10, 13) for b in content[:100]),
        "null_bytes": content.count(0),
        "unique_bytes": len(set(content)),
    }
    
    return ScanResult(
        scan_id=scan_id,
        filename=file_path.name,
        size=size,
        sha256=sha256,
        file_type=file_type,
        mime_type=mime_type,
        entropy=entropy,
        status="completed",
        scanned_at=datetime.utcnow(),
        analysis=analysis,
        fragments=fragments,
        fragment_count=len(fragments),
        relationships=relationships,
        reconstructions=reconstructions
    )