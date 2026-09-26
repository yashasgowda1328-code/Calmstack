"""
Pytest configuration for the ReConstructAI backend.

Every test run is pointed at an isolated temporary application-data directory
*before* any application module is imported. `app.storage.database` resolves its
SQLite path at import time, so isolation has to happen here - otherwise a test
that sets the variable later writes into the project's production storage
(`storage/reconstructai.db`, `storage/reconstructed`, `storage/uploads`).
"""

import os
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Force (do not default) the override so a developer machine that already has
# RECONSTRUCTAI_APP_DATA set cannot leak production data into the test run.
_TEST_APP_DATA = Path(tempfile.mkdtemp(prefix="reconstructai-tests-"))
os.environ["RECONSTRUCTAI_APP_DATA"] = str(_TEST_APP_DATA)

# Keep Qt headless: no test may require a visible desktop session.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def pytest_sessionfinish(session, exitstatus):
    """Remove the temporary application-data directory used by the test run."""
    import shutil

    shutil.rmtree(_TEST_APP_DATA, ignore_errors=True)
