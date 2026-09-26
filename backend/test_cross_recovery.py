"""
Cross-Evidence Recovery Tests (real bytes only)

Every case builds real files, damages them for real, and rebuilds them from
other real evidence files. Where a reference original exists the recovered
artifact is compared byte for byte and by SHA-256.
"""

import hashlib
import os
import struct
import sys
import tempfile
import zlib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.reconstruction.cross_recovery import (
    PORTION_SIZE,
    STATUS_INTACT,
    STATUS_NO_RECONSTRUCTION,
    STATUS_PARTIALLY_RECONSTRUCTED,
    STATUS_RECONSTRUCTED,
    CrossEvidenceRecovery,
    detect_damage,
    validate_structure,
)


# ------------------------------------------------------------------
# Real file builders
# ------------------------------------------------------------------

def noise(length: int, seed: int) -> bytes:
    """Deterministic, incompressible bytes so test files are genuinely large."""
    import random

    return random.Random(seed).randbytes(length)


def build_opaque_binary(size: int, seed: int, padding_at=None, mz_header: bool = True) -> bytes:
    """An opaque binary blob, optionally with a PE header and zero padding.

    Without structural rules for the format, this exercises the generic-binary
    recovery path: filler is treated as damage and intact padding is not.
    """
    import random

    rng = random.Random(seed)
    blob = bytearray(rng.randbytes(size))
    if mz_header:
        blob[0:2] = b"MZ"
    for start in (padding_at or ()):
        blob[start:start + 8192] = b"\x00" * 8192
    return bytes(blob)


def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + chunk_type
        + payload
        + struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF)
    )


def build_png(payload: bytes, width: int = 8, height: int = 8) -> bytes:
    """A structurally valid PNG with real IDAT pixel data."""
    raw = bytearray()
    for row in range(height):
        raw.append(0)  # filter type 0
        for col in range(width):
            raw.extend(((row * width + col) % 256, (row * 3) % 256, (col * 5) % 256))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(raw) + payload)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


def build_pdf(body: bytes) -> bytes:
    return (
        b"%PDF-1.7\n"
        + b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
        + b"2 0 obj\n<< /Length " + str(len(body)).encode() + b" >>\nstream\n"
        + body
        + b"\nendstream\nendobj\n"
        + b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"
    )


def build_zip(members: dict) -> bytes:
    import zipfile
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def build_jpeg(appended: bytes = b"") -> bytes:
    """A JPEG with a real SOI/APP0/SOS frame and EOI terminator."""
    soi = b"\xff\xd8"
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    comment_payload = b"ReConstructAI forensic sample"
    com = b"\xff\xfe" + struct.pack(">H", len(comment_payload) + 2) + comment_payload
    sos = b"\xff\xda" + struct.pack(">H", 8) + b"\x01\x01\x00\x00\x3f\x00"
    scan = bytes(range(256)) * 2
    return soi + app0 + com + sos + scan + appended + b"\xff\xd9"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        os.environ["RECONSTRUCTAI_APP_DATA"] = str(root / "appdata")
        evidence = root / "evidence"
        recovered = root / "recovered"
        evidence.mkdir(parents=True)
        recovered.mkdir(parents=True)
        yield {"root": root, "evidence": evidence, "recovered": recovered}


def engine_for(workspace) -> CrossEvidenceRecovery:
    return CrossEvidenceRecovery(output_dir=workspace["recovered"])


# ------------------------------------------------------------------
# Case A: healthy real file
# ------------------------------------------------------------------

def test_healthy_png_needs_no_recovery(workspace):
    original = build_png(b"healthy evidence payload")
    target = workspace["evidence"] / "healthy.png"
    target.write_bytes(original)

    result = engine_for(workspace).recover(target, [])

    assert result.status == STATUS_INTACT
    assert result.artifact_path is None, "an intact file must not produce an artifact"
    assert detect_damage(original) == []


# ------------------------------------------------------------------
# Case B: truncated file, missing bytes available in evidence (exact)
# ------------------------------------------------------------------

def test_truncated_png_rebuilt_from_evidence_is_byte_identical(workspace):
    original = build_png(noise(400 * 64, 7))
    full_copy = workspace["evidence"] / "photo_backup.png"
    full_copy.write_bytes(original)

    keep = len(original) - (PORTION_SIZE * 2) - 200
    target = workspace["evidence"] / "photo.png"
    target.write_bytes(original[:keep])

    assert detect_damage(target.read_bytes()), "the truncated target must show damage"

    result = engine_for(workspace).recover(target, [full_copy])

    assert result.status == STATUS_RECONSTRUCTED, result.insights
    assert result.artifact_path and Path(result.artifact_path).is_file()
    assert Path(result.artifact_path).name == "photo_recovered.png"

    recovered_bytes = Path(result.artifact_path).read_bytes()
    assert recovered_bytes == original
    assert result.artifact_sha256 == sha256(original)
    assert result.validation["structurally_valid"] is True
    assert result.missing_portions == 0
    assert result.recovered_portions, "the restored ranges must be recorded"
    for portion in result.recovered_portions:
        assert portion.source_path == str(full_copy)
        assert portion.target_offset == portion.source_offset, "same content, same placement"


def test_recovered_png_opens_as_a_real_image(workspace):
    original = build_png(noise(300 * 64, 11))
    full_copy = workspace["evidence"] / "source.png"
    full_copy.write_bytes(original)
    target = workspace["evidence"] / "broken.png"
    target.write_bytes(original[: len(original) - PORTION_SIZE - 64])

    result = engine_for(workspace).recover(target, [full_copy])
    assert result.status == STATUS_RECONSTRUCTED

    # A real decoder must accept the recovered file, not just its extension.
    from PySide6.QtGui import QImage

    image = QImage(str(result.artifact_path))
    assert not image.isNull(), "the recovered file must decode as an image"
    assert image.width() == 8 and image.height() == 8


# ------------------------------------------------------------------
# Case C: interior damaged region replaced with filler
# ------------------------------------------------------------------

def test_interior_zero_region_restored_from_evidence(workspace):
    original = build_png(noise(500 * 64, 7))
    full_copy = workspace["evidence"] / "container.bin"
    # The evidence stores the same bytes, but embedded inside a larger blob.
    blob = b"CONTAINER-PREFIX" + original + b"CONTAINER-SUFFIX"
    full_copy.write_bytes(blob)

    damaged = bytearray(original)
    start = PORTION_SIZE
    damaged[start:start + PORTION_SIZE] = b"\x00" * PORTION_SIZE
    target = workspace["evidence"] / "damaged.png"
    target.write_bytes(bytes(damaged))

    result = engine_for(workspace).recover(target, [full_copy])

    assert result.status == STATUS_RECONSTRUCTED, result.insights
    recovered_bytes = Path(result.artifact_path).read_bytes()
    assert recovered_bytes == original
    assert result.artifact_sha256 == sha256(original)


# ------------------------------------------------------------------
# Case D/E: multi-fragment and cross-evidence reconstruction
# ------------------------------------------------------------------

def test_multi_fragment_reconstruction_uses_real_offsets(workspace):
    """Interior damage and a missing tail are restored from two evidence files."""
    original = build_png(noise(1200 * 64, 7))
    size = len(original)
    first_split = (size // 3 // PORTION_SIZE) * PORTION_SIZE
    second_split = (2 * size // 3 // PORTION_SIZE) * PORTION_SIZE
    assert 0 < first_split < second_split < size

    part_a = workspace["evidence"] / "part_a.bin"
    part_b = workspace["evidence"] / "part_b.bin"
    part_c = workspace["evidence"] / "part_c.bin"
    part_a.write_bytes(original[:first_split])
    part_b.write_bytes(original[first_split:second_split])
    part_c.write_bytes(original[second_split:])

    damaged = bytearray(original)
    # One interior portion is destroyed, the tail is gone, the rest is intact.
    damaged[first_split:first_split + PORTION_SIZE] = b"\x00" * PORTION_SIZE
    damaged = damaged[:second_split]
    target = workspace["evidence"] / "whole.png"
    target.write_bytes(bytes(damaged))

    result = engine_for(workspace).recover(target, [part_a, part_b, part_c])

    assert result.status == STATUS_RECONSTRUCTED, result.insights
    assert Path(result.artifact_path).read_bytes() == original
    assert result.artifact_sha256 == sha256(original)

    sources = {p.source_path for p in result.recovered_portions}
    assert len(sources) >= 2, f"expected several evidence files, used {sources}"
    kinds = {p.kind for p in result.recovered_portions}
    assert "interior" in kinds and "tail" in kinds

    offsets = [p.target_offset for p in result.recovered_portions]
    assert offsets == sorted(offsets), "recorded placement must follow real offsets"
    for portion in result.recovered_portions:
        assert portion.size > 0
        assert Path(portion.source_path).is_file()


# ------------------------------------------------------------------
# Case F: partial reconstruction
# ------------------------------------------------------------------

def test_partial_recovery_is_labelled_partial(workspace):
    original = build_pdf(b"PARTIAL-RECOVERY-BODY-" * 400)
    truncated = original[: PORTION_SIZE]
    target = workspace["evidence"] / "truncated.pdf"
    target.write_bytes(truncated)

    result = engine_for(workspace).recover(target, [target])

    assert result.status in (STATUS_PARTIALLY_RECONSTRUCTED, STATUS_NO_RECONSTRUCTION)
    if result.status == STATUS_PARTIALLY_RECONSTRUCTED:
        assert result.missing_portions > 0
        assert result.missing_bytes > 0
        assert result.validation["structurally_valid"] is False
        assert Path(result.artifact_path).is_file()
    else:
        assert result.artifact_path is None


# ------------------------------------------------------------------
# Case G/H: unrelated evidence and honest failure
# ------------------------------------------------------------------

def test_unrelated_evidence_produces_no_artifact(workspace):
    original = build_png(noise(600 * 64, 7))
    target = workspace["evidence"] / "lost.png"
    target.write_bytes(original[: PORTION_SIZE + 128])

    unrelated = workspace["evidence"] / "unrelated.txt"
    unrelated.write_bytes(b"completely different content " * 500)
    also_unrelated = workspace["evidence"] / "other.png"
    also_unrelated.write_bytes(build_png(b"other file entirely " * 50))

    result = engine_for(workspace).recover(target, [unrelated, also_unrelated])

    assert result.status == STATUS_NO_RECONSTRUCTION
    assert result.artifact_path is None
    assert not list(workspace["recovered"].iterdir()), "no placeholder file may be written"
    # The unrelated PNG was examined and rejected: the target's own truncated
    # chunk is still incomplete, so the bytes are not really its missing tail.
    outstanding = (result.validation or {}).get("outstanding_issues") or []
    assert "TRUNCATED_CHUNK" in outstanding
    assert any("insight" in text for text in result.insights) or result.insights


def test_missing_evidence_reports_no_reliable_reconstruction(workspace):
    original = build_png(noise(400 * 64, 7))
    target = workspace["evidence"] / "orphan.png"
    target.write_bytes(original[: PORTION_SIZE * 2])

    result = engine_for(workspace).recover(target, [])

    assert result.status == STATUS_NO_RECONSTRUCTION
    assert result.artifact_path is None
    assert result.error is None, "an honest negative result is not an engine error"


# ------------------------------------------------------------------
# Structural validation of the real formats
# ------------------------------------------------------------------

def test_structure_validation_detects_real_format_damage():
    png = build_png(b"validation payload")
    assert validate_structure(png, "PNG")[0] is True
    assert validate_structure(png[:-40], "PNG")[0] is False, "a PNG without IEND is invalid"

    pdf = build_pdf(b"hello pdf body")
    assert validate_structure(pdf, "PDF")[0] is True
    assert validate_structure(pdf[: len(pdf) - 40], "PDF")[0] is False

    archive = build_zip({"note.txt": b"zip member payload"})
    assert validate_structure(archive, "ZIP")[0] is True
    assert validate_structure(archive[: len(archive) - 30], "ZIP")[0] is False

    image = build_jpeg()
    assert validate_structure(image, "JPEG")[0] is True
    assert validate_structure(image[:-4], "JPEG")[0] is False


def test_recovered_jpeg_from_evidence_is_byte_identical(workspace):
    original = build_jpeg(noise(200 * 64, 13))
    full_copy = workspace["evidence"] / "camera_backup.jpg"
    full_copy.write_bytes(original)

    target = workspace["evidence"] / "photo.jpg"
    target.write_bytes(original[: len(original) - (PORTION_SIZE + 32)])

    result = engine_for(workspace).recover(target, [full_copy])

    assert result.status == STATUS_RECONSTRUCTED, result.insights
    assert Path(result.artifact_path).read_bytes() == original
    assert result.artifact_sha256 == sha256(original)
    assert result.artifact_path.endswith("photo_recovered.jpg")


def test_original_file_is_never_modified(workspace):
    original = build_png(noise(400 * 64, 7))
    full_copy = workspace["evidence"] / "backup.png"
    full_copy.write_bytes(original)

    target = workspace["evidence"] / "target.png"
    target_bytes = original[: len(original) - PORTION_SIZE - 10]
    target.write_bytes(target_bytes)

    engine_for(workspace).recover(target, [full_copy])

    assert target.read_bytes() == target_bytes
    assert full_copy.read_bytes() == original


# ------------------------------------------------------------------
# Evidence-proven damage in opaque binary files
# ------------------------------------------------------------------

def test_binary_damage_is_localised_by_comparing_with_evidence(workspace):
    """Opaque binaries: only the ranges that really differ are restored."""
    original = build_opaque_binary(200 * 1024, seed=5)
    backup = workspace["evidence"] / "system_backup.dll"
    backup.write_bytes(original)

    damaged = bytearray(original)
    damaged[8192:8192 + 4096] = b"\x00" * 4096
    target = workspace["evidence"] / "system.dll"
    target.write_bytes(bytes(damaged))

    result = engine_for(workspace).recover(target, [backup])

    assert result.status == STATUS_RECONSTRUCTED, result.insights
    assert Path(result.artifact_path).read_bytes() == original
    assert result.artifact_sha256 == sha256(original)
    assert result.validation["validated_by"] == "evidence_continuity"

    # Only the genuinely damaged range is claimed as recovered: intact padding
    # and intact content are never rewritten.
    interior = [p for p in result.recovered_portions if p.kind == "interior"]
    assert len(interior) == 1
    recovered_range = (interior[0].target_offset, interior[0].target_offset + interior[0].size)
    assert recovered_range[0] <= 8192 < recovered_range[1]
    assert interior[0].source_path == str(backup)


def test_intact_padding_in_a_binary_is_not_treated_as_damage(workspace):
    """A real binary's own zero padding must not be reported as damage."""
    original = build_opaque_binary(80 * 1024, seed=9, padding_at=(4096, 8192))
    backup = workspace["evidence"] / "padding_backup.bin"
    backup.write_bytes(original)
    target = workspace["evidence"] / "padding.bin"
    target.write_bytes(original)

    result = engine_for(workspace).recover(target, [backup])

    assert result.status == STATUS_INTACT
    assert result.artifact_path is None


def test_binary_damage_with_no_evidence_reports_no_reconstruction(workspace):
    """An unknown binary with a wiped region and no evidence: honest failure."""
    original = build_opaque_binary(60 * 1024, seed=3, mz_header=False)
    damaged = bytearray(original)
    damaged[4096:4096 + 2048] = b"\x00" * 2048
    target = workspace["evidence"] / "damaged.bin"
    target.write_bytes(bytes(damaged))

    result = engine_for(workspace).recover(target, [])

    assert result.status == STATUS_NO_RECONSTRUCTION
    assert result.artifact_path is None
    assert not list(workspace["recovered"].iterdir())


# ------------------------------------------------------------------
# Windows PE images, validated from their own headers
# ------------------------------------------------------------------

def build_pe_image(section_size: int = 24 * 1024, seed: int = 4) -> bytes:
    """A small but structurally valid PE image with one real section."""
    import random

    e_lfanew = 0x80
    raw_offset = 0x400

    dos = bytearray(0x80)
    dos[0:2] = b"MZ"
    struct.pack_into("<I", dos, 0x3C, e_lfanew)

    coff_header = struct.pack("<4sHHIIIHH", b"PE\x00\x00", 0x8664, 1, 0, 0, 0,
                              0xE0, 0x0022)
    optional = bytearray(0xE0)
    struct.pack_into("<HBB", optional, 0, 0x20B, 14, 0)
    struct.pack_into("<I", optional, 0x10, raw_offset)
    struct.pack_into("<II", optional, 0x18, 0x1000, 0x1000)
    section = struct.pack("<8sIIIIIIHHI", b".text", section_size, 0x1000,
                          section_size, raw_offset, 0, 0, 0, 0, 0x60000020)

    headers = bytes(dos + coff_header + bytes(optional) + section)
    assert len(headers) < raw_offset
    padding = bytes(raw_offset - len(headers))
    body = random.Random(seed).randbytes(section_size)
    return headers + padding + body


def test_truncated_pe_image_is_detected_from_its_own_section_table(workspace):
    """A PE that ends before its last section is genuinely truncated."""
    original = build_pe_image()
    backup = workspace["evidence"] / "app_backup.exe"
    backup.write_bytes(original)

    target = workspace["evidence"] / "app.exe"
    target.write_bytes(original[: len(original) - 4096])

    result = engine_for(workspace).recover(target, [backup])

    assert result.status == STATUS_RECONSTRUCTED, result.insights
    assert Path(result.artifact_path).read_bytes() == original
    assert result.artifact_sha256 == sha256(original)
    assert result.validation["validated_by"] == "structure"

    truncation = [
        f for f in detect_damage(original[: len(original) - 4096])
        if f.kind == "TRUNCATED_SEGMENT"
    ]
    assert len(truncation) == 1
    assert truncation[0].fatal is True


def test_truncated_pe_with_unrelated_evidence_is_not_reconstructed(workspace):
    """Truncation is real, but unrelated evidence must never fill it in."""
    original = build_pe_image(section_size=32 * 1024, seed=7)
    target = workspace["evidence"] / "truncated.exe"
    target.write_bytes(original[: len(original) - 6000])
    unrelated = workspace["evidence"] / "notes.txt"
    unrelated.write_bytes(b"unrelated notes, no code here\n" * 400)

    result = engine_for(workspace).recover(target, [unrelated])

    assert result.status == STATUS_NO_RECONSTRUCTION
    assert result.artifact_path is None
    assert not list(workspace["recovered"].iterdir())


def test_complete_pe_image_is_reported_intact(workspace):
    """Real Windows padding must not make an intact executable look damaged."""
    original = build_pe_image(section_size=16 * 1024, seed=11)
    damaged_padding = bytearray(original)
    damaged_padding[0x200:0x200 + 2048] = b"\x00" * 2048
    backup = workspace["evidence"] / "padded_backup.exe"
    backup.write_bytes(bytes(damaged_padding))
    target = workspace["evidence"] / "padded.exe"
    target.write_bytes(original)

    result = engine_for(workspace).recover(target, [backup])

    assert result.status == STATUS_INTACT
    assert result.artifact_path is None


