"""NSE trading-holiday lookup.

On a trading holiday the exchange publishes no bhavcopy, so the daily report has
nothing to do. main.py asks this module whether the day it is about to report on
is a holiday and, if so, sends a one-off holiday notice instead of a report.

Source of truth, in order:
  1. NSE's live holiday-master API (segment FO — this is an F&O report).
  2. config/nse_holidays.json, a bundled copy of the same list, used when the
     API is unreachable (NSE sometimes refuses cloud-runner IPs). This bundled
     copy is refreshed weekly — see sync_holiday_list().

If neither can answer for the year in question the lookup *fails open* — it
reports "not a holiday" — because a missed holiday only costs one spurious
end-of-window alert, whereas wrongly skipping a real trading day would silently
drop a report.
"""

import json
from datetime import datetime, time, timedelta
from pathlib import Path

import requests

from src.config import now_ist

_HOLIDAY_FILE = Path(__file__).resolve().parent.parent / "config" / "nse_holidays.json"
_API_URL = "https://www.nseindia.com/api/holiday-master?type=trading"
_SEGMENT = "FO"                     # Futures & Options — the segment we report on

_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.nseindia.com/',
}

_cache = {}                         # year(int) -> {iso_date: description}


def _parse_nse_date(raw):
    try:
        return datetime.strptime(str(raw), "%d-%b-%Y").date()
    except (ValueError, TypeError):
        return None


def _bundled():
    try:
        payload = json.loads(_HOLIDAY_FILE.read_text())
        return payload.get("holidays", {}) or {}
    except Exception as e:
        print(f"holidays: could not read bundled list ({e})")
        return {}


def _fetch_live(year):
    """{iso_date: description} for `year` from NSE, or None if unreachable."""
    try:
        s = requests.Session()
        # NSE's API needs the session cookies the homepage sets.
        s.get("https://www.nseindia.com/", headers=_HEADERS, timeout=20)
        r = s.get(_API_URL, headers=_HEADERS, timeout=20)
        if r.status_code != 200:
            print(f"holidays: live API returned HTTP {r.status_code}")
            return None
        payload = r.json()
    except Exception as e:
        print(f"holidays: live API unreachable ({e})")
        return None

    out = {}
    for row in payload.get(_SEGMENT) or []:
        d = _parse_nse_date(row.get("tradingDate"))
        if d and d.year == year:
            out[d.isoformat()] = row.get("description", "")
    return out or None


def get_holidays(year):
    """{iso_date: description} for one year. Live API wins, bundled is fallback."""
    year = int(year)
    if year in _cache:
        return _cache[year]

    bundled = _bundled().get(str(year), {})
    live = _fetch_live(year)

    if live is not None:
        merged = dict(bundled)
        merged.update(live)                 # live entries take precedence
        print(f"holidays: {len(merged)} entries for {year} (live API + bundled)")
    else:
        merged = bundled
        if merged:
            print(f"holidays: using bundled list for {year} ({len(merged)} entries)")
        else:
            print(f"holidays: no data for {year} — assuming no holidays")

    _cache[year] = merged
    return merged


def is_trading_holiday(day):
    """Return (is_holiday, description). `day` is a date/datetime."""
    iso = day.date().isoformat() if isinstance(day, datetime) else day.isoformat()
    holidays = get_holidays(day.year)
    return (iso in holidays), holidays.get(iso, "")


# ── weekly refresh of the bundled fallback ────────────────
def week_key(now):
    """ISO [year, week] for `now` — the unit of the weekly sync."""
    iso = now.isocalendar()
    return [iso[0], iso[1]]


def monday_1800_of_week(now):
    """The Monday 18:00 IST that starts `now`'s ISO week."""
    monday = now.date() - timedelta(days=now.weekday())
    return datetime.combine(monday, time(18, 0), tzinfo=now.tzinfo)


def should_sync(now, last_synced_week):
    """
    True on the first run on/after Monday 18:00 IST of a week that hasn't been
    synced yet. Anchoring on the week (not the weekday) means a Monday slot that
    GitHub delivers after midnight still triggers the sync.
    """
    if last_synced_week == week_key(now):
        return False
    return now >= monday_1800_of_week(now)


def sync_holiday_list(year=None):
    """
    Refresh the bundled holiday list for `year` from NSE.

    Returns (ok, changed, count):
        ok=False  — the live API was unreachable; nothing was written.
        ok=True   — the bundled file is now current (changed says whether it moved).
    """
    year = int(year or now_ist().year)
    live = _fetch_live(year)
    if live is None:
        print("holidays: weekly sync skipped — live API unreachable")
        return False, False, 0

    try:
        payload = json.loads(_HOLIDAY_FILE.read_text())
    except Exception:
        payload = {}

    all_holidays = payload.get("holidays", {}) or {}
    if all_holidays.get(str(year)) == live:
        print(f"holidays: weekly sync — {year} list unchanged ({len(live)} entries)")
        return True, False, len(live)

    all_holidays[str(year)] = live
    payload["holidays"] = all_holidays
    payload["source"] = "NSE holiday-master (type=trading), segment FO"
    payload["fetched"] = now_ist().date().isoformat()
    payload["note"] = ("Fallback only. The live NSE API is tried first; this file "
                       "is used if it is unreachable. Refreshed weekly on the first "
                       "Monday run (18:00 IST).")
    _HOLIDAY_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True))
    _cache.pop(year, None)
    print(f"holidays: weekly sync — updated {year} list ({len(live)} entries)")
    return True, True, len(live)
