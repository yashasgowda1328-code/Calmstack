from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class Fragment(BaseModel):
    fragment_id: str
    scan_id: str
    offset: int
    size: int
    sha256: str
    entropy: float
    byte_stats: dict


class Relationship(BaseModel):
    fragment_a: str
    fragment_b: str
    relationship_score: float
    score_details: dict


class ReconstructionCandidate(BaseModel):
    reconstruction_id: str
    fragment_ids: list[str]
    fragment_count: int
    integrity_score: float
    confidence_score: float
    evidence_quality: str
    priority: str
    status: str
    total_size: int
    avg_relationship_score: float
    validation_details: dict


class ScanResult(BaseModel):
    scan_id: str
    filename: str
    size: int
    sha256: str
    file_type: str
    mime_type: str
    entropy: float
    status: str
    scanned_at: datetime
    analysis: dict
    fragments: list[Fragment]
    fragment_count: int
    relationships: list[Relationship]
    reconstructions: list[ReconstructionCandidate]