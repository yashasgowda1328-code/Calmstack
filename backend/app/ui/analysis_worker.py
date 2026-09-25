"""
ReConstructAI - Analysis Worker Thread
Background worker for running CoreEngine analysis without blocking UI.
"""

from PySide6.QtCore import QThread, Signal, QObject
from pathlib import Path
from typing import Optional, Dict, Any, List
import traceback

# Import CoreEngine
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.core_engine.engine import CoreEngine, WorkflowProgress, EngineStatus, ScanWorkflowResult
from app.storage.database import get_case


class AnalysisWorker(QThread):
    """Background worker for analyzing evidence files using CoreEngine."""
    
    # Signals
    progress = Signal(str, int, str)  # message, percent, stage
    file_started = Signal(str)  # file path
    file_completed = Signal(str, dict)  # file path, result data
    file_failed = Signal(str, str)  # file path, error
    analysis_complete = Signal(bool, str)  # success, message
    case_created = Signal(str)  # case_id
    
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
    
    def run(self):
        """Main analysis loop."""
        try:
            self._core_engine = CoreEngine()
            
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
            
            for idx, file_path in enumerate(self.file_paths):
                if self._cancelled:
                    self.analysis_complete.emit(False, "Analysis cancelled")
                    return
                
                # Progress update
                percent = int((idx / total_files) * 100)
                self.progress.emit(
                    f"Analyzing {idx + 1} / {total_files} files",
                    percent,
                    "analyzing"
                )
                
                self.file_started.emit(file_path)
                
                try:
                    # Run scan on this file
                    result = self._core_engine.run_scan(self.case_id, Path(file_path))
                    
                    if result.status == "completed":
                        # Extract relevant analysis data for UI
                        analysis_data = self._extract_analysis_data(result, file_path)
                        self.file_completed.emit(file_path, analysis_data)
                        successful += 1
                    else:
                        error_msg = result.error or "Unknown error"
                        self.file_failed.emit(file_path, error_msg)
                        failed += 1
                        
                except Exception as e:
                    error_msg = f"{type(e).__name__}: {str(e)}"
                    self.file_failed.emit(file_path, error_msg)
                    failed += 1
            
            # Final progress
            self.progress.emit(
                f"Analysis complete: {successful} successful, {failed} failed",
                100,
                "completed"
            )
            
            self.analysis_complete.emit(
                successful > 0,
                f"Analyzed {successful} files successfully, {failed} failed"
            )
            
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
        }
        
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
        
        # Add reconstruction info if available
        if reconstructions:
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
        """Map CoreEngine results to UI status."""
        # If no fragments, it's a very small file
        if not fragments:
            return "HEALTHY"
        
        # If has reconstructions, check their status
        if reconstructions:
            # Check if any reconstruction is successful
            for r in reconstructions:
                if r["status"] in ("RECONSTRUCTED", "PARTIALLY_RECONSTRUCTED"):
                    if r["status"] == "RECONSTRUCTED":
                        return "RECOVERED"
                    else:
                        return "PARTIALLY_RECOVERABLE"
            
            # Has candidates but none reconstructed yet
            return "FRAGMENTED"
        
        # Has fragments and relationships but no reconstructions
        if relationships:
            # Check relationship scores
            high_score_rels = [r for r in relationships if r.get("relationship_score", 0) > 0.7]
            if high_score_rels:
                return "SUSPICIOUS"
            return "FRAGMENTED"
        
        # Has fragments but no relationships
        if len(fragments) > 1:
            return "SUSPICIOUS"
        
        # Single fragment, no relationships
        entropy = file_info.get("entropy", 0)
        if entropy > 7.5:
            return "SUSPICIOUS"  # High entropy = possibly encrypted/compressed
        
        return "HEALTHY"


class SingleFileAnalysisWorker(QThread):
    """Background worker for analyzing a single file."""
    
    progress = Signal(str, int)
    completed = Signal(bool, dict, str)  # success, result_data, error_message
    
    def __init__(self, file_path: str, case_id: str = None):
        super().__init__()
        self.file_path = file_path
        self.case_id = case_id
        self._core_engine = None
    
    def run(self):
        try:
            self._core_engine = CoreEngine()
            
            # Create case if needed
            if not self.case_id:
                self.case_id = self._core_engine.create_case("Single File Analysis")
            
            self.progress.emit("Starting analysis...", 10)
            
            # Run scan
            result = self._core_engine.run_scan(self.case_id, Path(self.file_path))
            
            self.progress.emit("Processing results...", 80)
            
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
        """Map CoreEngine results to UI status."""
        if not fragments:
            return "HEALTHY"
        
        if reconstructions:
            for r in reconstructions:
                if r["status"] in ("RECONSTRUCTED", "PARTIALLY_RECONSTRUCTED"):
                    if r["status"] == "RECONSTRUCTED":
                        return "RECOVERED"
                    else:
                        return "PARTIALLY_RECOVERABLE"
            return "FRAGMENTED"
        
        if relationships:
            high_score_rels = [r for r in relationships if r.get("relationship_score", 0) > 0.7]
            if high_score_rels:
                return "SUSPICIOUS"
            return "FRAGMENTED"
        
        if len(fragments) > 1:
            return "SUSPICIOUS"
        
        entropy = file_info.get("entropy", 0)
        if entropy > 7.5:
            return "SUSPICIOUS"
        
        return "HEALTHY"