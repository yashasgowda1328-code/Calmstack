"""
ReConstructAI - Environment & Runtime Path Configuration

Resolves writable application-data paths for SQLite storage, recovered artifacts,
reports, and uploads. Ensures compliance with Windows AppData guidelines when
frozen or installed, while remaining compatible with local project development
and pytest runs.
"""

import os
import sys
from pathlib import Path


def get_app_data_dir() -> Path:
    """Return the writable application data directory."""
    if "RECONSTRUCTAI_APP_DATA" in os.environ:
        app_dir = Path(os.environ["RECONSTRUCTAI_APP_DATA"])
    elif getattr(sys, "frozen", False):
        local_app_data = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if local_app_data:
            app_dir = Path(local_app_data) / "ReConstructAI"
        else:
            app_dir = Path.home() / ".reconstructai"
    else:
        # Development / Pytest mode uses project root 'storage'
        project_root = Path(__file__).resolve().parent.parent.parent
        app_dir = project_root / "storage"

    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_db_path() -> Path:
    """Return path to SQLite database."""
    db_path = get_app_data_dir() / "reconstructai.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def get_reconstructed_dir() -> Path:
    """Return path to recovered artifacts folder."""
    reconstructed = get_app_data_dir() / "reconstructed"
    reconstructed.mkdir(parents=True, exist_ok=True)
    return reconstructed


def get_reports_dir() -> Path:
    """Return path to reports output folder."""
    reports = get_app_data_dir() / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    return reports


def get_uploads_dir() -> Path:
    """Return path to uploaded evidence storage."""
    uploads = get_app_data_dir() / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    return uploads
