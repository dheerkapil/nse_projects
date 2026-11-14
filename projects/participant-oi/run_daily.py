#!/usr/bin/env python3
"""Daily participant-wise open interest: fetch, append, deliver the workbook.

Replaces the manual loop in derivatives_data_longerterm_new_site.xlsm: download
NSE's fao_participant_oi_<DDMMYYYY>.csv, append it, rebuild the analysis
workbook and send it to Telegram as a document.

    python run_daily.py                 # fill any missing sessions, then send
    python run_daily.py --no-telegram   # build the file locally only
    python run_daily.py --date 2026-11-12
    python run_daily.py --skip-if-sent  # used by the scheduled slots
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date

import fetch
import store
import workbook


def send_document(path, caption):
    import requests

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set - nothing posted.",
              file=sys.stderr)
        return False

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    with open(path, "rb") as fh:
        resp = requests.post(
            url,
            data={"chat_id": chat, "caption": caption[:1024], "parse_mode": "HTML"},
            files={"document": (os.path.basename(path), fh,
                                "application/vnd.openxmlformats-officedocument."
                                "spreadsheetml.sheet")},
            timeout=120,
        )
    try:
        payload = resp.json()
    except Exception:
        payload = {}
    if resp.ok and payload.get("ok"):
        return True
    print(f"sendDocument failed: {resp.status_code} {resp.text[:300]}", file=sys.stderr)
    return False


def caption_for(history, closes, target):
    stamp = date.fromisoformat(target).strftime("%d %b %Y")
    parts = [f"<b>Participant OI — {stamp}</b>"]
    close = closes.get(target)
    if close is not None:
        earlier = [d for d in sorted(closes) if d < target]
        if earlier:
            prev = closes[earlier[-1]]
            parts.append(f"Nifty {close:,.2f} ({close - prev:+,.2f}, "
                         f"{(close - prev) / prev * 100:+.2f}%)")
        else:
            parts.append(f"Nifty {close:,.2f}")

    row = history.get(target, {})
    fii = row.get("FII")
    if fii:
        net = fii["Future Index Long"] - fii["Future Index Short"]
        gross = fii["Future Index Long"] + fii["Future Index Short"]
        share = (fii["Future Index Long"] / gross * 100) if gross else 0
        parts.append(f"FII index fut net {net:+,} (long {share:.0f}%)")
    return "\n".join(parts)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookback", type=int, default=15,
                    help="how many days back to look for missing sessions")
    ap.add_argument("--date", help="report this date only (YYYY-MM-DD)")
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--skip-if-sent", action="store_true",
                    help="do nothing if this date has already been sent")
    args = ap.parse_args(argv)

    wanted = ([date.fromisoformat(args.date)] if args.date
              else store.missing_sessions(args.lookback))

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
    path = workbook.build(history, closes)
    caption = caption_for(history, closes, target)
    print(f"{target}: workbook written to {path} ({path.stat().st_size / 1024:.0f} KB), "
          f"{added} rows added")
    print(caption.replace("<b>", "").replace("</b>", ""))

    if args.no_telegram:
        print("Telegram post skipped (--no-telegram).")
        return 0

    if send_document(path, caption):
        state["sent"] = target
        state["sent_at"] = date.today().isoformat()
        store.write_state(state)
        print("Workbook sent to Telegram.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
