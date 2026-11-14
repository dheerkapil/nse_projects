#!/usr/bin/env python3
"""Daily participant-wise open interest: fetch, append, report to Telegram.

Replaces the manual loop in derivatives_data_longerterm_new_site.xlsm: download
NSE's fao_participant_oi_<DDMMYYYY>.csv, append it, recompute the positioning
views and post a summary plus a chart.

    python run_daily.py                 # fill any missing sessions, then report
    python run_daily.py --no-telegram   # fetch + report to stdout only
    python run_daily.py --date 2026-11-12
    python run_daily.py --skip-if-sent  # used by the scheduled slots
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date

import fetch
import report
import store


def send_telegram(text, photo=None):
    import requests

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set - nothing posted.",
              file=sys.stderr)
        return False

    base = f"https://api.telegram.org/bot{token}"
    if photo:
        with open(photo, "rb") as fh:
            resp = requests.post(
                f"{base}/sendPhoto",
                data={"chat_id": chat, "caption": text[:1024], "parse_mode": "HTML"},
                files={"photo": fh}, timeout=60)
        if resp.ok and resp.json().get("ok"):
            return True
        print(f"sendPhoto failed: {resp.status_code} {resp.text[:200]}",
              file=sys.stderr)
        # fall through to a text-only message so the numbers still arrive

    resp = requests.post(
        f"{base}/sendMessage",
        data={"chat_id": chat, "text": text[:4096], "parse_mode": "HTML"},
        timeout=60)
    if resp.ok and resp.json().get("ok"):
        return True
    print(f"sendMessage failed: {resp.status_code} {resp.text[:200]}", file=sys.stderr)
    return False


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookback", type=int, default=15,
                    help="how many days back to look for missing sessions")
    ap.add_argument("--date", help="report this date only (YYYY-MM-DD)")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--skip-if-sent", action="store_true",
                    help="do nothing if this date has already been sent")
    args = ap.parse_args(argv)

    if args.date:
        wanted = [date.fromisoformat(args.date)]
    else:
        wanted = store.missing_sessions(args.lookback)

    added = 0
    for day in wanted:
        rows = fetch.fetch(day)
        if rows:
            added += store.append(rows)
            print(f"{day}: {len(rows)} client rows stored")
        else:
            print(f"{day}: not published yet")

    history = store.load()
    if not history:
        print("no history on disk - nothing to report", file=sys.stderr)
        return 1

    target = args.date or max(history)
    if target not in history:
        print(f"{target}: no data for that session", file=sys.stderr)
        return 1

    state = store.read_state()
    if args.skip_if_sent and state.get("sent") == target:
        print(f"{target}: already sent - nothing to do.")
        return 0

    closes = store.nifty_closes()
    text = report.build_text(history, target, closes)
    print("\n" + text.replace("<b>", "").replace("</b>", "")
          .replace("<i>", "").replace("</i>", "") + "\n")

    if args.no_telegram:
        print(f"rows added: {added}; Telegram post skipped (--no-telegram).")
        return 0

    chart = report.build_chart(history, closes)
    if send_telegram(text, chart):
        state["sent"] = target
        state["sent_at"] = date.today().isoformat()
        store.write_state(state)
        print("Telegram post sent.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
