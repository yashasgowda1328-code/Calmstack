#!/usr/bin/env python3
"""
ReConstructAI - Application Entry Point

Launches the PySide6 desktop application.
"""

import sys
import os

# Add backend to path
backend_path = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_path)

from app.ui.main_window import main

if __name__ == "__main__":
    sys.exit(main())