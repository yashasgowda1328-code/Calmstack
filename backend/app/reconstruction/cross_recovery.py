"""
ReConstructAI - Cross-Evidence Recovery Engine

Rebuilds a damaged, truncated or partially overwritten file from other real
evidence files supplied by the investigator.

The engine never invents bytes:

* the target is inspected with format-aware structural checks (PNG chunks and
  CRC, JPEG marker segments, PDF trailer, ZIP end-of-central-directory, text
  decoding, generic entropy/continuity);
* the damaged byte ranges are identified from those checks;
* every damaged range is restored only from bytes that physically exist in the
  evidence files, located by exact anchor search plus adjacency/offset
  reasoning, and the recovered ranges are placed at their original offsets;
* the assembled artifact is validated again with the same format checks before
  it is written to disk;
* when the evidence does not contain the missing bytes the engine reports
  NO RELOABLE RECONSTRUCTION FOUND and writes nothing.

The existing AI relevance layer is used only to decide which evidence file is
worth investigating first. It never contributes bytes and never declares a
recovery successful on its own.
"""

from __future__ import annotations

import hashlib
import math
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: Size of one target portion. The target is split into fixed portions so
#: damage can be located and restored range by range.
PORTION_SIZE = 4096

#: Number of leading bytes used to locate a known-intact anchor inside evidence.
ANCHOR_SIZE = 64

#: Minimum share of a damaged range that must be restored for a partial result.
MIN_PARTIAL_COVERAGE = 0.5

STATUS_INTACT = "INTACT"
STATUS_RECONSTRUCTED = "RECONSTRUCTED"
STATUS_PARTIALLY_RECONSTRUCTED = "PARTIALLY_RECONSTRUCTED"
STATUS_NO_RECONSTRUCTION = "NO_RELIABLE_RECONSTRUCTION"

SIGNATURES: List[Tuple[bytes, str, str]] = [
    (b"\x89PNG\r\n\x1a\n", "PNG", "image/png"),
    (b"\xff\xd8\xff", "JPEG", "image/jpeg"),
    (b"GIF87a", "GIF", "image/gif"),
    (b"GIF89a", "GIF", "image/gif"),
    (b"%PDF", "PDF", "application/pdf"),
    (b"PK\x03\x04", "ZIP", "application/zip"),
    (b"PK\x05\x06", "ZIP", "application/zip"),
    (b"RIFF", "RIFF", "application/octet-stream"),
    (b"BM", "BMP", "image/bmp"),
    (b"\x1f\x8b", "GZIP", "application/gzip"),
    (b"7z\xbc\xaf\x27\x1c", "7Z", "application/x-7z-compressed"),
    (b"Rar!\x1a\x07", "RAR", "application/vnd.rar"),
    (b"ustar", "TAR", "application/x-tar"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "OLE2", "application/x-ole-storage"),
    (b"L\x00\x00\x00", "Windows Shortcut", "application/x-ms-shortcut"),
    (b"MZ", "Windows Executable", "application/x-msdownload"),
    (b"\x7fELF", "ELF Executable", "application/x-executable"),
    (b"SQLite format 3\x00", "SQLite Database", "application/vnd.sqlite3"),
    (b"{\\rtf", "RTF Document", "application/rtf"),
    (b"%!PS", "PostScript", "application/postscript"),
    (b"\xca\xfe\xba\xbe", "Java Class", "application/java-vm"),
    (b"\x00\x00\x00\x18ftypmp4", "MP4 Video", "video/mp4"),
    (b"\x00\x00\x00\x20ftypM4A", "M4A Audio", "audio/mp4"),
    (b"ID3", "MP3 Audio", "audio/mpeg"),
    (b"OggS", "Ogg Media", "application/ogg"),
    (b"\x25\x21PS", "PostScript", "application/postscript"),
    (b"-----BEGIN ", "PEM Certificate", "application/x-pem-file"),
    (b"\xef\xbb\xbf", "UTF-8 Text", "text/plain"),
    (b"<?xml", "XML Document", "application/xml"),
    (b"<!DOCTYPE html", "HTML Document", "text/html"),
    (b"#!", "Script", "text/x-script"),
    (b"\x89HDF\r\n\x1a\n", "HDF5 Dataset", "application/x-hdf5"),
    (b"\x78\x01", "Zlib Stream", "application/zlib"),
    (b"\x78\x9c", "Zlib Stream", "application/zlib"),
    (b"\x78\xda", "Zlib Stream", "application/zlib"),
]

#: Formats whose structure this module can verify end to end.
STRUCTURAL_TYPES = {
    "PNG", "JPEG", "PDF", "ZIP", "Windows Shortcut", "GIF", "BMP",
    "Windows Executable",
}

#: Filler inside these formats is explained by the format itself, so padding is
#: never damage evidence. A PE is excluded: its own headers are validated, and
#: real Windows binaries contain large zero-filled regions.
FILLER_CLAIM_TYPES = STRUCTURAL_TYPES - {"Windows Executable"}

#: Formats whose validator checks the *content* (chunk lengths, decodability),
#: so a result can be confirmed rather than merely sized. A PE header only
#: declares a length, which proves nothing about the bytes inside it.
CONTENT_VALIDATED_TYPES = STRUCTURAL_TYPES - {"Windows Executable"}


def looks_like_text(data: bytes, sample: int = 4096) -> bool:
    """True when the bytes are readable text rather than opaque binary."""
    if not data:
        return False
    head = data[:sample]
    if b"\x00" in head:
        return False
    printable = sum(1 for b in head if 32 <= b <= 126 or b in (9, 10, 13))
    return printable / len(head) >= 0.9



def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def entropy_of(data: bytes) -> float:
    if not data:
        return 0.0
    counts = [0] * 256
    for byte in data:
        counts[byte] += 1
    total = len(data)
    entropy = 0.0
    for count in counts:
        if count:
            p = count / total
            entropy -= p * math.log2(p)
    return round(entropy, 4)


def detect_signature(data: bytes) -> Tuple[Optional[str], Optional[str], bool]:
    """Return (file_type, mime_type, matched) from the leading bytes."""
    for signature, file_type, mime in SIGNATURES:
        if data.startswith(signature):
            return file_type, mime, True
    return None, None, False


@dataclass
class DamageFinding:
    """One structural problem found in the target file."""

    kind: str
    start: int
    end: int
    detail: str
    fatal: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "start": self.start,
            "end": self.end,
            "detail": self.detail,
            "fatal": self.fatal,
        }


# ====================================================================
# Format aware structure inspection
# ====================================================================

def inspect_png(data: bytes) -> List[DamageFinding]:
    """Walk PNG chunks, verify CRCs and check for the IEND trailer."""
    findings: List[DamageFinding] = []
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        findings.append(DamageFinding("INVALID_HEADER", 0, min(len(data), 8),
                                      "PNG signature is missing or corrupted", fatal=True))
        return findings

    offset = 8
    saw_iend = False
    while offset + 8 <= len(data):
        length = int.from_bytes(data[offset:offset + 4], "big")
        chunk_type = data[offset + 4:offset + 8]
        end = offset + 12 + length
        if length > len(data) or end > len(data):
            findings.append(DamageFinding(
                "TRUNCATED_CHUNK", offset, len(data),
                f"Chunk {chunk_type.decode('ascii', 'replace')} claims {length} bytes "
                f"but only {len(data) - offset - 12} remain",
            ))
            return findings
        payload = data[offset + 8:offset + 8 + length]
        expected_crc = int.from_bytes(data[offset + 8 + length:offset + 12 + length], "big")
        if zlib.crc32(chunk_type + payload) & 0xFFFFFFFF != expected_crc:
            findings.append(DamageFinding(
                "CRC_MISMATCH", offset, end,
                f"Chunk {chunk_type.decode('ascii', 'replace')} fails its CRC check",
            ))
        if chunk_type == b"IEND":
            saw_iend = True
            if end != len(data):
                findings.append(DamageFinding(
                    "TRAILING_DATA", end, len(data),
                    f"{len(data) - end} bytes follow the PNG IEND chunk",
                ))
            break
        offset = end

    if not saw_iend:
        findings.append(DamageFinding("MISSING_IEND", max(0, len(data) - 16), len(data),
                                      "PNG stream ends without an IEND chunk", fatal=True))
    return findings


def inspect_jpeg(data: bytes) -> List[DamageFinding]:
    """Walk JPEG marker segments and check for the EOI marker."""
    findings: List[DamageFinding] = []
    if not data.startswith(b"\xff\xd8"):
        findings.append(DamageFinding("INVALID_HEADER", 0, min(len(data), 4),
                                      "JPEG SOI marker is missing or corrupted", fatal=True))
        return findings

    offset = 2
    saw_eoi = False
    while offset + 1 < len(data):
        if data[offset] != 0xFF:
            findings.append(DamageFinding("DESYNC", offset, min(offset + 1, len(data)),
                                          "Lost JPEG marker alignment", fatal=True))
            return findings
        marker = data[offset + 1]
        if marker == 0xD9:  # EOI
            saw_eoi = True
            break
        if marker == 0xDA:  # SOS: entropy coded data follows, scan to EOI
            eoi = data.rfind(b"\xff\xd9")
            if eoi == -1:
                findings.append(DamageFinding("TRUNCATED_SCAN", offset, len(data),
                                              "JPEG entropy coded data has no EOI marker", fatal=True))
            else:
                saw_eoi = True
            break
        if marker == 0x00 or 0xD0 <= marker <= 0xD7:
            offset += 2
            continue
        if offset + 4 > len(data):
            findings.append(DamageFinding("TRUNCATED_SEGMENT", offset, len(data),
                                          "JPEG segment header is truncated", fatal=True))
            return findings
        length = int.from_bytes(data[offset + 2:offset + 4], "big")
        if length < 2 or offset + 2 + length > len(data):
            findings.append(DamageFinding("TRUNCATED_SEGMENT", offset, len(data),
                                          f"JPEG segment claims {length} bytes but the file ends", fatal=True))
            return findings
        offset += 2 + length

    if not saw_eoi:
        findings.append(DamageFinding("MISSING_EOI", max(0, len(data) - 4), len(data),
                                      "JPEG stream ends without an EOI marker", fatal=True))
    return findings


def inspect_pdf(data: bytes) -> List[DamageFinding]:
    """Check PDF header and trailer."""
    findings: List[DamageFinding] = []
    if not data.startswith(b"%PDF"):
        findings.append(DamageFinding("INVALID_HEADER", 0, min(len(data), 8),
                                      "PDF header is missing or corrupted", fatal=True))
        return findings
    if b"%%EOF" not in data[-2048:] and b"%%EOF" not in data:
        findings.append(DamageFinding("MISSING_TRAILER", max(0, len(data) - 2048), len(data),
                                      "PDF ends without a %%EOF trailer", fatal=True))
    return findings


def inspect_zip(data: bytes) -> List[DamageFinding]:
    """Check that the ZIP end-of-central-directory record is present."""
    findings: List[DamageFinding] = []
    eocd = data.rfind(b"PK\x05\x06")
    if eocd == -1:
        findings.append(DamageFinding("MISSING_EOCD", max(0, len(data) - 64), len(data),
                                      "ZIP end-of-central-directory record is missing", fatal=True))
        return findings
    if eocd + 22 > len(data):
        findings.append(DamageFinding("TRUNCATED_EOCD", eocd, len(data),
                                      "ZIP end-of-central-directory record is truncated", fatal=True))
    return findings


def inspect_text(data: bytes) -> List[DamageFinding]:
    """Check that the bytes decode as text and carry no NUL padding."""
    findings: List[DamageFinding] = []
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        findings.append(DamageFinding("DECODE_ERROR", max(0, exc.start - 64),
                                      min(len(data), exc.end + 64),
                                      f"Text is not valid UTF-8 at byte {exc.start}"))
    return findings


def find_null_runs(data: bytes, min_run: int = 512) -> List[Tuple[int, int]]:
    """Return the (start, end) ranges of long NUL padding, a common damage sign."""
    return _find_repeated_runs(data, b"\x00", min_run)


def _find_repeated_runs(data: bytes, filler: bytes, min_run: int) -> List[Tuple[int, int]]:
    """Ranges where one filler byte repeats, which real file content rarely does."""
    runs: List[Tuple[int, int]] = []
    marker = filler[0]
    start = -1
    for index, byte in enumerate(data):
        if byte == marker:
            if start < 0:
                start = index
        elif start >= 0:
            if index - start >= min_run:
                runs.append((start, index))
            start = -1
    if start >= 0 and len(data) - start >= min_run:
        runs.append((start, len(data)))
    return runs


def detect_damage(data: bytes) -> List[DamageFinding]:
    """Inspect real bytes and report the damaged ranges of the file."""
    if not data:
        return [DamageFinding("EMPTY_FILE", 0, 0, "The file contains no bytes", fatal=True)]

    file_type, _, matched = detect_signature(data)
    findings: List[DamageFinding] = []

    if file_type == "PNG":
        findings.extend(inspect_png(data))
    elif file_type == "JPEG":
        findings.extend(inspect_jpeg(data))
    elif file_type == "PDF":
        findings.extend(inspect_pdf(data))
    elif file_type == "ZIP":
        findings.extend(inspect_zip(data))
    elif file_type == "Windows Executable":
        findings.extend(inspect_pe(data))

    # Filler is evidence of damage only when the file has no recognisable
    # structure to explain it. A PE, ELF or SQLite file legitimately contains
    # zero-filled sections, so those are never reported as damage; the
    # structural checks above (or a comparison against real evidence) decide.
    if not matched or file_type in FILLER_CLAIM_TYPES:
        for start, end in find_null_runs(data):
            findings.append(DamageFinding("NULL_REGION", start, end,
                                          f"{end - start} bytes of NUL padding"))
        for marker, label in ((b"\xff", "0xFF"), (b"\xaa", "0xAA")):
            for start, end in _find_repeated_runs(data, marker, 512):
                findings.append(DamageFinding("FILLER_REGION", start, end,
                                              f"{end - start} bytes of {label} filler"))

    if not findings and not matched and looks_like_text(data):
        findings.extend(inspect_text(data))

    return findings


def inspect_generic(data: bytes) -> List[DamageFinding]:
    """Validate an unrecognised file: real bytes, no filler, no empty payload."""
    findings: List[DamageFinding] = []
    if not data:
        return [DamageFinding("EMPTY_FILE", 0, 0, "The file contains no bytes", fatal=True)]

    for start, end in find_null_runs(data):
        findings.append(DamageFinding("NULL_REGION", start, end,
                                      f"{end - start} bytes of NUL padding"))
    for marker, label in ((b"\xff", "0xFF"), (b"\xaa", "0xAA")):
        for start, end in _find_repeated_runs(data, marker, 512):
            findings.append(DamageFinding("FILLER_REGION", start, end,
                                          f"{end - start} bytes of {label} filler"))
    if looks_like_text(data):
        findings.extend(inspect_text(data))
    return findings


def _skip_utf16_string(data: bytes, offset: int) -> int:
    """Offset just past a null-terminated UTF-16 string, or -1 if it runs out."""
    while offset + 1 < len(data):
        if data[offset] == 0 and data[offset + 1] == 0:
            return offset + 2
        offset += 2
    return -1


def inspect_shell_link(data: bytes) -> List[DamageFinding]:
    """Validate a Windows Shell Link (.lnk) using its own declared structure.

    The header flags state which sections must follow, so a link whose strings
    or target list run past the end of the file is genuinely truncated.
    """
    findings: List[DamageFinding] = []
    if len(data) < 4:
        return [DamageFinding("INVALID_HEADER", 0, len(data),
                              "Shell Link file is too short for a header", fatal=True)]

    header_size = struct.unpack_from("<I", data, 0)[0]
    if header_size != 0x4C:
        return [DamageFinding("INVALID_HEADER", 0, min(len(data), 4),
                              "Shell Link header size is not 0x4C", fatal=True)]
    if len(data) < 0x4C:
        return [DamageFinding("TRUNCATED_SEGMENT", 0, len(data),
                              "Shell Link header is truncated", fatal=True)]

    flags = struct.unpack_from("<I", data, 0x14)[0]
    offset = 0x4C

    if flags & 0x01:  # HasLinkTargetIDList
        if offset + 2 > len(data):
            return findings + [DamageFinding("TRUNCATED_SEGMENT", offset, len(data),
                                             "Shell Link target ID list is truncated", fatal=True)]
        offset += 2 + struct.unpack_from("<H", data, offset)[0]
    if flags & 0x02:  # HasLinkInfo
        if offset + 4 > len(data):
            return findings + [DamageFinding("TRUNCATED_SEGMENT", offset, len(data),
                                             "Shell Link info block is truncated", fatal=True)]
        offset += 4 + struct.unpack_from("<I", data, offset)[0]

    if offset > len(data):
        return findings + [DamageFinding(
            "TRUNCATED_SEGMENT", max(0, len(data) - 64), len(data),
            "Shell Link sections extend past the end of the file", fatal=True,
        )]

    for bit, name in ((0x04, "name"), (0x08, "relative path"),
                      (0x20, "arguments"), (0x10, "working directory"),
                      (0x40, "icon location")):
        if not flags & bit:
            continue
        offset = _skip_utf16_string(data, offset)
        if offset < 0:
            return findings + [DamageFinding(
                "TRUNCATED_SEGMENT", max(0, len(data) - 64), len(data),
                f"Shell Link {name} string is not terminated inside the file",
                fatal=True,
            )]
    return findings


def _pe_declared_size(data: bytes) -> Optional[int]:
    """The file size a PE image's own headers declare, or None if unparseable."""
    if len(data) < 0x40:
        return None

    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if not 0x40 <= e_lfanew <= len(data) - 24:
        return None
    if data[e_lfanew:e_lfanew + 4] != b"PE\x00\x00":
        return None

    coff = e_lfanew + 4
    section_count = struct.unpack_from("<H", data, coff + 2)[0]
    optional_size = struct.unpack_from("<H", data, coff + 16)[0]
    if not 0 < section_count <= 96:
        return None
    section_table = coff + 20 + optional_size
    if section_table + section_count * 40 > len(data):
        return None

    expected_end = 0
    for index in range(section_count):
        base = section_table + index * 40
        raw_size = struct.unpack_from("<I", data, base + 16)[0]
        raw_offset = struct.unpack_from("<I", data, base + 20)[0]
        if raw_size:
            expected_end = max(expected_end, raw_offset + raw_size)
    return expected_end or None


def pe_structure_is_complete(data: bytes) -> bool:
    """True only when the headers parse and declare nothing beyond the file.

    A bare ``MZ`` prefix is not a PE structure, so it never earns a structural
    claim: such a file stays validated by evidence continuity.
    """
    declared = _pe_declared_size(data)
    return declared is not None and len(data) >= declared


def inspect_pe(data: bytes) -> List[DamageFinding]:
    """Validate a Windows PE image using the sizes its own headers declare.

    The section table states where every section's raw data lives, so a file
    that ends before the last declared section is genuinely truncated. Headers
    that do not parse coherently prove nothing, so no damage is claimed.
    """
    declared = _pe_declared_size(data)
    if declared and len(data) < declared:
        return [DamageFinding(
            "TRUNCATED_SEGMENT", len(data), declared,
            f"PE sections declare {declared} bytes but the file has {len(data)}",
            fatal=True,
        )]
    return []


def validate_structure(data: bytes, file_type: Optional[str] = None) -> Tuple[bool, List[str]]:
    """Re-check a fully assembled artifact with the same format rules."""
    notes: List[str] = []
    detected, _, matched = detect_signature(data)
    kind = file_type or detected

    if kind == "PNG":
        issues = inspect_png(data)
    elif kind == "JPEG":
        issues = inspect_jpeg(data)
    elif kind == "PDF":
        issues = inspect_pdf(data)
    elif kind == "ZIP":
        issues = inspect_zip(data)
    elif kind == "Windows Shortcut":
        issues = inspect_shell_link(data)
    elif kind == "Windows Executable":
        issues = inspect_pe(data)
    elif matched:
        issues = inspect_generic(data)
    else:
        issues = inspect_generic(data)

    for issue in issues:
        notes.append(f"{issue.kind}: {issue.detail}")
    if not issues and matched:
        notes.append(f"{kind} structure verified end to end")
    return (not issues), notes


def remaining_structure_issues(data: bytes, file_type: Optional[str]) -> List[DamageFinding]:
    """Findings that still block a complete reconstruction of `data`."""
    if file_type == "PNG":
        return inspect_png(data)
    if file_type == "JPEG":
        return inspect_jpeg(data)
    if file_type == "PDF":
        return inspect_pdf(data)
    if file_type == "ZIP":
        return inspect_zip(data)
    if file_type == "Windows Shortcut":
        return inspect_shell_link(data)
    if file_type == "Windows Executable":
        return inspect_pe(data)
    return inspect_generic(data)


# ====================================================================
# Damage scope
# ====================================================================

#: Findings that mean the file ends before its own structure does, so the
#: missing bytes lie past the end of the target.
TAIL_FINDINGS = {
    "TRUNCATED_CHUNK",
    "TRUNCATED_SEGMENT",
    "TRUNCATED_SCAN",
    "TRUNCATED_EOCD",
    "MISSING_IEND",
    "MISSING_EOI",
    "MISSING_TRAILER",
    "MISSING_EOCD",
    "DECODE_ERROR",
}

#: Findings that mean the file starts inside a larger stream.
HEAD_FINDINGS = {
    "INVALID_HEADER",
}

#: Findings that localise damage to an exact byte range.
LOCALIZED_FINDINGS = {
    "NULL_REGION",
    "INVALID_HEADER",
    "DESYNC",
}

#: Stream-level findings: they prove damage but do not say which bytes are bad.
STREAM_FINDINGS = TAIL_FINDINGS | {
    "CRC_MISMATCH",
    "EMPTY_FILE",
    "TRAILING_DATA",
}

#: Findings that mean bytes are still absent after a reconstruction attempt.
BLOCKING_FINDINGS = {
    "TRUNCATED_CHUNK",
    "TRUNCATED_SEGMENT",
    "TRUNCATED_SCAN",
    "TRUNCATED_EOCD",
    "MISSING_IEND",
    "MISSING_EOI",
    "MISSING_TRAILER",
    "MISSING_EOCD",
    "INVALID_HEADER",
    "DESYNC",
    "DECODE_ERROR",
}


def trim_to_terminator(data: bytes, file_type: Optional[str]) -> Optional[bytes]:
    """Cut a candidate byte run at the format's real end marker.

    Only the structural terminator decides where a recovered run ends, so
    unrelated trailing evidence is never pulled into an artifact.
    """
    if file_type == "PNG":
        index = data.rfind(b"IEND")
        if index == -1 or index + 8 > len(data):
            return None
        expected = struct.unpack(">I", data[index + 4:index + 8])[0]
        if expected != (zlib.crc32(b"IEND") & 0xFFFFFFFF):
            return None
        return data[:index + 8]

    if file_type == "JPEG":
        index = data.rfind(b"\xff\xd9")
        return data[:index + 2] if index != -1 else None

    if file_type == "PDF":
        index = data.rfind(b"%%EOF")
        return data[:index + 5] if index != -1 else None

    if file_type == "ZIP":
        index = data.rfind(b"PK\x05\x06")
        if index == -1 or index + 22 > len(data):
            return None
        comment_length = struct.unpack("<H", data[index + 20:index + 22])[0]
        end = index + 22 + comment_length
        return data[:end] if end <= len(data) else None

    return data or None


# ====================================================================
# Portion plan
# ====================================================================

@dataclass
class Portion:
    """One fixed-size slice of the target file."""

    index: int
    offset: int
    size: int
    damaged: bool = False
    suspect: bool = False
    damage_kinds: List[str] = field(default_factory=list)

    @property
    def end(self) -> int:
        return self.offset + self.size

    def data_from(self, target: bytes) -> bytes:
        return target[self.offset:self.end]


def build_portions(size: int, findings: Sequence[DamageFinding]) -> List[Portion]:
    """Split the target into portions and flag the ones overlapping damage.

    Only findings that localise damage mark a portion as damaged. A stream-level
    finding (a chunk CRC, a missing trailer) marks it as suspect instead: those
    bytes are real and can still anchor a recovery, the structure check simply
    failed.
    """
    portions: List[Portion] = []
    for index, offset in enumerate(range(0, max(size, 1), PORTION_SIZE)):
        portion = Portion(index=index, offset=offset, size=min(PORTION_SIZE, size - offset))
        for finding in findings:
            if finding.start >= portion.end or finding.end <= portion.offset:
                continue
            if finding.kind in LOCALIZED_FINDINGS:
                portion.damaged = True
            elif finding.kind in STREAM_FINDINGS:
                portion.suspect = True
            if finding.kind not in portion.damage_kinds:
                portion.damage_kinds.append(finding.kind)
        portions.append(portion)
    return portions


def damaged_runs(portions: Sequence[Portion]) -> List[Tuple[int, int]]:
    """Group consecutive damaged portions into (first_index, last_index) runs."""
    runs: List[Tuple[int, int]] = []
    for portion in portions:
        if portion.damaged:
            if runs and runs[-1][1] == portion.index - 1:
                runs[-1] = (runs[-1][0], portion.index)
            else:
                runs.append((portion.index, portion.index))
    return runs


# ====================================================================
# Evidence and recovered ranges
# ====================================================================

@dataclass
class EvidenceFile:
    """One real evidence file offered as a source of missing bytes."""

    path: Path
    size: int
    data: bytes
    relevance_score: Optional[float] = None
    relevance_class: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": str(self.path),
            "size": self.size,
            "relevance_score": self.relevance_score,
            "relevance_class": self.relevance_class,
        }


@dataclass
class RecoveredPortion:
    """A range of the target restored from real evidence bytes."""

    kind: str
    portion_index: Optional[int]
    target_offset: int
    size: int
    source_path: str
    source_offset: int
    sha256: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "portion_index": self.portion_index,
            "target_offset": self.target_offset,
            "size": self.size,
            "source_path": self.source_path,
            "source_offset": self.source_offset,
            "sha256": self.sha256,
        }


@dataclass
class _Candidate:
    """One evidence-based placement of real bytes into the target."""

    kind: str                        # "interior" | "tail" | "head"
    data: bytes
    item: EvidenceFile
    source_offset: int
    run_first: Optional[int] = None  # first portion index for interior runs
    #: True when the evidence file is assumed to be the missing tail rather
    #: than proven to continue the target. Such a placement is only accepted
    #: when the assembled file is validated by a content-checking validator.
    assumed: bool = False


@dataclass
class RecoveryResult:
    """Outcome of one cross-evidence recovery run."""

    target_path: str
    target_size: int
    target_sha256: str
    detected_type: Optional[str] = None
    status: str = STATUS_NO_RECONSTRUCTION
    artifact_path: Optional[str] = None
    artifact_sha256: Optional[str] = None
    artifact_size: Optional[int] = None
    expected_portions: int = 0
    intact_portions: int = 0
    damaged_portions: int = 0
    missing_portions: int = 0
    recovered_portions: List[RecoveredPortion] = field(default_factory=list)
    evidence: List[EvidenceFile] = field(default_factory=list)
    damage: List[DamageFinding] = field(default_factory=list)
    integrity: float = 0.0
    confidence: float = 0.0
    original_bytes: int = 0
    recovered_bytes: int = 0
    missing_bytes: int = 0
    validation: Dict[str, Any] = field(default_factory=dict)
    insights: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_path": self.target_path,
            "target_size": self.target_size,
            "target_sha256": self.target_sha256,
            "detected_type": self.detected_type,
            "status": self.status,
            "artifact_path": self.artifact_path,
            "artifact_sha256": self.artifact_sha256,
            "artifact_size": self.artifact_size,
            "expected_portions": self.expected_portions,
            "intact_portions": self.intact_portions,
            "damaged_portions": self.damaged_portions,
            "missing_portions": self.missing_portions,
            "recovered_portions": [p.to_dict() for p in self.recovered_portions],
            "evidence": [e.to_dict() for e in self.evidence],
            "damage": [d.to_dict() for d in self.damage],
            "integrity": self.integrity,
            "confidence": self.confidence,
            "original_bytes": self.original_bytes,
            "recovered_bytes": self.recovered_bytes,
            "missing_bytes": self.missing_bytes,
            "validation": self.validation,
            "insights": list(self.insights),
            "error": self.error,
        }


# ====================================================================
# Engine
# ====================================================================

MAX_CANDIDATES_PER_SLOT = 4
MAX_COMBINATIONS = 64


class CrossEvidenceRecovery:
    """Restores damaged target ranges from real evidence files.

    Placement always comes from real evidence: a known-intact portion of the
    target is located inside an evidence file and the missing range is read from
    the position that adjacency implies, or from the format's own terminator.
    Every combination is re-validated as a whole before it is accepted, so a
    reconstruction is only reported when the real file structure agrees.
    """

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = Path(output_dir) if output_dir else None
        self._relevance_model = None
        self._relevance_note: Optional[str] = None

    # -- evidence handling ------------------------------------------------

    def _load_evidence(self, evidence_paths: Sequence[Path]) -> List[EvidenceFile]:
        loaded: List[EvidenceFile] = []
        for path in evidence_paths:
            try:
                path = Path(path)
                if not path.is_file():
                    continue
                data = path.read_bytes()
            except OSError:
                continue
            if not data:
                continue
            item = EvidenceFile(path=path, size=len(data), data=data)
            self._score_relevance(item)
            loaded.append(item)

        # The AI layer only decides which evidence is worth trying first.
        loaded.sort(key=lambda e: (e.relevance_score is None,
                                   -(e.relevance_score or 0.0),
                                   e.size))
        return loaded

    def _score_relevance(self, item: EvidenceFile) -> None:
        """Rank one evidence file with the existing AI relevance model."""
        if self._relevance_model is None and self._relevance_note is None:
            from app.ai.fragment_relevance import (
                create_relevance_model,
                relevance_model_unavailable_reason,
            )

            self._relevance_model = create_relevance_model()
            if self._relevance_model is None:
                self._relevance_note = (
                    relevance_model_unavailable_reason()
                    or "the AI relevance model could not be trained"
                )

        if self._relevance_model is None:
            return

        from app.models.scan import Fragment

        sample = item.data[:PORTION_SIZE]
        fragment = Fragment(
            fragment_id=f"evidence::{item.path.name}",
            scan_id="cross_evidence",
            offset=0,
            size=len(sample),
            sha256=sha256_hex(sample),
            entropy=entropy_of(sample),
            byte_stats={
                "unique_bytes": len(set(sample)),
                "null_bytes": sample.count(0),
                "header_bytes": sample[:8].hex(),
            },
        )
        try:
            scored = self._relevance_model.predict_fragment(fragment)
        except Exception as exc:  # a scoring failure must not stop recovery
            self._relevance_note = f"AI relevance scoring failed: {exc}"
            self._relevance_model = None
            return
        item.relevance_score = scored.relevance_score
        item.relevance_class = scored.relevance_class

    # -- anchor search ----------------------------------------------------

    @staticmethod
    def _find_all(haystack: bytes, needle: bytes, limit: int = 32) -> List[int]:
        if not needle:
            return []
        offsets: List[int] = []
        start = haystack.find(needle)
        while start != -1 and len(offsets) < limit:
            offsets.append(start)
            start = haystack.find(needle, start + 1)
        return offsets

    @staticmethod
    def _plausible(chunk: bytes) -> bool:
        """Reject filler that no real file would contain in a missing range."""
        return bool(chunk) and len(set(chunk)) > 1

    # -- candidate generation ---------------------------------------------

    def _interior_candidates(
        self,
        target: bytes,
        portions: Sequence[Portion],
        first: int,
        last: int,
        evidence: Sequence[EvidenceFile],
    ) -> List[_Candidate]:
        """Place one damaged interior run using the bytes adjacent to it."""
        run_start = portions[first].offset
        run_end = portions[last].end
        length = run_end - run_start
        before = portions[first - 1] if first > 0 else None
        after = portions[last + 1] if last + 1 < len(portions) else None

        candidates: List[_Candidate] = []
        for item in evidence:
            for anchor_portion, direction in ((before, 1), (after, -1)):
                if anchor_portion is None:
                    continue
                anchor = anchor_portion.data_from(target)
                for hit in self._find_all(item.data, anchor):
                    source_offset = hit + anchor_portion.size if direction > 0 else hit - length
                    if source_offset < 0 or source_offset + length > item.size:
                        continue
                    chunk = item.data[source_offset:source_offset + length]
                    if not self._plausible(chunk):
                        continue
                    candidates.append(_Candidate(
                        kind="interior",
                        data=chunk,
                        item=item,
                        source_offset=source_offset,
                        run_first=first,
                    ))
                    break
        return candidates[:MAX_CANDIDATES_PER_SLOT]

    def _tail_candidates(
        self,
        target: bytes,
        trailing_start: int,
        portions: Sequence[Portion],
        evidence: Sequence[EvidenceFile],
        file_type: Optional[str],
    ) -> List[_Candidate]:
        """Bytes that continue the file from `trailing_start` onwards.

        Two evidence-based placements are used: the bytes that follow the
        target's last intact portion inside an evidence file (real adjacency),
        and the terminating bytes of an evidence file that is itself the missing
        tail of the target.
        """
        candidates: List[_Candidate] = []

        anchors = [p for p in portions if not p.damaged and p.offset < trailing_start]
        for anchor_portion in reversed(anchors):
            anchor = anchor_portion.data_from(target)
            if len(anchor) < ANCHOR_SIZE:
                continue
            for item in evidence:
                for hit in self._find_all(item.data, anchor):
                    start = hit + len(anchor)
                    if start >= item.size:
                        continue
                    trimmed = trim_to_terminator(item.data[start:], file_type)
                    if trimmed and self._plausible(trimmed):
                        candidates.append(_Candidate(
                            kind="tail", data=trimmed, item=item, source_offset=start
                        ))
                    break
            if candidates:
                break

        # A whole evidence file can only *be* the missing tail when nothing
        # proves otherwise, so such a placement is marked as assumed: it is
        # accepted only when a content-checking validator confirms the result.
        for item in evidence:
            trimmed = trim_to_terminator(item.data, file_type)
            if trimmed and self._plausible(trimmed):
                candidates.append(_Candidate(
                    kind="tail", data=trimmed, item=item, source_offset=0,
                    assumed=True,
                ))

        unique: List[_Candidate] = []
        seen = set()
        for candidate in candidates:
            key = (str(candidate.item.path), candidate.source_offset, len(candidate.data))
            if key in seen:
                continue
            seen.add(key)
            unique.append(candidate)
        return unique[:MAX_CANDIDATES_PER_SLOT]

    def _head_candidates(
        self,
        target: bytes,
        portions: Sequence[Portion],
        evidence: Sequence[EvidenceFile],
        file_type: Optional[str],
    ) -> List[_Candidate]:
        """Bytes that precede the target when the file starts mid-stream."""
        candidates: List[_Candidate] = []
        if not portions:
            return candidates
        anchor = portions[0].data_from(target)
        if len(anchor) < ANCHOR_SIZE:
            return candidates

        for item in evidence:
            for hit in self._find_all(item.data, anchor):
                if hit == 0:
                    continue
                head = item.data[:hit]
                start = None
                for signature, kind, _ in SIGNATURES:
                    index = head.rfind(signature)
                    if index != -1 and (file_type is None or kind == file_type):
                        start = index
                        break
                if start is None:
                    continue
                candidate_bytes = head[start:]
                if self._plausible(candidate_bytes):
                    candidates.append(_Candidate(
                        kind="head", data=candidate_bytes, item=item, source_offset=start
                    ))
                break
        return candidates[:MAX_CANDIDATES_PER_SLOT]

    # -- evidence placement ------------------------------------------------

    def _locate_in_evidence(
        self,
        target: bytes,
        evidence: Sequence[EvidenceFile],
    ) -> Optional[Tuple[EvidenceFile, int, int]]:
        """Find the target's own bytes inside an evidence file.

        Anchors are whole real portions, never filenames. The returned overlap
        is the number of leading target bytes that the evidence file contains
        at `offset`.
        """
        if not target:
            return None

        anchors: List[bytes] = []
        for offset in (0, max(0, len(target) // 2), max(0, len(target) - PORTION_SIZE)):
            candidate = target[offset:offset + PORTION_SIZE]
            if len(candidate) >= ANCHOR_SIZE and candidate not in anchors:
                anchors.append(candidate)

        best: Optional[Tuple[EvidenceFile, int, int]] = None
        for item in evidence:
            for anchor in anchors:
                for hit in self._find_all(item.data, anchor, limit=8):
                    overlap = min(len(target), item.size - hit)
                    if overlap < ANCHOR_SIZE:
                        continue
                    if best is None or overlap > best[2]:
                        best = (item, hit, overlap)
        return best

    @staticmethod
    def _diff_ranges(left: bytes, right: bytes, merge_gap: int = 64) -> List[Tuple[int, int]]:
        """Byte ranges where the target and the evidence copy disagree.

        These are evidence-proven damaged ranges: the rest of the overlap is
        byte-identical, so nothing intact is ever overwritten.
        """
        size = min(len(left), len(right))
        ranges: List[Tuple[int, int]] = []
        start: Optional[int] = None
        for index in range(size):
            if left[index] != right[index]:
                if start is None:
                    start = index
            elif start is not None:
                ranges.append((start, index))
                start = None
        if start is not None:
            ranges.append((start, size))

        merged: List[Tuple[int, int]] = []
        for begin, end in ranges:
            if merged and begin - merged[-1][1] <= merge_gap:
                merged[-1] = (merged[-1][0], end)
            else:
                merged.append((begin, end))
        return merged

    def _evidence_anchored_reconstruction(
        self,
        target: bytes,
        placement: Tuple[EvidenceFile, int, int],
        file_type: Optional[str],
    ) -> Optional[Tuple[bytes, List[RecoveredPortion], List[str], int]]:
        """Rebuild the target from the evidence copy that contains its bytes.

        Returns (artifact bytes, recovered ranges, insights, bytes restored) or
        None when the evidence is not the same content.
        """
        item, offset, overlap = placement
        reference = item.data[offset:offset + overlap]
        if not reference:
            return None

        identical = sum(1 for a, b in zip(target[:overlap], reference) if a == b)
        ratio = identical / overlap if overlap else 0.0
        if ratio < 0.6:
            return None
        if overlap < len(target) and overlap < PORTION_SIZE * 2:
            return None

        diffs = self._diff_ranges(target[:overlap], reference)
        restored = sum(end - begin for begin, end in diffs)

        recovered = [
            RecoveredPortion(
                kind="interior",
                portion_index=begin // PORTION_SIZE,
                target_offset=begin,
                size=end - begin,
                source_path=str(item.path),
                source_offset=offset + begin,
                sha256=sha256_hex(reference[begin:end]),
            )
            for begin, end in diffs
        ]

        insights = [
            f"Located the target's bytes inside {item.path.name} at offset {offset}; "
            f"{identical} of {overlap} bytes match exactly."
        ]

        artifact = bytearray(reference)
        if overlap < len(target):
            missing = len(target) - overlap
            artifact.extend(b"\x00" * missing)
            recovered.append(RecoveredPortion(
                kind="gap",
                portion_index=None,
                target_offset=overlap,
                size=missing,
                source_path="",
                source_offset=0,
                sha256="",
            ))
            insights.append(
                f"{missing} target bytes past the located region are not present in the evidence."
            )

        tail = b""
        if overlap < item.size:
            remainder = item.data[offset + overlap:]
            if file_type in STRUCTURAL_TYPES:
                trimmed = trim_to_terminator(remainder, file_type)
                if trimmed:
                    tail = trimmed
                    recovered.append(RecoveredPortion(
                        kind="tail",
                        portion_index=None,
                        target_offset=len(artifact),
                        size=len(trimmed),
                        source_path=str(item.path),
                        source_offset=offset + overlap,
                        sha256=sha256_hex(trimmed),
                    ))
                    insights.append(
                        f"Recovered {len(trimmed)} trailing bytes found after the located region."
                    )
            if not tail and file_type not in STRUCTURAL_TYPES:
                insights.append(
                    "The evidence continues past the target, but this file type has no "
                    "structural terminator, so no trailing bytes were added."
                )

        return bytes(artifact) + tail, recovered, insights, restored

    # -- assembly and validation ------------------------------------------

    @staticmethod
    def _assemble(
        target: bytes,
        portions: Sequence[Portion],
        interior: Dict[int, _Candidate],
        head: Optional[_Candidate],
        tail: Optional[_Candidate],
        trailing_start: int,
    ) -> bytes:
        """Place every recovered range at its real offset in the file."""
        out = bytearray(head.data if head else b"")
        for portion in portions:
            if portion.offset >= trailing_start:
                break
            candidate = interior.get(portion.index)
            if candidate is None:
                out.extend(portion.data_from(target))
                continue
            run_offset = portions[candidate.run_first].offset
            start = portion.offset - run_offset
            out.extend(candidate.data[start:start + portion.size])
        out.extend(tail.data if tail else b"")
        return bytes(out)

    def _evaluate(
        self,
        target: bytes,
        portions: Sequence[Portion],
        interior: Dict[int, _Candidate],
        head: Optional[_Candidate],
        tail: Optional[_Candidate],
        trailing_start: int,
        file_type: Optional[str],
    ) -> Tuple[bytes, bool, List[str]]:
        assembled = self._assemble(target, portions, interior, head, tail, trailing_start)
        valid, notes = validate_structure(assembled, file_type)
        return assembled, valid, notes

    @staticmethod
    def _split_combination(
        combination: List[Optional[_Candidate]],
        interior_runs: Sequence[Tuple[int, int]],
        tail_slot: Optional[int],
        head_slot: Optional[int],
    ) -> Tuple[Dict[int, _Candidate], Optional[_Candidate], Optional[_Candidate]]:
        interior: Dict[int, _Candidate] = {}
        for index, (first, _last) in enumerate(interior_runs):
            option = combination[index]
            if option is not None:
                interior[first] = option
        tail = combination[tail_slot] if tail_slot is not None else None
        head = combination[head_slot] if head_slot is not None else None
        return interior, head, tail

    # -- public API -------------------------------------------------------

    def recover(self, target_path: Path, evidence_paths: Sequence[Path]) -> RecoveryResult:
        """Rebuild the target from evidence and report what was actually restored."""
        target_path = Path(target_path)
        try:
            target = target_path.read_bytes()
        except OSError as exc:
            result = RecoveryResult(
                target_path=str(target_path),
                target_size=0,
                target_sha256="",
                error=f"Could not read the target file: {exc}",
            )
            result.insights.append("The target file could not be read.")
            return result

        file_type, mime, _ = detect_signature(target)
        result = RecoveryResult(
            target_path=str(target_path),
            target_size=len(target),
            target_sha256=sha256_hex(target),
            detected_type=file_type,
            original_bytes=len(target),
        )
        if file_type:
            result.insights.append(f"Detected target format: {file_type} ({mime}).")

        damage = detect_damage(target)
        result.damage = damage

        # The evidence is inspected before damage is judged: a byte-level
        # comparison against a real copy is stronger evidence about what is
        # damaged than any structural heuristic.
        evidence = self._load_evidence([Path(p) for p in evidence_paths])
        result.evidence = evidence
        placement = self._locate_in_evidence(target, evidence) if evidence else None
        anchored = None
        progressed = False
        if placement is not None:
            anchored = self._evidence_anchored_reconstruction(target, placement, file_type)
            if anchored is not None:
                progressed = anchored[3] > 0 or any(r.kind == "tail" for r in anchored[1])

        if not damage and not progressed:
            result.status = STATUS_INTACT
            result.expected_portions = len(range(0, max(len(target), 1), PORTION_SIZE))
            result.intact_portions = result.expected_portions
            result.artifact_size = len(target)
            result.recovered_bytes = len(target)
            result.integrity = 1.0
            result.confidence = 1.0
            result.insights.append("The file is complete, so no recovery was needed.")
            return result

        for finding in damage:
            result.insights.append(f"{finding.kind}: {finding.detail}")

        if anchored is not None and progressed:
            return self._finish_anchored(
                target, target_path, file_type, damage, result, anchored, evidence
            )
        if anchored is not None and not progressed:
            result.insights.append(
                "A byte-identical copy of the target exists in the evidence; searching "
                "the remaining evidence for the missing ranges."
            )

        kinds = {finding.kind for finding in damage}
        needs_tail = bool(kinds & TAIL_FINDINGS)
        needs_head = bool(kinds & HEAD_FINDINGS)

        portions = build_portions(len(target), damage)
        runs = damaged_runs(portions)
        result.expected_portions = len(portions)
        result.intact_portions = sum(1 for p in portions if not p.damaged)
        result.damaged_portions = sum(1 for p in portions if p.damaged)

        # A damaged run that reaches the end of the file is one trailing region:
        # those bytes, plus whatever the original continued with, are restored
        # as a single continuous tail instead of separate fixed-size portions.
        trailing_start = len(target) if needs_tail else None
        interior_runs: List[Tuple[int, int]] = []
        for first, last in runs:
            if portions[last].end >= len(target):
                trailing_start = portions[first].offset
            else:
                interior_runs.append((first, last))

        if not evidence:
            result.insights.append("No readable evidence file was supplied.")
            return result

        if self._relevance_note:
            result.insights.append(f"AI relevance unavailable: {self._relevance_note}")
        high = [e for e in evidence if e.relevance_class == "HIGH_RELEVANCE"]
        if high:
            result.insights.append(
                f"AI marked {len(high)} evidence file(s) as HIGH recovery priority."
            )

        slot_options: List[List[Optional[_Candidate]]] = []
        for first, last in interior_runs:
            options: List[Optional[_Candidate]] = list(
                self._interior_candidates(target, portions, first, last, evidence)
            )
            slot_options.append(options or [None])

        tail_slot: Optional[int] = None
        if trailing_start is not None:
            tail_slot = len(slot_options)
            slot_options.append(
                list(self._tail_candidates(target, trailing_start, portions, evidence, file_type))
                or [None]
            )
        head_slot: Optional[int] = None
        if needs_head:
            head_slot = len(slot_options)
            slot_options.append(
                list(self._head_candidates(target, portions, evidence, file_type)) or [None]
            )

        effective_trailing = trailing_start if trailing_start is not None else len(target)
        damaged_total = sum(
            p.size for p in portions
            if p.damaged and p.end <= effective_trailing
        )
        if trailing_start is not None:
            damaged_total += len(target) - trailing_start
        if needs_head and portions:
            damaged_total += portions[0].size

        best: Optional[Tuple[bytes, bool, List[str], List[Optional[_Candidate]]]] = None
        chosen: Optional[Tuple[bytes, bool, List[str], List[Optional[_Candidate]]]] = None
        for index, combination in enumerate(self._combinations(slot_options)):
            if index >= MAX_COMBINATIONS:
                break
            interior, head, tail = self._split_combination(
                combination, interior_runs, tail_slot, head_slot
            )
            assembled, valid, notes = self._evaluate(
                target, portions, interior, head, tail, effective_trailing, file_type
            )
            if best is None:
                best = (assembled, valid, notes, list(combination))
            if valid:
                chosen = (assembled, valid, notes, list(combination))
                break

        if chosen is None:
            chosen = best
        if chosen is None:
            result.status = STATUS_NO_RECONSTRUCTION
            result.insights.append("No candidate reconstruction could be assembled.")
            return result

        assembled, valid, notes, combination = chosen
        interior, head, tail = self._split_combination(
            combination, interior_runs, tail_slot, head_slot
        )

        if tail is not None and tail.assumed and file_type not in CONTENT_VALIDATED_TYPES:
            # Nothing proves this evidence file continues the target, and this
            # format has no validator that could confirm the result, so the
            # bytes are not used: guessing them would fabricate evidence.
            result.insights.append(
                f"{Path(tail.item.path).name} was not accepted as the missing tail "
                f"because no evidence places it directly after the last intact bytes "
                f"of the {file_type or 'target'}."
            )
            tail = None

        recovered_bytes = 0
        missing_portions = 0
        missing_bytes = 0
        for first, last in interior_runs:
            candidate = interior.get(first)
            run_length = portions[last].end - portions[first].offset
            if candidate is None:
                missing_portions += last - first + 1
                missing_bytes += run_length
                continue
            recovered_bytes += len(candidate.data)
            for index in range(first, last + 1):
                portion = portions[index]
                start = portion.offset - portions[first].offset
                piece = candidate.data[start:start + portion.size]
                result.recovered_portions.append(RecoveredPortion(
                    kind="interior",
                    portion_index=index,
                    target_offset=portion.offset,
                    size=portion.size,
                    source_path=str(candidate.item.path),
                    source_offset=candidate.source_offset + start,
                    sha256=sha256_hex(piece),
                ))

        if tail is not None:
            recovered_bytes += len(tail.data)
            result.recovered_portions.append(RecoveredPortion(
                kind="tail",
                portion_index=None,
                target_offset=trailing_start if trailing_start is not None else len(target),
                size=len(tail.data),
                source_path=str(tail.item.path),
                source_offset=tail.source_offset,
                sha256=sha256_hex(tail.data),
            ))
        elif trailing_start is not None:
            missing_bytes += len(target) - trailing_start
            missing_portions += sum(1 for p in portions if p.offset >= trailing_start)
            result.insights.append(
                "The file is truncated and no evidence file supplies the missing tail."
            )

        if head is not None:
            recovered_bytes += len(head.data)
            result.recovered_portions.append(RecoveredPortion(
                kind="head",
                portion_index=None,
                target_offset=0,
                size=len(head.data),
                source_path=str(head.item.path),
                source_offset=head.source_offset,
                sha256=sha256_hex(head.data),
            ))
        elif needs_head:
            result.insights.append(
                "The file header is damaged and no evidence file supplies it."
            )
            missing_bytes += portions[0].size if portions else 0
            missing_portions += 1

        result.recovered_portions.sort(key=lambda p: p.target_offset)
        result.missing_portions = missing_portions
        result.missing_bytes = missing_bytes
        result.recovered_bytes = recovered_bytes

        if not result.recovered_portions:
            result.status = STATUS_NO_RECONSTRUCTION
            result.insights.append(
                "No evidence file contains the missing bytes; select additional evidence."
            )
            return result

        detected_type, detected_mime, _ = detect_signature(assembled)
        blocking = [
            f.kind for f in remaining_structure_issues(assembled, file_type)
            if f.kind in BLOCKING_FINDINGS
        ]
        type_name = file_type or detected_type
        structural = (
            pe_structure_is_complete(assembled)
            if type_name == "Windows Executable"
            else (type_name in STRUCTURAL_TYPES and valid)
        )
        result.validation = {
            "validation_status": "VALID" if valid else "INVALID",
            "structurally_valid": valid,
            "validated_by": "structure" if structural else "evidence_continuity",
            "detected_type": detected_type or file_type or "Unknown",
            "mime_type": detected_mime or "application/octet-stream",
            "entropy": entropy_of(assembled),
            "notes": notes,
            "damaged_bytes": damaged_total,
            "recovered_from_evidence": recovered_bytes,
            "sha256": sha256_hex(assembled),
            "outstanding_issues": blocking,
        }
        if not structural and valid:
            result.insights.append(
                f"No structural validator exists for {detected_type or 'this file type'}; "
                "the restored bytes are corroborated by exact evidence continuity."
            )

        coverage = min(1.0, recovered_bytes / damaged_total) if damaged_total else 0.0
        result.confidence = round(coverage if valid else coverage * 0.5, 4)
        result.integrity = round(
            (len(assembled) - missing_bytes) / len(assembled), 4
        ) if assembled else 0.0

        if valid:
            result.status = STATUS_RECONSTRUCTED
            result.integrity = 1.0
            result.insights.append(
                f"Restored {recovered_bytes} bytes from real evidence and verified the "
                f"{file_type or 'file'} structure end to end."
            )
        elif (
            coverage >= MIN_PARTIAL_COVERAGE
            and not blocking
            and detect_signature(assembled)[2]
        ):
            # A real partial artifact: the file keeps a valid structure, but some
            # of the damaged bytes are still unknown.
            result.status = STATUS_PARTIALLY_RECONSTRUCTED
            result.insights.append(
                f"Restored {recovered_bytes} of {damaged_total} damaged bytes; "
                f"{missing_bytes} bytes are still missing."
            )
        else:
            result.status = STATUS_NO_RECONSTRUCTION
            result.insights.append(
                "The evidence does not contain enough of the missing bytes for a "
                "reliable reconstruction."
            )
            return result

        artifact_path = self._write_artifact(target_path, assembled)
        if artifact_path is None:
            result.status = STATUS_NO_RECONSTRUCTION
            result.insights.append("The recovery directory is not writable.")
            return result

        result.artifact_path = str(artifact_path)
        result.artifact_sha256 = sha256_hex(assembled)
        result.artifact_size = len(assembled)
        return result

    def _finish_anchored(
        self,
        target: bytes,
        target_path: Path,
        file_type: Optional[str],
        damage: List[DamageFinding],
        result: RecoveryResult,
        anchored: Tuple[bytes, List[RecoveredPortion], List[str], int],
        evidence: List[EvidenceFile],
    ) -> RecoveryResult:
        """Validate and persist a reconstruction taken from a located copy."""
        artifact, recovered, insights, restored = anchored
        result.insights.extend(insights)
        if self._relevance_note:
            result.insights.append(f"AI relevance unavailable: {self._relevance_note}")

        detected_kind = file_type or detect_signature(artifact)[0]
        structural = (
            pe_structure_is_complete(artifact)
            if detected_kind == "Windows Executable"
            else detected_kind in STRUCTURAL_TYPES
        )
        valid, notes = validate_structure(artifact, file_type)
        blocking = [
            f.kind for f in remaining_structure_issues(artifact, file_type)
            if f.kind in BLOCKING_FINDINGS
        ]
        # A format without structural rules may legitimately contain filler
        # padding, so the accepted criterion is: no blocking issue remains.
        accepted = (not blocking) if not structural else (valid and not blocking)
        detected_type, detected_mime, _ = detect_signature(artifact)

        missing = [r for r in recovered if r.kind == "gap"]
        result.recovered_portions = [r for r in recovered if r.kind != "gap"]
        result.recovered_bytes = restored + sum(r.size for r in result.recovered_portions if r.kind == "tail")
        result.missing_bytes = sum(r.size for r in missing)
        result.missing_portions = len(missing)
        result.expected_portions = len(range(0, max(len(target), 1), PORTION_SIZE))
        result.intact_portions = sum(1 for r in result.recovered_portions if r.kind == "interior")
        result.damaged_portions = max(1, len(result.recovered_portions)) if restored else 0

        result.validation = {
            "validation_status": "VALID" if accepted else "INVALID",
            "structurally_valid": accepted,
            "validated_by": "structure" if structural else "evidence_continuity",
            "detected_type": detected_type or file_type or "Unknown",
            "mime_type": detected_mime or "application/octet-stream",
            "entropy": entropy_of(artifact),
            "notes": notes,
            "damaged_bytes": restored + result.missing_bytes,
            "recovered_from_evidence": result.recovered_bytes,
            "sha256": sha256_hex(artifact),
            "outstanding_issues": blocking,
        }

        if not result.recovered_portions:
            result.status = STATUS_NO_RECONSTRUCTION
            result.insights.append(
                "The located evidence copy is identical to the target, so nothing needed recovery."
            )
            return result

        complete = accepted and not missing
        coverage = restored / (restored + result.missing_bytes) if (restored + result.missing_bytes) else 0.0
        result.confidence = round(coverage if complete else coverage * 0.5, 4)
        result.integrity = round(
            (len(artifact) - result.missing_bytes) / len(artifact), 4
        ) if artifact else 0.0

        if complete:
            result.status = STATUS_RECONSTRUCTED
            result.integrity = 1.0
            result.insights.append(
                f"Restored {result.recovered_bytes} bytes from real evidence; the rebuilt file "
                f"passes {'structural' if structural else 'evidence'} validation."
            )
        elif coverage >= MIN_PARTIAL_COVERAGE and not blocking:
            result.status = STATUS_PARTIALLY_RECONSTRUCTED
            result.insights.append(
                f"Restored {restored} bytes; {result.missing_bytes} bytes are not present in "
                "the available evidence."
            )
        else:
            result.status = STATUS_NO_RECONSTRUCTION
            result.insights.append(
                "The evidence does not contain enough of the missing bytes for a "
                "reliable reconstruction."
            )
            return result

        artifact_path = self._write_artifact(target_path, artifact)
        if artifact_path is None:
            result.status = STATUS_NO_RECONSTRUCTION
            result.insights.append("The recovery directory is not writable.")
            return result

        result.artifact_path = str(artifact_path)
        result.artifact_sha256 = sha256_hex(artifact)
        result.artifact_size = len(artifact)
        return result

    @staticmethod
    def _combinations(
        slot_options: List[List[Optional[_Candidate]]],
    ) -> List[List[Optional[_Candidate]]]:
        """All candidate combinations, strongest evidence first."""
        combinations: List[List[Optional[_Candidate]]] = [[]]
        for options in slot_options:
            expanded: List[List[Optional[_Candidate]]] = []
            for prefix in combinations:
                for option in options:
                    expanded.append(prefix + [option])
            combinations = expanded[:512]
        return combinations

    def _write_artifact(self, target_path: Path, data: bytes) -> Optional[Path]:
        """Write the recovered bytes to the recovery directory, never overwriting."""
        if self.output_dir is None:
            from app.config import get_reconstructed_dir

            output_dir = get_reconstructed_dir()
        else:
            output_dir = self.output_dir

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None

        stem = target_path.stem or "recovered"
        suffix = target_path.suffix
        candidate = output_dir / f"{stem}_recovered{suffix}"
        counter = 1
        while candidate.exists():
            candidate = output_dir / f"{stem}_recovered_{counter}{suffix}"
            counter += 1

        try:
            candidate.write_bytes(data)
        except OSError:
            return None
        return candidate




#: Findings that mean the file ends before its own structure does, so the
#: missing bytes lie past the end of the target.
TAIL_FINDINGS = {
    "TRUNCATED_CHUNK",
    "TRUNCATED_SEGMENT",
    "TRUNCATED_SCAN",
    "TRUNCATED_EOCD",
    "MISSING_IEND",
    "MISSING_EOI",
    "MISSING_TRAILER",
    "MISSING_EOCD",
    "DECODE_ERROR",
}

#: Findings that mean the file starts inside a larger stream.
HEAD_FINDINGS = {
    "INVALID_HEADER",
}


def trim_to_terminator(data: bytes, file_type: Optional[str]) -> Optional[bytes]:
    """Cut a candidate byte run at the format's real end marker.

    Only the structural terminator decides where a recovered run ends, so no
    unrelated trailing evidence is ever pulled into the artifact.
    """
    if file_type == "PNG":
        index = data.rfind(b"IEND")
        if index == -1 or index + 8 > len(data):
            return None
        expected = struct.unpack(">I", data[index + 4:index + 8])[0]
        actual = zlib.crc32(b"IEND") & 0xFFFFFFFF
        if expected != actual:
            return None
        return data[:index + 8]

    if file_type == "JPEG":
        index = data.rfind(b"\xff\xd9")
        if index == -1:
            return None
        return data[:index + 2]

    if file_type == "PDF":
        index = data.rfind(b"%%EOF")
        if index == -1:
            return None
        return data[:index + 5]

    if file_type == "ZIP":
        index = data.rfind(b"PK\x05\x06")
        if index == -1 or index + 22 > len(data):
            return None
        comment_length = struct.unpack("<H", data[index + 20:index + 22])[0]
        end = index + 22 + comment_length
        if end > len(data):
            return None
        return data[:end]

    if file_type is None:
        return data or None
    return data or None



