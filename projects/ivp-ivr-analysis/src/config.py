import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── IV rank / percentile window ───────────────────────────
# The rank/percentile is measured over a trailing window that INCLUDES the
# current reading. Including it keeps both metrics inside [0, 100] by
# construction — the current value cannot sit outside the window's own
# min/max. Excluding it is what let IVR exceed 100 on new highs and fall
# below 0 on new lows.
IV_WINDOW_DAYS = 365      # calendar days (~252 trading days = 1 year)
MIN_HISTORY_DAYS = 60     # don't publish a rank until this many observations
TRIM_KEEP_DAYS = 400      # retention — keep a little more than the window
YEAR_TRADING_DAYS = 252   # how many trading days we publish (the rolling year)


# ── Timezone ──────────────────────────────────────────────
# Everything user-facing is IST. The GitHub runner's clock is UTC, so "today"
# computed from the runner's local time is wrong for ~5.5 hours of every day
# (00:00–05:30 IST). Always derive dates from IST.
try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
except Exception:                                   # pragma: no cover
    IST = timezone(timedelta(hours=5, minutes=30))


def now_ist():
    """Current time in IST (tz-aware)."""
    return datetime.now(IST)


# ── Alert window (IST) ────────────────────────────────────
# The daily report is attempted from ALERT_FIRST (18:00 IST) every 30 minutes.
# The first attempt that finds the day's bhavcopy sends the full report and the
# day is closed. If nothing is found by the end of the window (midnight IST),
# a single "no data" alert is sent instead. See trading_day_for() for how a run
# is mapped to the trading day it belongs to.
ALERT_FIRST_HOUR = 18
ALERT_FIRST_MINUTE = 0
ALERT_SLOT_MINUTES = 30


def trading_day_for(now=None):
    """
    The trading day a run belongs to.

    The report window is 16:30 → 24:00 IST *of a trading day T*. A run that
    fires after midnight (00:00–07:59 IST) still belongs to the previous
    trading day — this matters because GitHub's scheduler frequently delivers
    the late slots after midnight. Weekends roll back to the previous Friday.
    """
    now = now or now_ist()
    d = now.date()
    if now.hour < 8:            # before the market day has started
        d -= timedelta(days=1)
    while d.weekday() >= 5:     # Saturday(5) / Sunday(6) → back to Friday
        d -= timedelta(days=1)
    return d


def window_closed(now=None):
    """
    True once the calendar has moved past the trading day a run belongs to —
    i.e. the 16:30→24:00 window for that day is over. Delay-tolerant: it does
    not depend on any particular slot actually having run on time.
    """
    now = now or now_ist()
    return now.date() > trading_day_for(now)


# ── Persistent run state ──────────────────────────────────
# GitHub runners start empty, so "already sent today" has to live in the repo.
# data/state.json is committed by the workflow alongside data/daily/*.json.
STATE_PATH = Path(__file__).resolve().parent.parent / "data" / "state.json"


def load_config():
    """Load configuration from config/fno_stocks.json"""
    config_path = Path(__file__).parent.parent / "config" / "fno_stocks.json"
    with open(config_path, 'r') as f:
        return json.load(f)


def get_project_root():
    """Get the project root directory"""
    return Path(__file__).parent.parent
