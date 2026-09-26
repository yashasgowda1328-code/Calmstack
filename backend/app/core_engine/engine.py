"""
Core Engine Orchestration Module for ReConstructAI

Coordinates the complete investigation workflow:
Case -> Evidence -> Analysis -> Fragments -> Relationships -> 
Reconstructions -> Validation -> Prioritization -> Persistence

This is the main entry point for the PySide6 Desktop UI.
"""

import os
import uuid
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

from app.routes.scan import (
    extract_fragments, detect_file_type, find_uploaded_file,
    calculate_sha256, calculate_entropy, get_byte_stats, FRAGMENT_SIZE
)
from app.core.relationships import analyze_relationships, RelationshipScorer
from app.ai.fragment_relevance import create_relevance_model, get_relevance_model, FragmentRelevanceModel, FragmentRelevanceResult
from app.core.reconstruction import build_reconstructions, ReconstructionEngine
from app.reconstruction.engine import ReconstructionEngine as ArtifactReconstructionEngine, ReconstructionResult
from app.reconstruction.validator import StructuralValidator, StructuralValidationResult
from app.storage.database import (
    initialize_database, create_case, create_scan, update_scan_status,
    save_file, save_fragments_bulk, save_relationships_bulk, save_reconstruction,
    update_reconstruction_result,
    persist_scan_result, get_database_stats
)
from app.models.scan import Fragment, Relationship, ReconstructionCandidate, ScanResult


class EngineStatus(Enum):
    """Workflow status stages."""
    IDLE = "IDLE"
    CREATING_SCAN = "CREATING_SCAN"
    ANALYZING = "ANALYZING"
    EXTRACTING_FRAGMENTS = "EXTRACTING_FRAGMENTS"
    SCORING_RELEVANCE = "SCORING_RELEVANCE"
    ANALYZING_RELATIONSHIPS = "ANALYZING_RELATIONSHIPS"
    GENERATING_RECONSTRUCTIONS = "GENERATING_RECONSTRUCTIONS"
    VALIDATING = "VALIDATING"
    PRIORITIZING = "PRIORITIZING"
    PERSISTING = "PERSISTING"
    RECONSTRUCTING = "RECONSTRUCTING"
    VALIDATING_STRUCTURE = "VALIDATING_STRUCTURE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class WorkflowProgress:
    """Progress information for UI callbacks."""
    status: EngineStatus
    stage: str
    message: str
    progress_percent: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScanWorkflowResult:
    """Complete result of a scan workflow."""
    case_id: str
    scan_id: str
    status: str
    file_info: Dict[str, Any]
    fragments: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]]
    reconstructions: List[Dict[str, Any]]
    relevance_scores: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    relevance_error: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ReconstructionWorkflowResult:
    """Result of a reconstruction workflow."""
    reconstruction_id: str
    status: str
    output_path: Optional[str] = None
    output_size: int = 0
    output_sha256: Optional[str] = None
    structural_validation: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class CoreEngine:
    """
    Core Engine orchestrating the complete ReConstructAI investigation workflow.
    
    Usage:
        engine = CoreEngine()
        engine.set_progress_callback(callback)
        
        # Create a case
        case_id = engine.create_case("Case Name", "Description")
        
        # Run complete scan workflow
        result = engine.run_scan(case_id, "path/to/evidence")
        
        # Reconstruct a specific candidate
        recon_result = engine.reconstruct(candidate.reconstruction_id)
    """
    
    def __init__(
        self,
        upload_dir: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        fragment_size: int = FRAGMENT_SIZE,
        relationship_threshold: float = 0.70,
        use_ml_scoring: bool = True
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
        self.relationship_threshold = relationship_threshold
        self.use_ml_scoring = use_ml_scoring
        
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        initialize_database()
        
        # Initialize component engines
        self.relationship_scorer = RelationshipScorer(use_ml=use_ml_scoring)
        self.reconstruction_engine = ArtifactReconstructionEngine(upload_dir, output_dir, fragment_size)
        self.structural_validator = StructuralValidator()
        
        # Initialize AI relevance model
        self.relevance_model = create_relevance_model() if use_ml_scoring else None
        self.relevance_error: Optional[str] = None
        if use_ml_scoring and self.relevance_model is None:
            from app.ai.fragment_relevance import relevance_model_unavailable_reason

            self.relevance_error = (
                relevance_model_unavailable_reason()
                or "the AI relevance model could not be trained"
            )
        
        # Progress callback
        self._progress_callback: Optional[Callable[[WorkflowProgress], None]] = None
        
        # Current workflow state
        self._current_status = EngineStatus.IDLE
        self._current_case_id: Optional[str] = None
        self._current_scan_id: Optional[str] = None
    
    def set_progress_callback(self, callback: Callable[[WorkflowProgress], None]):
        """Set callback for progress updates."""
        self._progress_callback = callback
    
    def _emit_progress(self, status: EngineStatus, stage: str, message: str, 
                       progress: float = 0.0, details: Dict = None):
        """Emit progress to callback if set."""
        self._current_status = status
        if self._progress_callback:
            self._progress_callback(WorkflowProgress(
                status=status,
                stage=stage,
                message=message,
                progress_percent=progress,
                details=details or {}
            ))
    
    def _handle_error(self, stage: str, error: Exception) -> WorkflowProgress:
        """Handle error gracefully."""
        error_msg = f"{stage} failed: {str(error)}"
        self._emit_progress(EngineStatus.FAILED, stage, error_msg, 0.0, {"error": str(error)})
        return WorkflowProgress(
            status=EngineStatus.FAILED,
            stage=stage,
            message=error_msg,
            progress_percent=0.0,
            details={"error": str(error)}
        )
    
    # ============================================================
    # Case Operations
    # ============================================================
    
    def create_case(self, name: str, description: str = "") -> str:
        """Create a new investigation case."""
        case_id = str(uuid.uuid4())
        create_case(case_id, name, description)
        self._current_case_id = case_id
        return case_id
    
    def get_case(self, case_id: str) -> Optional[Dict]:
        """Get case by ID."""
        from app.storage.database import get_case
        return get_case(case_id)
    
    def list_cases(self) -> List[Dict]:
        """List all cases."""
        from app.storage.database import list_cases
        return list_cases()
    
    # ============================================================
    # Evidence / Scan Operations
    # ============================================================
    
    def add_evidence(self, case_id: str, evidence_path: Path) -> str:
        """
        Add evidence file to a case by copying to uploads.
        Returns scan_id.
        """
        evidence_path = Path(evidence_path)
        # Generate scan ID
        scan_id = str(uuid.uuid4())
        
        # Read original file
        with open(evidence_path, "rb") as f:
            content = f.read()
        
        # Calculate hash
        file_sha256 = calculate_sha256(content)
        
        # Save to uploads with scan_id as filename
        ext = evidence_path.suffix
        dest_filename = f"{scan_id}{ext}"
        dest_path = self.upload_dir / dest_filename
        
        with open(dest_path, "wb") as f:
            f.write(content)
        
        # Create scan in database
        create_scan(scan_id, case_id, "uploaded")
        
        return scan_id
    
    def get_evidence_info(self, scan_id: str) -> Optional[Dict]:
        """Get information about uploaded evidence."""
        file_path = find_uploaded_file(scan_id)
        if not file_path:
            return None
        
        with open(file_path, "rb") as f:
            content = f.read()
        
        file_type, mime_type = detect_file_type(file_path)
        
        return {
            "scan_id": scan_id,
            "filename": file_path.name,
            "path": str(file_path),
            "size": len(content),
            "sha256": calculate_sha256(content),
            "file_type": file_type,
            "mime_type": mime_type,
            "entropy": calculate_entropy(content),
        }
    
    # ============================================================
    # Complete Scan Workflow
    # ============================================================
    
    def run_scan(self, case_id: str, evidence_path: Path) -> ScanWorkflowResult:
        """
        Execute complete scan workflow on evidence.
        """
        evidence_path = Path(evidence_path)
        scan_id = str(uuid.uuid4())
        self._current_scan_id = scan_id
        self._current_case_id = case_id
        
        try:
            # Stage 1: Create scan
            self._emit_progress(EngineStatus.CREATING_SCAN, "create_scan", 
                              "Creating scan record", 5.0)
            create_scan(scan_id, case_id, "processing")
            
            # Stage 2: Analyze evidence
            self._emit_progress(EngineStatus.ANALYZING, "analyze", 
                              "Analyzing evidence file", 15.0)
            
            # Read and copy evidence
            with open(evidence_path, "rb") as f:
                content = f.read()
            
            file_sha256 = calculate_sha256(content)
            file_size = len(content)
            file_type, mime_type = detect_file_type(evidence_path)
            file_entropy = calculate_entropy(content)
            analysis = {
                "header_bytes": content[:16].hex() if len(content) >= 16 else content.hex(),
                "is_binary": not all(32 <= b <= 126 or b in (9, 10, 13) for b in content[:100]),
                "null_bytes": content.count(0),
                "unique_bytes": len(set(content)),
            }
            
            # Save to uploads
            ext = evidence_path.suffix
            dest_filename = f"{scan_id}{ext}"
            dest_path = self.upload_dir / dest_filename
            with open(dest_path, "wb") as f:
                f.write(content)
            
            # Save file metadata
            file_id = f"file_{scan_id}"
            save_file(
                file_id=file_id,
                scan_id=scan_id,
                filename=evidence_path.name,
                path=str(dest_path),
                size=file_size,
                sha256=file_sha256,
                detected_type=file_type,
                mime_type=mime_type,
                entropy=file_entropy,
                analysis_data=analysis
            )
            
            # Stage 3: Extract fragments
            self._emit_progress(EngineStatus.EXTRACTING_FRAGMENTS, "extract_fragments",
                              f"Extracting {self.fragment_size}-byte fragments", 30.0)
            
            # Use scan-specific fragment IDs to avoid collisions
            fragments = self._extract_fragments_unique(content, scan_id)
            
            # Stage 4: AI relevance scoring
            self._emit_progress(EngineStatus.VALIDATING, "relevance_scoring",
                              "Scoring fragment relevance", 45.0)
            
            relevance_results = self._score_fragment_relevance(fragments)
            
            # Stage 5: Analyze relationships (on all fragments, relevance used for ordering)
            self._emit_progress(EngineStatus.ANALYZING_RELATIONSHIPS, "analyze_relationships",
                              "Calculating fragment relationships", 55.0)
            
            relationships = analyze_relationships(fragments)
            
            # Stage 6: Generate reconstruction candidates
            self._emit_progress(EngineStatus.GENERATING_RECONSTRUCTIONS, "generate_reconstructions",
                              "Generating reconstruction candidates", 65.0)
            
            candidates = build_reconstructions(fragments, relationships, self.relationship_threshold)
            
            # Apply relevance ranking to reconstruction candidates
            if self.relevance_model and relevance_results:
                candidates = self._rank_by_relevance(candidates, fragments, relevance_results)
            
            # Stage 7: Validate candidates
            self._emit_progress(EngineStatus.VALIDATING, "validate",
                              "Validating reconstruction candidates", 75.0)
            
            # Validation is already done in build_reconstructions
            # ReconstructionEngine includes validator
            
            # Stage 8: Prioritize candidates
            self._emit_progress(EngineStatus.PRIORITIZING, "prioritize",
                              "Prioritizing candidates by evidence quality", 80.0)
            
            # Prioritization is already done in build_reconstructions (evidence_quality, priority)
            candidates.sort(key=lambda c: (-c.confidence_score, -c.integrity_score))
            
            # Stage 8: Persist results
            self._emit_progress(EngineStatus.PERSISTING, "persist",
                              "Saving results to database", 90.0)
            
            # Build ScanResult for persistence
            scan_result = ScanResult(
                scan_id=scan_id,
                filename=dest_filename,
                size=file_size,
                sha256=file_sha256,
                file_type=file_type,
                mime_type=mime_type,
                entropy=file_entropy,
                status="completed",
                scanned_at=datetime.utcnow(),
                analysis=analysis,
                fragments=fragments,
                fragment_count=len(fragments),
                relationships=relationships,
                reconstructions=candidates
            )
            
            persist_scan_result(case_id, scan_id, scan_result, fragments, relationships, candidates)
            
            # Update scan status
            update_scan_status(scan_id, "completed")
            
            # Complete
            self._emit_progress(EngineStatus.COMPLETED, "completed",
                              "Scan workflow completed successfully", 100.0)
            
            # Convert to serializable format
            result = ScanWorkflowResult(
                case_id=case_id,
                scan_id=scan_id,
                status="completed",
                file_info={
                    "file_id": file_id,
                    "filename": dest_filename,
                    "path": str(dest_path),
                    "size": file_size,
                    "sha256": file_sha256,
                    "file_type": file_type,
                    "mime_type": mime_type,
                    "entropy": file_entropy,
                    "analysis": analysis
                },
                fragments=[{
                    "fragment_id": f.fragment_id,
                    "offset": f.offset,
                    "size": f.size,
                    "sha256": f.sha256,
                    "entropy": f.entropy,
                    "byte_stats": f.byte_stats
                } for f in fragments],
                relationships=[{
                    "fragment_a": r.fragment_a,
                    "fragment_b": r.fragment_b,
                    "relationship_score": r.relationship_score,
                    "score_details": r.score_details
                } for r in relationships],
                reconstructions=[{
                    "reconstruction_id": c.reconstruction_id,
                    "fragment_ids": c.fragment_ids,
                    "fragment_count": c.fragment_count,
                    "integrity_score": c.integrity_score,
                    "confidence_score": c.confidence_score,
                    "evidence_quality": c.evidence_quality,
                    "priority": c.priority,
                    "status": c.status,
                    "total_size": c.total_size,
                    "avg_relationship_score": c.avg_relationship_score,
                    "validation_details": c.validation_details
                } for c in candidates],
                relevance_scores={
                    fid: r.to_dict() for fid, r in relevance_results.items()
                },
                relevance_error=self.relevance_error
            )
            
            return result
            
        except Exception as e:
            update_scan_status(scan_id, "failed")
            return ScanWorkflowResult(
                case_id=case_id,
                scan_id=scan_id,
                status="failed",
                file_info={},
                fragments=[],
                relationships=[],
                reconstructions=[],
                error=str(e)
            )
    
    # ============================================================
    # Reconstruction Operations
    # ============================================================
    
    def reconstruct(self, reconstruction_id: str, scan_id: str) -> ReconstructionWorkflowResult:
        """
        Reconstruct artifact from a reconstruction candidate.
        
        Uses the existing ArtifactReconstructionEngine.
        """
        try:
            self._emit_progress(EngineStatus.RECONSTRUCTING, "reconstruct",
                              f"Reconstructing artifact {reconstruction_id}", 10.0)
            
            # Get fragments for the scan
            from app.storage.database import get_fragments_by_scan, get_reconstruction
            
            fragments_data = get_fragments_by_scan(scan_id)
            fragments = [Fragment(**f) for f in fragments_data]
            
            # Get reconstruction candidate
            recon_data = get_reconstruction(reconstruction_id)
            if not recon_data:
                raise ValueError(f"Reconstruction {reconstruction_id} not found")
            
            candidate = ReconstructionCandidate(
                reconstruction_id=recon_data['reconstruction_id'],
                fragment_ids=recon_data['fragment_ids'],
                fragment_count=len(recon_data['fragment_ids']),
                integrity_score=recon_data['integrity_score'],
                confidence_score=recon_data['confidence_score'],
                evidence_quality=recon_data['evidence_quality'],
                priority=recon_data['priority'],
                status=recon_data['status'],
                total_size=recon_data.get('output_size', recon_data.get('total_size', 0)),
                avg_relationship_score=recon_data.get('avg_relationship_score', 0.0),
                validation_details=recon_data.get('validation_details') or {}
            )
            
            # Reconstruct artifact
            self._emit_progress(EngineStatus.RECONSTRUCTING, "reconstruct",
                              "Reading and concatenating fragments", 50.0)
            
            result = self.reconstruction_engine.reconstruct(candidate, scan_id, fragments)
            
            # Stage: Structural validation
            self._emit_progress(EngineStatus.VALIDATING_STRUCTURE, "validate_structure",
                              "Validating reconstructed artifact structure", 80.0)
            
            structural_validation = None
            if result.output_path:
                sv = self.structural_validator.validate(Path(result.output_path), reconstruction_id)
                structural_validation = {
                    "file_exists": sv.file_exists,
                    "readable": sv.readable,
                    "size_valid": sv.size_valid,
                    "signature_detected": sv.signature_detected,
                    "detected_type": sv.detected_type,
                    "mime_type": sv.mime_type,
                    "entropy": sv.entropy,
                    "is_binary": sv.is_binary,
                    "null_bytes": sv.null_bytes,
                    "unique_bytes": sv.unique_bytes,
                    "header_bytes": sv.header_bytes,
                    "sha256": sv.sha256,
                    "structurally_valid": sv.structurally_valid,
                    "validation_status": sv.validation_status,
                    "validation_notes": sv.validation_notes
                }
            
            self._emit_progress(EngineStatus.COMPLETED, "completed",
                              "Reconstruction completed", 100.0)

            # Stage: Persist the artifact outcome so Recovered views show it
            validation_details = dict(result.validation or {})
            if structural_validation:
                validation_details["structural_validation"] = structural_validation
            update_reconstruction_result(
                reconstruction_id=reconstruction_id,
                status=result.status,
                output_path=result.output_path or None,
                output_sha256=result.sha256 or None,
                output_size=result.output_size,
                output_entropy=result.entropy,
                output_file_type=result.file_type,
                output_mime_type=result.mime_type,
                validation_status=(structural_validation or {}).get("validation_status"),
                validation_details=validation_details or None
            )

            return ReconstructionWorkflowResult(
                reconstruction_id=reconstruction_id,
                status=result.status,
                output_path=result.output_path,
                output_size=result.output_size,
                output_sha256=result.sha256,
                structural_validation=structural_validation
            )
            
        except Exception as e:
            self._emit_progress(EngineStatus.FAILED, "reconstruct",
                              f"Reconstruction failed: {str(e)}", 0.0, {"error": str(e)})
            try:
                update_reconstruction_result(
                    reconstruction_id=reconstruction_id,
                    status="FAILED",
                    validation_status="FAILED",
                    validation_details={"error": str(e)}
                )
            except Exception:
                pass
            return ReconstructionWorkflowResult(
                reconstruction_id=reconstruction_id,
                status="failed",
                error=str(e)
            )
    
    # ============================================================
    # Utility
    # ============================================================
    
    def get_scan_status(self, scan_id: str) -> Optional[Dict]:
        """Get scan status from database."""
        from app.storage.database import get_scan
        return get_scan(scan_id)
    
    def get_database_stats(self) -> Dict:
        """Get database statistics."""
        return get_database_stats()
    
    def _score_fragment_relevance(self, fragments: List[Fragment]) -> Dict[str, FragmentRelevanceResult]:
        """Score fragments for relevance using AI model.

        When the model cannot run, the reason is recorded and reported through
        the workflow instead of returning an empty mapping: each real fragment
        gets the neutral UNCERTAIN result already used for unscored fragments
        elsewhere in this engine.
        """
        if not self.relevance_model:
            self.relevance_error = self.relevance_model_error or (
                "AI relevance scoring is disabled (use_ml_scoring=False)"
            )
            self._emit_progress(
                EngineStatus.SCORING_RELEVANCE, "relevance_scoring",
                f"AI relevance unavailable: {self.relevance_error}", 45.0,
                {"error": self.relevance_error},
            )
            return self._neutral_relevance(fragments)

        try:
            results = {}
            relevance_results = self.relevance_model.score_fragments(fragments)
            for result in relevance_results:
                results[result.fragment_id] = result
            self.relevance_error = None
            return results
        except Exception as exc:
            self.relevance_error = f"AI relevance scoring failed: {type(exc).__name__}: {exc}"
            self._emit_progress(
                EngineStatus.SCORING_RELEVANCE, "relevance_scoring",
                self.relevance_error, 45.0, {"error": self.relevance_error},
            )
            return self._neutral_relevance(fragments)

    @staticmethod
    def _neutral_relevance(fragments: List[Fragment]) -> Dict[str, FragmentRelevanceResult]:
        """Neutral per-fragment result used when the model cannot score."""
        return {
            fragment.fragment_id: FragmentRelevanceResult(
                fragment_id=fragment.fragment_id,
                relevance_score=0.5,
                relevance_class="UNCERTAIN",
                confidence=0.0,
            )
            for fragment in fragments
        }
    
    def _rank_by_relevance(
        self, 
        candidates: list,
        fragments: List[Fragment],
        relevance_results: Dict[str, FragmentRelevanceResult]
    ) -> list:
        """Rank reconstruction candidates by relevance scores."""
        # For each candidate, calculate average relevance of its fragments
        for candidate in candidates:
            fragment_relevances = [
                relevance_results.get(fid, FragmentRelevanceResult(
                    fragment_id=fid,
                    relevance_score=0.5,
                    relevance_class="UNCERTAIN",
                    confidence=0.0
                ))
                for fid in candidate.fragment_ids
            ]
            
            high_relevance_frags = [r for r in fragment_relevances if r.relevance_class == "HIGH_RELEVANCE"]
            uncertain_frags = [r for r in fragment_relevances if r.relevance_class == "UNCERTAIN"]
            low_relevance_frags = [r for r in fragment_relevances if r.relevance_class == "LOW_RELEVANCE"]
            
            avg_relevance = sum(r.relevance_score for r in fragment_relevances) / len(fragment_relevances) if fragment_relevances else 0.0
            
            # Store relevance assessment in validation_details
            candidate.validation_details = candidate.validation_details or {}
            candidate.validation_details["relevance"] = {
                "average_relevance_score": round(avg_relevance, 4),
                "high_relevance_count": len(high_relevance_frags),
                "uncertain_count": len(uncertain_frags),
                "low_relevance_count": len(low_relevance_frags),
                "per_fragment": {fid: r.to_dict() for fid, r in zip(candidate.fragment_ids, fragment_relevances)},
            }
            
            # Adjust confidence score based on relevance
            # Higher relevance -> higher confidence
            relevance_boost = avg_relevance * 0.1
            candidate.confidence_score = min(1.0, candidate.confidence_score + relevance_boost)
        
        # Sort by relevance-adjusted confidence
        candidates.sort(key=lambda c: -c.confidence_score)
        
        return candidates
    
    @property
    def current_status(self) -> EngineStatus:
        return self._current_status
    
    @property
    def current_case_id(self) -> Optional[str]:
        return self._current_case_id
    
    @property
    def current_scan_id(self) -> Optional[str]:
        return self._current_scan_id
    
    def _extract_fragments_unique(self, content: bytes, scan_id: str) -> List[Fragment]:
        """Extract fragments with unique IDs incorporating scan_id."""
        from app.routes.scan import calculate_sha256, calculate_entropy, get_byte_stats
        
        fragments = []
        total_size = len(content)
        fragment_count = (total_size + self.fragment_size - 1) // self.fragment_size
        
        for i in range(fragment_count):
            offset = i * self.fragment_size
            chunk = content[offset:offset + self.fragment_size]
            size = len(chunk)
            
            # Use scan_id prefix to ensure unique fragment IDs across scans
            fragment_id = f"{scan_id[:8]}_F{i+1:03d}"
            
            fragment = Fragment(
                fragment_id=fragment_id,
                scan_id=scan_id,
                offset=offset,
                size=size,
                sha256=calculate_sha256(chunk),
                entropy=calculate_entropy(chunk),
                byte_stats=get_byte_stats(chunk)
            )
            fragments.append(fragment)
        
        return fragments


# Convenience function for simple usage
def run_investigation(
    case_name: str,
    evidence_path: Path,
    output_dir: Path = Path("storage/reconstructed"),
    progress_callback: Optional[Callable[[WorkflowProgress], None]] = None
) -> ScanWorkflowResult:
    """
    Convenience function to run complete investigation in one call.
    """
    engine = CoreEngine(output_dir=output_dir)
    if progress_callback:
        engine.set_progress_callback(progress_callback)
    
    case_id = engine.create_case(case_name)
    return engine.run_scan(case_id, evidence_path)