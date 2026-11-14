"""Storage for the participant-wise OI history, plus the trading calendar.

One CSV, one row per (date, client type), in the same column order the old
workbook used, so the two can be compared directly.
"""

from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
HISTORY = DATA / "participant_oi.csv"
STATE = DATA / "state.json"
SHARED_HOLIDAYS = ROOT.parent / "common" / "nse_holidays.json"
NIFTY_CLOSE = ROOT.parent / "gift-nifty-oi" / "data" / "nifty_daily.csv"

from fetch import FIELDS  # noqa: E402

COLUMNS = ["date", "client"] + FIELDS


def _holiday_dates():
    try:
        payload = json.loads(SHARED_HOLIDAYS.read_text())
        dates = set()
        for year_block in (payload.get("holidays") or {}).values():
            if isinstance(year_block, dict):
                dates.update(year_block.keys())
        return dates
    except Exception:
        return set()


def is_trading_day(day: date) -> bool:
    if day.weekday() >= 5:
        return False
    return day.isoformat() not in _holiday_dates()


def load():
    """{date_str: {client: {field: value}}} for everything on disk."""
    if not HISTORY.exists():
        return {}
    out = {}
    with HISTORY.open(newline="") as fh:
        for row in csv.DictReader(fh):
            d = row["date"]
            client = row["client"]
            out.setdefault(d, {})[client] = {
                f: int(float(row[f] or 0)) for f in FIELDS}
    return out


def last_date():
    dates = sorted(load())
    return dates[-1] if dates else None


def append(rows):
    """Append parsed rows, creating the file with a header if needed."""
    if not rows:
        return 0
    DATA.mkdir(exist_ok=True)
    exists = HISTORY.exists()
    with HISTORY.open("a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return len(rows)


def dates_on_disk():
    return set(load())


def missing_sessions(lookback: int = 15):
    """Trading days between the last stored date and today, oldest first."""
    from datetime import timezone
    today = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    start = today - timedelta(days=lookback)
    have = dates_on_disk()
    out = []
    day = start
    while day <= today:
        if is_trading_day(day) and day.isoformat() not in have:
            out.append(day)
        day += timedelta(days=1)
    return out


def nifty_closes():
    """{date: close} from the GIFT pipeline's price file, if it is present."""
    if not NIFTY_CLOSE.exists():
        return {}
    out = {}
    with NIFTY_CLOSE.open(newline="") as fh:
        for row in csv.DictReader(fh):
            raw = (row.get("date") or "").strip()
            try:
                value = float(row["nifty"])
            except (KeyError, TypeError, ValueError):
                continue
            iso = _iso(raw)
            if iso:
                out[iso] = value
    return out


def _iso(raw):
    """Accept both 2026-11-13 and 13-Nov-2026."""
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def read_state():
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def write_state(state):
    DATA.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
