"""Storage for the unusual-options history, plus the trading calendar.

History is kept as one gzipped CSV per month under data/. Only the 20 base
fields are stored; the three derived columns (COI/OI, Traded Value by Vol,
Traded Value by COI) are recomputed when the workbook is built, so a change to
their definition never needs a backfill.
"""

from __future__ import annotations

import csv
import gzip
import json
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
STATE = DATA / "state.json"
SHARED_HOLIDAYS = ROOT.parent / "common" / "nse_holidays.json"

FIELDS = ["TradDt", "XpryDt", "TckrSymb", "StrkPric", "OptnTp", "FinInstrmNm",
          "OpnPric", "HghPric", "LwPric", "ClsPric", "LastPric", "PrvsClsgPric",
          "UndrlygPric", "SttlmPric", "OI lots", "COI lots", "TtlTradgVol",
          "NewBrdLotQty", "Vol/COI", "Gap"]


def _month(date_str):
    return date_str[:7]


def _path(month):
    return DATA / f"{month}.csv.gz"


def append(rows):
    """Add rows to the month file(s) they belong to. Returns rows written."""
    DATA.mkdir(exist_ok=True)
    by_month = {}
    for row in rows:
        by_month.setdefault(_month(row[0]), []).append(row)

    written = 0
    for month, fresh in by_month.items():
        path = _path(month)
        existing = []
        if path.exists():
            with gzip.open(path, "rt", newline="") as fh:
                existing = [r for r in csv.reader(fh)][1:]
        dates = {r[0] for r in fresh}
        kept = [r for r in existing if r[0] not in dates]     # idempotent per date
        merged = kept + [[str(v) for v in r] for r in fresh]
        merged.sort(key=lambda r: (r[0], r[2], float(r[3]), r[4]))
        with gzip.open(path, "wt", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(FIELDS)
            w.writerows(merged)
        written += len(fresh)
    return written


def load(sessions=None):
    """All history, oldest first. Optionally only the last `sessions` sessions."""
    if not DATA.exists():
        return []
    rows = []
    for path in sorted(DATA.glob("*.csv.gz")):
        with gzip.open(path, "rt", newline="") as fh:
            for r in list(csv.reader(fh))[1:]:
                rows.append(r)
    rows.sort(key=lambda r: (r[0], r[2], float(r[3]), r[4]))
    if sessions:
        keep = sorted({r[0] for r in rows})[-sessions:]
        allowed = set(keep)
        rows = [r for r in rows if r[0] in allowed]
    return rows


def dates():
    return sorted({r[0] for r in load()})


def holidays():
    try:
        payload = json.loads(SHARED_HOLIDAYS.read_text())
    except Exception:
        return set()
    out = set()
    for block in (payload.get("holidays") or {}).values():
        if isinstance(block, dict):
            out.update(block.keys())
    return out


def missing_sessions(lookback=15):
    """Weekdays since the last stored session that aren't holidays."""
    have = set(dates())
    hol = holidays()
    today = date.today()
    out = []
    for i in range(lookback):
        day = today - timedelta(days=i)
        if day.weekday() >= 5:
            continue
        iso = day.isoformat()
        if iso in have or iso in hol:
            continue
        out.append(day)
    return sorted(out)


def read_state():
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def write_state(state):
    DATA.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2) + "\n")
