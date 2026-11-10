"""Tiny persistent run-state store.

GitHub Actions runners are ephemeral: every run checks out the repo fresh, so
the only way to remember "the report for 2026-10-19 has already been sent" is
to keep it in a file that gets committed. data/state.json does that job, next
to the per-day reading files.

Shape:
    {
      "sent":              {"2026-10-19": "2026-10-19T18:47:12+05:30"},
      "failed":            {"2026-10-17": "2026-10-18T00:05:31+05:30"},
      "holiday_notified":  {"2026-10-20": "2026-10-20T18:01:09+05:30"},
      "holiday_sync_week": [2026, 43],
      "holiday_sync_at":   "2026-10-19T18:03:44+05:30"
    }
"""

import json

from src.config import STATE_PATH


def load_state():
    try:
        return json.loads(STATE_PATH.read_text())
    except FileNotFoundError:
        return {}
    except Exception as e:                       # corrupt file → start clean
        print(f"state: could not read {STATE_PATH} ({e}); starting fresh")
        return {}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))


# ── daily report ──────────────────────────────────────────
def already_sent(date_str):
    return date_str in load_state().get("sent", {})


def mark_sent(date_str, when):
    state = load_state()
    state.setdefault("sent", {})[date_str] = when
    save_state(state)


def already_failed(date_str):
    return date_str in load_state().get("failed", {})


def mark_failed(date_str, when):
    state = load_state()
    state.setdefault("failed", {})[date_str] = when
    save_state(state)


# ── holiday notice ────────────────────────────────────────
def holiday_notified(date_str):
    return date_str in load_state().get("holiday_notified", {})


def mark_holiday_notified(date_str, when):
    state = load_state()
    state.setdefault("holiday_notified", {})[date_str] = when
    save_state(state)


# ── weekly holiday-list sync ──────────────────────────────
def get_holiday_sync_week():
    """The [iso_year, iso_week] the holiday list was last refreshed in."""
    return load_state().get("holiday_sync_week")


def set_holiday_sync_week(week_key, when):
    state = load_state()
    state["holiday_sync_week"] = list(week_key)
    state["holiday_sync_at"] = when
    save_state(state)
