#!/usr/bin/env python3
"""Unusual options: fetch the session, store the rows, send the workbook.

    python run_daily.py                 # fill missing sessions, then send
    python run_daily.py --no-telegram   # build locally only
    python run_daily.py --skip-if-sent  # used by the scheduled slots
    python run_daily.py --lookback 60   # wider backfill
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date

import fetch
import store
import transform
import workbook

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "unusual_options.xlsx")
WINDOW = 60          # sessions kept in the delivered workbook


def send_document(path, caption):
    import requests

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set - nothing posted.", file=sys.stderr)
        return False
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    with open(path, "rb") as fh:
        resp = requests.post(
            url,
            data={"chat_id": chat, "caption": caption[:1024], "parse_mode": "HTML"},
            files={"document": (os.path.basename(path), fh,
                                "application/vnd.openxmlformats-officedocument."
                                "spreadsheetml.sheet")},
            timeout=180,
        )
    try:
        payload = resp.json()
    except Exception:
        payload = {}
    if resp.ok and payload.get("ok"):
        return True
    print(f"sendDocument failed: {resp.status_code} {resp.text[:300]}", file=sys.stderr)
    return False


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookback", type=int, default=15)
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--skip-if-sent", action="store_true")
    args = ap.parse_args(argv)

    for day in store.missing_sessions(args.lookback):
        rows = fetch.fetch(day)
        if not rows:
            continue
        selected = transform.select(rows)
        if not selected:
            print(f"{day}: nothing passed the filters")
            continue
        store.append(selected)
        print(f"{day}: {len(selected):,} rows stored")

    history = store.load(sessions=WINDOW)
    if not history:
        print("no history on disk - nothing to build", file=sys.stderr)
        return 1

    latest = max(r[0] for r in history)
    state = store.read_state()
    if args.skip_if_sent and state.get("sent") == latest:
        print(f"{latest}: already sent - nothing to do.")
        return 0

    path = workbook.build(history, OUT)
    today = [r for r in history if r[0] == latest]
    calls = sum(1 for r in today if r[4] == "CE")
    caption = (f"<b>Unusual options — {date.fromisoformat(latest).strftime('%d %b %Y')}</b>\n"
               f"{len(today):,} contracts · {calls:,} calls · {len(today) - calls:,} puts")
    print(f"{latest}: workbook {os.path.getsize(path) / 1e6:.1f} MB, {len(today):,} rows for the day")

    if args.no_telegram:
        print("Telegram post skipped (--no-telegram).")
        return 0

    if send_document(path, caption):
        state["sent"] = latest
        state["sent_at"] = date.today().isoformat()
        store.write_state(state)
        print("Workbook sent to Telegram.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
