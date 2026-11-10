"""Write per-day reading files.

    python scripts/export_daily.py            # today's (latest) date only
    python scripts/export_daily.py --date 2026-10-15
    python scripts/export_daily.py --all      # every date in the DB

Each date becomes data/daily/<date>.json – written once, never rewritten.
"""

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from src.database import init_database
from src.daily_files import export_date, export_all, latest_date, prune_files

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="export every date in the DB")
    parser.add_argument("--date", help="export one specific date (YYYY-MM-DD)")
    args = parser.parse_args()

    init_database()

    if args.all:
        export_all()
    else:
        date = args.date or latest_date()
        if not date:
            print("No data in the database to export")
            sys.exit(0)
        n = export_date(date)
        print(f"Exported {date}: {n} stocks -> data/daily/{date}.json")

    # keep data/daily a rolling year
    prune_files()
