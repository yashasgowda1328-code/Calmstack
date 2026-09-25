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
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.ui.styles import apply_stylesheet, COLORS
from app.ui.sidebar import Sidebar
from app.ui.evidence import EvidencePage, RecoveredPage, PlaceholderPage
from app.ui.deleted_recovery import DeletedDataRecoveryPage
from app.ui.dashboard import DashboardPage
from app.ui.cases import CasesPage
from app.storage.database import initialize_database, get_database_stats
from app.core_engine.engine import CoreEngine


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
        self.content_stack.addWidget(self.pages["dashboard"])
        
        # Evidence / Files
        self.pages["evidence"] = EvidencePage()
        self.pages["evidence"].analyze_requested.connect(self._on_analyze_evidence)
        self.pages["evidence"].folder_selected.connect(self._on_folder_selected)
        self.content_stack.addWidget(self.pages["evidence"])
        
        # All Files (same as evidence for now, filtered view)
        self.pages["all_files"] = PlaceholderPage(
            "All Files",
            "This view will show all discovered files across cases.\n"
            "Implementation pending."
        )
        self.content_stack.addWidget(self.pages["all_files"])
        
        # Status filter pages
        for status in ["healthy", "suspicious", "corrupted", "fragments"]:
            self.pages[status] = PlaceholderPage(
                status.capitalize(),
                f"This view will show files classified as {status}.\n"
                "Run analysis on evidence folder to populate."
            )
            self.content_stack.addWidget(self.pages[status])
        
        # Recovered
        self.pages["recovered"] = RecoveredPage()
        self.content_stack.addWidget(self.pages["recovered"])
        
        # Deleted Data Recovery
        self.pages["deleted_recovery"] = DeletedDataRecoveryPage()
        self.content_stack.addWidget(self.pages["deleted_recovery"])
        
        # Link recovered page for refresh after analysis
        self.pages["evidence"].recovered_page_ref = self.pages["recovered"]
        
        # Reports
        self.pages["reports"] = PlaceholderPage(
            "Reports",
            "Investigation reports will appear here.\n"
            "Generate reports after reconstruction to populate."
        )
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
    
    def _on_navigation_changed(self, page_id: str):
        """Handle sidebar navigation."""
        self._show_page(page_id)
    
    def _check_system_status(self):
        """Check and update system status indicators."""
        # Check database
        try:
            stats = get_database_stats()
            self.sidebar.update_status("database", "ready", "Connected")
            if "dashboard" in self.pages:
                self.pages["dashboard"].update_status("database", "ready", "Connected")
        except Exception as e:
            self.sidebar.update_status("database", "error", f"Error: {str(e)[:30]}")
        
        # Check Core Engine
        try:
            # Quick test
            test_engine = CoreEngine()
            self.sidebar.update_status("engine", "ready", "Ready")
            if "dashboard" in self.pages:
                self.pages["dashboard"].update_status("engine", "ready", "Ready")
        except Exception as e:
            self.sidebar.update_status("engine", "error", f"Error: {str(e)[:30]}")
        
        # Check Storage
        try:
            upload_dir = Path("uploads")
            upload_dir.mkdir(parents=True, exist_ok=True)
            reconstructed_dir = Path("storage/reconstructed")
            reconstructed_dir.mkdir(parents=True, exist_ok=True)
            self.sidebar.update_status("storage", "ready", "Ready")
            if "dashboard" in self.pages:
                self.pages["dashboard"].update_status("storage", "ready", "Ready")
        except Exception as e:
            self.sidebar.update_status("storage", "error", f"Error: {str(e)[:30]}")
    
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
        self.sidebar.set_page("evidence")
        self._show_page("evidence")
        # Could auto-load case's evidence folder here
    
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