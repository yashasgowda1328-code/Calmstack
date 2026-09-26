"""
ReConstructAI - In-process session state

Holds the few pieces of state that the SQLite schema does not persist but
that the interface legitimately needs during a working session:

  * the case / scan currently under investigation
  * the evidence folder currently selected in the Evidence page
  * AI relevance produced by the live CoreEngine run (not written to SQLite)

This is a plain in-memory registry. It is never a source of fabricated data:
every value here originates from a real CoreEngine result or a real user
action in this process.
"""

from typing import Any, Dict, List, Optional


class SessionState:
    """Process-wide registry of the active investigation."""

    def __init__(self):
        self.case_id: Optional[str] = None
        self.case_name: Optional[str] = None
        self.scan_id: Optional[str] = None
        self.evidence_folder: Optional[str] = None
        self.reconstructed_root: Optional[str] = None
        # scan_id -> {fragment_id: relevance dict} captured from a live run
        self._relevance: Dict[str, Dict[str, Dict[str, Any]]] = {}
        # list of (timestamp string, text) for the dashboard activity feed
        self._activity: List[Dict[str, str]] = []

    # -- investigation identity ---------------------------------------
    def set_case(self, case_id: Optional[str], case_name: Optional[str] = None):
        self.case_id = case_id
        if case_name is not None:
            self.case_name = case_name
        if case_id is None:
            self.scan_id = None

    def set_scan(self, scan_id: Optional[str]):
        self.scan_id = scan_id

    def set_evidence_folder(self, path: Optional[str]):
        self.evidence_folder = path

    def has_case(self) -> bool:
        return bool(self.case_id)

    # -- AI relevance from the live run -------------------------------
    def record_relevance(self, scan_id: str, relevance: Dict[str, Dict[str, Any]]):
        if not scan_id or not relevance:
            return
        self._relevance[scan_id] = dict(relevance)
        if len(self._relevance) > 25:
            oldest = next(iter(self._relevance))
            self._relevance.pop(oldest, None)

    def relevance_for_scan(self, scan_id: Optional[str]) -> Dict[str, Dict[str, Any]]:
        if not scan_id:
            return {}
        return self._relevance.get(scan_id, {})

    def relevance_for_fragment(self, scan_id: Optional[str], fragment_id: Optional[str]):
        if not scan_id or not fragment_id:
            return None
        return self._relevance.get(scan_id, {}).get(fragment_id)

    def has_relevance(self, scan_id: Optional[str]) -> bool:
        return bool(scan_id) and bool(self._relevance.get(scan_id))

    # -- activity feed -------------------------------------------------
    def log_activity(self, text: str, kind: str = "info"):
        from datetime import datetime

        self._activity.insert(0, {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "text": text,
            "kind": kind,
        })
        del self._activity[12:]

    def recent_activity(self, limit: int = 6) -> List[Dict[str, str]]:
        return self._activity[:limit]

    def reset(self):
        self.case_id = None
        self.case_name = None
        self.scan_id = None
        self.evidence_folder = None
        self._relevance.clear()
        self._activity.clear()


#: Shared instance used by the pages.
SESSION = SessionState()
