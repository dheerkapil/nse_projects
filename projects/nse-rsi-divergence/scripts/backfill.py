#!/usr/bin/env python3
"""One-off history loader: backfill ~1 year of daily bhavcopy into SQLite.

Usage:
    python scripts/backfill.py --days 365
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from src.downloader import fetch_bhavcopy  # noqa: E402
from src.database import init_db, store_prices  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--end", help="end date YYYY-MM-DD (default: today)")
    args = ap.parse_args()

    init_db()
    end = date.fromisoformat(args.end) if args.end else date.today()
    start = end - timedelta(days=args.days)

    session = requests.Session()
    d = start
    stored_days = 0
    total_rows = 0
    while d <= end:
        if d.weekday() < 5:
            try:
                df = fetch_bhavcopy(d, session=session)
            except Exception as e:  # network hiccup — keep going
                print(f"  {d}  error: {e}")
                d += timedelta(days=1)
                continue
            if df is not None and not df.empty:
                total_rows += store_prices(df)
                stored_days += 1
                print(f"  {d}  {len(df)} rows")
            # None -> holiday / not published; silently skip
        d += timedelta(days=1)

    print(f"\nDone. {stored_days} trading days, {total_rows} rows stored.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
