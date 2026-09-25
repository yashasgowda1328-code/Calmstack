"""
ReConstructAI - Main Application Window
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QStackedWidget,
    QMessageBox, QApplication
)
from PySide6.QtCore import Qt, QTimer, Signal
import sys
import os

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.ui.styles import apply_stylesheet, COLORS
from app.ui.sidebar import Sidebar
from app.ui.evidence import EvidencePage
from app.ui.recovered_page import RecoveredPage
from app.ui.deleted_recovery import DeletedDataRecoveryPage
from app.ui.dashboard import DashboardPage
from app.ui.cases import CasesPage
from app.ui.filtered_files import FilteredFilesPage
from app.ui.fragments_page import FragmentsPage
from app.ui.reports_page import ReportsPage
from app.storage.database import initialize_database
from app.core_engine.engine import CoreEngine
from app.ui.session import SESSION


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ReConstructAI")
        self.resize(1400, 900)
        self.setMinimumSize(1200, 700)
        
        # Core engine instance
        self.core_engine = CoreEngine()
        
        # Current state
        self.current_case_id = None
        self.current_page = "evidence"
        
        self._setup_ui()
        self._check_system_status()
        self._load_initial_data()
    
    def _setup_ui(self):
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        
        # Main layout
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Sidebar
        self.sidebar = Sidebar()
        self.sidebar.navigation_changed.connect(self._on_navigation_changed)
        main_layout.addWidget(self.sidebar)
        
        # Content stack
        self.content_stack = QStackedWidget()
        main_layout.addWidget(self.content_stack, 1)
        
        # Create pages
        self.pages = {}
        
        # Dashboard
        self.pages["dashboard"] = DashboardPage()
        self.pages["dashboard"].create_case_requested.connect(self._create_case_from_dashboard)
        self.pages["dashboard"].open_case_requested.connect(self._open_case_from_dashboard)
        self.pages["dashboard"].analyze_evidence_requested.connect(self._on_dashboard_analyze_evidence)
        self.pages["dashboard"].analyze_single_requested.connect(self._on_dashboard_analyze_single)
        self.pages["dashboard"].recover_deleted_requested.connect(self._on_dashboard_recover_deleted)
        self.content_stack.addWidget(self.pages["dashboard"])
        
        # Evidence / Files
        self.pages["evidence"] = EvidencePage()
        self.pages["evidence"].analyze_requested.connect(self._on_analyze_evidence)
        self.pages["evidence"].folder_selected.connect(self._on_folder_selected)
        self.content_stack.addWidget(self.pages["evidence"])
        
        # All Files (filtered view of the evidence dataset)
        self.pages["all_files"] = FilteredFilesPage("All Files", None, "All files across all cases")
        self.content_stack.addWidget(self.pages["all_files"])
        
        # Status filter pages
        for status in ["healthy", "suspicious", "corrupted"]:
            self.pages[status] = FilteredFilesPage(
                status.capitalize(),
                status.upper(),
                f"Files classified as {status}"
            )
            self.content_stack.addWidget(self.pages[status])
        
        # Fragments page
        self.pages["fragments"] = FragmentsPage()
        self.content_stack.addWidget(self.pages["fragments"])
        
        # Recovered
        self.pages["recovered"] = RecoveredPage()
        self.content_stack.addWidget(self.pages["recovered"])
        
        # Deleted Data Recovery
        self.pages["deleted_recovery"] = DeletedDataRecoveryPage()
        self.content_stack.addWidget(self.pages["deleted_recovery"])
        
        # Link recovered page for refresh after analysis
        self.pages["evidence"].recovered_page_ref = self.pages["recovered"]
        
        # Reports
        self.pages["reports"] = ReportsPage()
        self.content_stack.addWidget(self.pages["reports"])
        
        # Cases (reusing existing)
        self.pages["cases"] = CasesPage()
        self.pages["cases"].case_selected.connect(self._on_case_selected)
        self.content_stack.addWidget(self.pages["cases"])
        
        # Show initial page
        self._show_page("evidence")
    
    def _show_page(self, page_id: str):
        """Switch to a page."""
        if page_id in self.pages:
            self.content_stack.setCurrentWidget(self.pages[page_id])
            self.current_page = page_id
            self.sidebar.set_page(page_id)
            page = self.pages[page_id]
            if hasattr(page, "refresh"):
                try:
                    page.refresh()
                except Exception:
                    pass
            if page_id == "dashboard":
                try:
                    self.pages["dashboard"].refresh_metrics()
                except Exception:
                    pass
    
    def _on_navigation_changed(self, page_id: str):
        """Handle sidebar navigation."""
        self._show_page(page_id)
    
    def _on_dashboard_analyze_evidence(self):
        """Start folder analysis from the dashboard."""
        self._show_page("evidence")
        evidence_page = self.pages["evidence"]
        if evidence_page.get_evidence_folder():
            self._on_analyze_evidence(evidence_page.get_evidence_folder())
        else:
            evidence_page._select_folder()
    
    def _on_dashboard_analyze_single(self):
        """Start single-file analysis from the dashboard."""
        self._show_page("evidence")
        self.pages["evidence"]._on_analyze_single_clicked()
    
    def _on_dashboard_recover_deleted(self):
        """Navigate to deleted data recovery from the dashboard."""
        self._show_page("deleted_recovery")
    
    def _check_system_status(self):
        """Check and update system status indicators from the real subsystems."""
        dashboard = self.pages.get("dashboard")
        if dashboard is not None and hasattr(dashboard, "check_health"):
            dashboard.check_health()
            for component in ("engine", "database", "storage"):
                reported = dashboard.status_strip.state_for(component)
                if reported:
                    self.sidebar.update_status(component, reported[0], reported[1])
    
    def _load_initial_data(self):
        """Load any initial data."""
        # Ensure database is initialized
        try:
            initialize_database()
        except Exception as e:
            print(f"Database init warning: {e}")
    
    def _create_case_from_dashboard(self):
        """Handle create case from dashboard."""
        self._show_page("cases")
        # The cases page handles creation
    
    def _open_case_from_dashboard(self):
        """Handle open case from dashboard."""
        self._show_page("cases")
    
    def _on_case_selected(self, case_id: str):
        """Handle case selection."""
        self.current_case_id = case_id
        from app.storage.database import get_case

        case = get_case(case_id) or {}
        name = case.get("name") or case_id[:8]
        SESSION.set_case(case_id, name)
        SESSION.log_activity(f"Opened case {name}", "case")
        self._show_page("evidence")
    
    def _on_folder_selected(self, folder_path: str):
        """Handle evidence folder selection."""
        # Could create/associate a case here
        pass
    
    def _on_analyze_evidence(self, folder_path: str):
        """Handle analyze evidence request - delegate to evidence page's worker."""
        evidence_page = self.pages["evidence"]
        # Use current case if selected, otherwise create new
        case_id = self.current_case_id
        case_name = f"Analysis - {os.path.basename(folder_path)}"
        evidence_page.start_folder_analysis(case_id=case_id, case_name=case_name)


def main():
    """Application entry point."""
    app = QApplication(sys.argv)
    app.setApplicationName("ReConstructAI")
    app.setApplicationVersion("1.0.0")
    
    # Apply stylesheet
    apply_stylesheet(app)
    
    # Set default font
    font = app.font()
    font.setFamily("Segoe UI")
    font.setPointSize(10)
    app.setFont(font)
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())