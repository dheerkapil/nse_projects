#!/usr/bin/env python3
"""Refresh the F&O universe from NSE's market-lots file.

Writes config/fno_stocks.json only when the symbol set actually changes, so the
daily workflow does not create noise commits. On any failure the existing list
is kept untouched.
"""
from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

import config  # noqa: E402

FNO_URL = "https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv"
INDEX = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50",
         "NIFTYFPI", "Symbol", "UNDERLYING"}


def fetch_symbols() -> list[str]:
    r = requests.get(FNO_URL, headers=config.HTTP_HEADERS, timeout=config.REQUEST_TIMEOUT)
    r.raise_for_status()
    rows = list(csv.reader(io.StringIO(r.text)))
    syms: list[str] = []
    for row in rows[1:]:
        if len(row) > 1:
            s = row[1].strip().strip(",").strip()
            if s and s not in INDEX and s.isupper():
                syms.append(s)
    return sorted(set(syms))


def main() -> int:
    path = Path(config.FNO_FILE)
    try:
        syms = fetch_symbols()
    except Exception as e:
        print(f"[refresh_fno] fetch failed ({e}); keeping existing list")
        return 0

    if len(syms) < 50:  # sanity: NSE F&O is ~200 names
        print(f"[refresh_fno] suspiciously small list ({len(syms)}); keeping existing")
        return 0

    old: list[str] = []
    if path.exists():
        try:
            old = json.loads(path.read_text()).get("stocks", [])
        except Exception:
            old = []

    if sorted(old) == syms:
        print(f"[refresh_fno] unchanged ({len(syms)} symbols)")
        return 0

    path.write_text(json.dumps({"stocks": syms}, indent=2))
    added = sorted(set(syms) - set(old))
    removed = sorted(set(old) - set(syms))
    print(f"[refresh_fno] updated {len(old)} -> {len(syms)} (+{len(added)} -{len(removed)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
