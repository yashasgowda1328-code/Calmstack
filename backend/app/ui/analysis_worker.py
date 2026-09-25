"""
ReConstructAI - Analysis Worker Thread
Background worker for running CoreEngine analysis without blocking UI.
"""

from PySide6.QtCore import QThread, Signal, QObject
from pathlib import Path
from typing import Optional, Dict, Any, List
import os
import traceback

# Import CoreEngine
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.core_engine.engine import CoreEngine, WorkflowProgress, EngineStatus, ScanWorkflowResult
from app.storage.database import get_case
from app.ui.data import derive_file_status


#: Human-readable labels for the engine's workflow stages.
STAGE_LABELS = {
    "create_scan": "Creating scan record",
    "analyze": "Reading evidence",
    "extract_fragments": "Fragment analysis",
    "relevance_scoring": "AI relevance scoring",
    "analyze_relationships": "Relationship analysis",
    "generate_reconstructions": "Candidate generation",
    "validate": "Validation",
    "prioritize": "Prioritization",
    "persist": "Persisting results",
    "reconstruct": "Reconstruction",
    "validate_structure": "Structural validation",
    "completed": "Completed",
}


def stage_label(stage: str) -> str:
    """Map an engine stage token to a readable label."""
    if not stage:
        return "Working"
    return STAGE_LABELS.get(stage, stage.replace("_", " ").capitalize())


class AnalysisWorker(QThread):
    """Background worker for analyzing evidence files using CoreEngine."""

    # Signals
    progress = Signal(str, int, str)          # message, percent, stage token
    stage_changed = Signal(str, str)           # stage token, readable label
    file_started = Signal(str)                 # file path
    file_completed = Signal(str, dict)         # file path, result data
    file_failed = Signal(str, str)             # file path, error
    analysis_complete = Signal(bool, str)      # success, message
    case_created = Signal(str)                 # case_id
    relevance_ready = Signal(str, dict)        # scan_id, {fragment_id: relevance}

    def __init__(self, evidence_folder: str, file_paths: List[str] = None,
                 case_id: str = None, case_name: str = "Evidence Analysis"):
        super().__init__()
        self.evidence_folder = evidence_folder
        self.file_paths = file_paths or []
        self.case_id = case_id
        self.case_name = case_name
        self._cancelled = False
        self._core_engine = None

    def cancel(self):
        """Request cancellation."""
        self._cancelled = True

    def _on_engine_progress(self, progress: WorkflowProgress):
        """Relay the engine's real stage information to the UI."""
        self.stage_changed.emit(progress.stage, stage_label(progress.stage))

    def run(self):
        """Main analysis loop."""
        try:
            self._core_engine = CoreEngine()
            self._core_engine.set_progress_callback(self._on_engine_progress)

            # Create or use existing case
            if not self.case_id:
                self.case_id = self._core_engine.create_case(self.case_name)
                self.case_created.emit(self.case_id)

            total_files = len(self.file_paths)
            if total_files == 0:
                self.analysis_complete.emit(True, "No files to analyze")
                return

            successful = 0
            failed = 0
            failures: List[str] = []

            for idx, file_path in enumerate(self.file_paths):
                if self._cancelled:
                    self.analysis_complete.emit(False, "Analysis cancelled")
                    return

                # Progress update: file-level, merged with the engine's own stage
                percent = int(((idx + 1) / total_files) * 100)
                self.progress.emit(
                    f"Analyzing {idx + 1} / {total_files} files",
                    percent,
                    "analyzing"
                )
                self.stage_changed.emit("analyze", stage_label("analyze"))

                self.file_started.emit(file_path)

                try:
                    # Run scan on this file
                    result = self._core_engine.run_scan(self.case_id, Path(file_path))

                    if result.status == "completed":
                        # Extract relevant analysis data for UI
                        analysis_data = self._extract_analysis_data(result, file_path)
                        self.file_completed.emit(file_path, analysis_data)
                        if result.relevance_scores:
                            self.relevance_ready.emit(result.scan_id, result.relevance_scores)
                        successful += 1
                    else:
                        error_msg = result.error or "Unknown error"
                        self.file_failed.emit(file_path, error_msg)
                        failures.append(f"{Path(file_path).name}: {error_msg}")
                        failed += 1

                except Exception as e:
                    error_msg = f"{type(e).__name__}: {str(e)}"
                    self.file_failed.emit(file_path, error_msg)
                    failures.append(f"{Path(file_path).name}: {error_msg}")
                    failed += 1

            # Final progress
            message = (
                f"Analysis complete: {successful} successful, {failed} failed"
                if failed else f"Analysis complete: {successful} files"
            )
            self.progress.emit(message, 100, "completed")
            self.stage_changed.emit("completed", stage_label("completed"))

            if failed and successful == 0:
                self.analysis_complete.emit(False, message)
            else:
                self.analysis_complete.emit(True, message)

        except Exception as e:
            traceback.print_exc()
            self.analysis_complete.emit(False, f"Analysis failed: {str(e)}")

    def _extract_analysis_data(self, result: ScanWorkflowResult, file_path: str) -> Dict[str, Any]:
        """Extract analysis data from CoreEngine result for UI."""
        file_info = result.file_info
        fragments = result.fragments
        relationships = result.relationships
        reconstructions = result.reconstructions

        # Determine status based on analysis results
        status = self._determine_status(file_info, fragments, relationships, reconstructions)

        # Build analysis data dict
        analysis_data = {
            "status": status,
            "sha256": file_info.get("sha256"),
            "entropy": file_info.get("entropy"),
            "detected_type": file_info.get("file_type"),
            "mime_type": file_info.get("mime_type"),
            "size": file_info.get("size"),
            "fragment_count": len(fragments),
            "relationship_count": len(relationships),
            "reconstruction_count": len(reconstructions),
            "scan_id": result.scan_id,
            "case_id": result.case_id,
            "file_id": file_info.get("file_id"),
            "analysis": file_info.get("analysis", {}),
        }

        # Relevance summary for the file: mean score and dominant class
        if result.relevance_scores:
            scores = [
                r.get("relevance_score")
                for r in result.relevance_scores.values()
                if r.get("relevance_score") is not None
            ]
            classes = [r.get("relevance_class") for r in result.relevance_scores.values()]
            if scores:
                analysis_data["relevance_score"] = round(sum(scores) / len(scores), 4)
            if classes:
                for candidate in ("HIGH_RELEVANCE", "UNCERTAIN", "LOW_RELEVANCE"):
                    if candidate in classes:
                        analysis_data["relevance_class"] = candidate
                        break

        # Add fragment details if available
        if fragments:
            analysis_data["fragments"] = [
                {
                    "fragment_id": f["fragment_id"],
                    "offset": f["offset"],
                    "size": f["size"],
                    "entropy": f["entropy"],
                    "sha256": f["sha256"],
                }
                for f in fragments
            ]

        # Add relationship summary
        if relationships:
            scores = [r.get("relationship_score", 0.0) for r in relationships]
            analysis_data["max_relationship_score"] = round(max(scores), 4) if scores else None
            analysis_data["relationships"] = [
                {
                    "fragment_a": r["fragment_a"],
                    "fragment_b": r["fragment_b"],
                    "relationship_score": r["relationship_score"],
                }
                for r in sorted(relationships, key=lambda r: -(r.get("relationship_score") or 0))[:10]
            ]

        # Add reconstruction info if available
        if reconstructions:
            best = max(
                reconstructions,
                key=lambda r: (r.get("confidence_score") or 0.0, r.get("integrity_score") or 0.0),
            )
            analysis_data["integrity"] = best.get("integrity_score")
            analysis_data["confidence"] = best.get("confidence_score")
            analysis_data["reconstructions"] = [
                {
                    "reconstruction_id": r["reconstruction_id"],
                    "status": r["status"],
                    "integrity_score": r["integrity_score"],
                    "confidence_score": r["confidence_score"],
                    "evidence_quality": r["evidence_quality"],
                    "priority": r["priority"],
                    "fragment_count": r["fragment_count"],
                }
                for r in reconstructions
            ]

        return analysis_data

    def _determine_status(self, file_info: Dict, fragments: List,
                          relationships: List, reconstructions: List) -> str:
        """Map CoreEngine results to the shared UI status vocabulary."""
        return derive_file_status(
            fragment_count=len(fragments),
            relationship_scores=[r.get("relationship_score", 0.0) for r in relationships],
            reconstruction_statuses=[r.get("status") for r in reconstructions if r.get("status")],
            entropy=file_info.get("entropy"),
        )


class CrossEvidenceRecoveryWorker(QThread):
    """Rebuild one damaged file from other real evidence files.

    Runs the existing cross-evidence pipeline off the UI thread: it detects the
    damage in the target, then tries to restore it from the evidence files the
    investigator supplied. The emitted payload is the pipeline's own result, so
    the interface never has to invent a recovery outcome.
    """

    progress = Signal(str, int)          # message, percent
    stage_changed = Signal(str, str)     # stage token, readable label
    completed = Signal(dict)             # RecoveryResult.to_dict()

    def __init__(
        self,
        target_path: str,
        evidence_paths: List[str],
        output_dir: Optional[str] = None,
    ):
        super().__init__()
        self.target_path = target_path
        self.evidence_paths = list(evidence_paths)
        self.output_dir = output_dir
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        from app.reconstruction.cross_recovery import (
            PORTION_SIZE,
            CrossEvidenceRecovery,
            RecoveryResult,
            detect_damage,
        )
        from app.routes.scan import calculate_sha256

        target = Path(self.target_path)
        try:
            data = target.read_bytes()
        except OSError as exc:
            result = RecoveryResult(
                target_path=str(target),
                target_size=0,
                target_sha256="",
                error=f"Could not read the target file: {exc}",
            )
            result.insights.append("The target file could not be read.")
            self.completed.emit(result.to_dict())
            return

        self.progress.emit("Reading target evidence", 10)
        self.stage_changed.emit("detect_damage", "Detecting damage")

        damage = detect_damage(data)
        kinds = ", ".join(finding.kind for finding in damage) or "none"
        self.progress.emit(f"Damage detected: {kinds}", 30)

        if not damage:
            result = RecoveryResult(
                target_path=str(target),
                target_size=len(data),
                target_sha256=calculate_sha256(data),
                detected_type=None,
                status="INTACT",
                expected_portions=len(range(0, len(data), PORTION_SIZE)),
                intact_portions=len(range(0, len(data), PORTION_SIZE)),
                integrity=1.0,
                original_bytes=len(data),
                recovered_bytes=len(data),
            )
            result.insights.append(
                "The file is complete, so no cross-evidence recovery was needed."
            )
            self.completed.emit(result.to_dict())
            return

        self.stage_changed.emit("index_evidence", "Indexing evidence")
        self.progress.emit(
            f"Indexing {len(self.evidence_paths)} evidence file(s)", 45
        )

        engine = CrossEvidenceRecovery(
            output_dir=Path(self.output_dir) if self.output_dir else None
        )
        self.stage_changed.emit("recover", "Recovering from evidence")
        self.progress.emit("Matching fragments against evidence", 70)

        result = engine.recover(target, [Path(p) for p in self.evidence_paths])

        self.progress.emit("Validating recovered artifact", 95)
        self.stage_changed.emit("validate", "Structural validation")
        self.completed.emit(result.to_dict())


class SingleFileAnalysisWorker(QThread):
    
    progress = Signal(str, int)
    stage_changed = Signal(str, str)
    completed = Signal(bool, dict, str)  # success, result_data, error_message
    
    def __init__(self, file_path: str, case_id: str = None):
        super().__init__()
        self.file_path = file_path
        self.case_id = case_id
        self._core_engine = None

    def _on_engine_progress(self, progress: WorkflowProgress):
        self.stage_changed.emit(progress.stage, stage_label(progress.stage))
    
    def run(self):
        try:
            self._core_engine = CoreEngine()
            self._core_engine.set_progress_callback(self._on_engine_progress)
            
            # Create case if needed
            if not self.case_id:
                self.case_id = self._core_engine.create_case("Single File Analysis")
            
            self.progress.emit("Starting analysis...", 10)
            
            # Run scan
            result = self._core_engine.run_scan(self.case_id, Path(self.file_path))
            
            self.progress.emit("Processing results...", 80)
            self.stage_changed.emit("analyze", stage_label("analyze"))
            
            if result.status == "completed":
                file_info = result.file_info
                fragments = result.fragments
                relationships = result.relationships
                reconstructions = result.reconstructions
                
                # Build comprehensive result
                analysis_data = {
                    "file_path": self.file_path,
                    "case_id": result.case_id,
                    "scan_id": result.scan_id,
                    "file_info": file_info,
                    "fragments": [
                        {
                            "fragment_id": f["fragment_id"],
                            "offset": f["offset"],
                            "size": f["size"],
                            "entropy": f["entropy"],
                            "sha256": f["sha256"],
                            "byte_stats": f["byte_stats"],
                        }
                        for f in fragments
                    ],
                    "relationships": [
                        {
                            "fragment_a": r["fragment_a"],
                            "fragment_b": r["fragment_b"],
                            "relationship_score": r["relationship_score"],
                            "score_details": r["score_details"],
                        }
                        for r in relationships
                    ],
                    "reconstructions": [
                        {
                            "reconstruction_id": r["reconstruction_id"],
                            "fragment_ids": r["fragment_ids"],
                            "fragment_count": r["fragment_count"],
                            "integrity_score": r["integrity_score"],
                            "confidence_score": r["confidence_score"],
                            "evidence_quality": r["evidence_quality"],
                            "priority": r["priority"],
                            "status": r["status"],
                            "total_size": r["total_size"],
                            "avg_relationship_score": r["avg_relationship_score"],
                            "validation_details": r["validation_details"],
                        }
                        for r in reconstructions
                    ],
                    "analysis": file_info.get("analysis", {}),
                    "file_id": file_info.get("file_id"),
                    "relevance_scores": result.relevance_scores,
                    "status": self._determine_status(file_info, fragments, relationships, reconstructions),
                }
                
                self.progress.emit("Complete", 100)
                self.completed.emit(True, analysis_data, "")
            else:
                self.completed.emit(False, {}, result.error or "Analysis failed")
                
        except Exception as e:
            traceback.print_exc()
            self.completed.emit(False, {}, f"{type(e).__name__}: {str(e)}")
    
    def _determine_status(self, file_info: Dict, fragments: List, 
                          relationships: List, reconstructions: List) -> str:
        """Map CoreEngine results to the shared UI status vocabulary."""
        return derive_file_status(
            fragment_count=len(fragments),
            relationship_scores=[r.get("relationship_score", 0.0) for r in relationships],
            reconstruction_statuses=[r.get("status") for r in reconstructions if r.get("status")],
            entropy=file_info.get("entropy"),
        )