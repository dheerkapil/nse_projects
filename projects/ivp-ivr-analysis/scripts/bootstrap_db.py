"""Rebuild the SQLite database from the committed per-day files.

Run this at the start of every daily job: CI runners start with an empty
working tree, so the DB must be reconstructed from data/daily/*.json before
main.py needs a history to compute IVP/IVR against.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from src.database import init_database
from src.daily_files import bootstrap_from_files

if __name__ == "__main__":
    init_database()
    bootstrap_from_files()
