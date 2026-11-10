#!/usr/bin/env python3
"""Daily pipeline: fetch bhavcopy -> store -> scan -> persist signals -> snapshot.

Usage:
    python run_daily.py                 # today's bhavcopy (walks back over holidays)
    python run_daily.py --wait          # wait for TODAY's bhavcopy, retrying every
                                        # 30 min until midnight IST
    python run_daily.py --date 2026-10-09
    python run_daily.py --no-fetch      # rescan existing DB only
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))

import requests  # noqa: E402

import config  # noqa: E402
from src.downloader import fetch_bhavcopy  # noqa: E402
from src.database import (  # noqa: E402
    init_db, store_prices, prune_prices, purge_duplicate_days,
    get_symbols, get_price_history, store_signals, set_meta, get_last_price_date,
    stale_symbols,
)
from src.signals import scan_symbol  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")
HISTORY_BARS = 300  # bars loaded per symbol for the scan


def _today_ist() -> date:
    return datetime.now(IST).date()


def _gh_out(key: str, value: str) -> None:
    """Emit a GitHub Actions step output when running inside Actions."""
    import os
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            f.write(f"{key}={value}\n")


def latest_available_bhavcopy(session: requests.Session, start: date, max_back: int = 7):
    """Return (date, df) for the most recent published bhavcopy at/behind ``start``."""
    d = start
    for _ in range(max_back):
        if d.weekday() < 5:  # skip weekends outright
            df = fetch_bhavcopy(d, session=session)
            if df is not None and not df.empty:
                return d, df
        d -= timedelta(days=1)
    return None, None


def wait_for_today(session: requests.Session, target: date,
                   deadline: tuple[int, int] = (23, 45), interval: int = 1800):
    """Block until ``target``'s bhavcopy is published, or the IST deadline passes.

    Retries every ``interval`` seconds (default 30 min) so a single dispatched run
    covers the evening: first try ~19:00, then half-hourly until midnight.
    """
    while True:
        got, df = latest_available_bhavcopy(session, target)
        if df is not None and got == target:
            return got, df
        now = datetime.now(IST)
        if (now.hour, now.minute) >= deadline:
            print(f"[run_daily] {target} still not published at the deadline "
                  f"({deadline[0]:02d}:{deadline[1]:02d} IST); giving up for tonight")
            return got, df
        print(f"[run_daily] {target} not published yet (latest {got}); "
              f"retrying in {interval // 60} min", flush=True)
        time.sleep(interval)


def load_fno() -> set:
    """Load the F&O symbol universe (for tagging signals)."""
    try:
        with open(config.FNO_FILE) as f:
            return set(json.load(f).get("stocks", []))
    except Exception as e:
        print(f"[run_daily] F&O list unavailable ({e}); is_fno will be false")
        return set()


def scan_all(params: dict, fno: set, skip: set | None = None) -> list[dict]:
    skip = skip or set()
    signals: list[dict] = []
    for sym in get_symbols():
        if sym in skip:
            continue
        df = get_price_history(sym, limit=HISTORY_BARS)
        signals.extend(scan_symbol(sym, df, params, fno))
    signals.sort(key=lambda s: (s["signal_date"], s["strength"]), reverse=True)
    return signals


def write_snapshot(signals: list[dict], params: dict, asof: str) -> Path:
    payload = {
        "generated_at": datetime.now(IST).isoformat(),
        "profile": params["PROFILE"],
        "asof": asof,
        "count": len(signals),
        "signals": signals,
    }
    out = config.OUTPUT_DIR / "daily_signals.json"
    out.write_text(json.dumps(payload, indent=2))
    return out


def write_csv(signals: list[dict]) -> Path:
    """Write the snapshot as a flat CSV (handy for scripting / downloads)."""
    import csv
    cols = ["symbol", "direction", "state", "signal_date", "price", "last_price", "pct_since",
            "rsi", "pivot1_date", "pivot1_price", "pivot1_rsi",
            "pivot2_date", "pivot2_price", "pivot2_rsi",
            "strength", "age_bars", "is_fno", "invalidated", "resolved",
            "resolution_date", "max_rsi_since", "min_rsi_since"]
    out = config.OUTPUT_DIR / "daily_signals.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for s in signals:
            row = dict(s)
            row["pct_since"] = (round((s["last_price"] - s["price"]) / s["price"] * 100, 2)
                                if s.get("price") else "")
            w.writerow(row)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="target date YYYY-MM-DD (default: today IST)")
    ap.add_argument("--no-fetch", action="store_true", help="skip download, rescan DB")
    ap.add_argument("--force", action="store_true", help="rescan even if the bhavcopy is already processed")
    ap.add_argument("--wait", action="store_true",
                    help="wait for today's bhavcopy, retrying every 30 min until midnight IST")
    args = ap.parse_args()

    init_db()
    params = config.active_params()

    asof = args.date or _today_ist().isoformat()

    snap_path = config.OUTPUT_DIR / "daily_signals.json"
    prev_asof = None
    if snap_path.exists():
        try:
            prev_asof = json.loads(snap_path.read_text()).get("asof")
        except Exception:
            prev_asof = None

    if not args.no_fetch:
        target = date.fromisoformat(asof)
        session = requests.Session()
        if args.wait:
            got, df = wait_for_today(session, target)
        else:
            got, df = latest_available_bhavcopy(session, target)
        if df is None:
            # No file within the walk-back window (e.g. exchange closed). Stay
            # graceful: the half-hourly schedule retries; we stop at midnight.
            print(f"[run_daily] No bhavcopy available at/behind {asof}; will retry.")
            _gh_out("changed", "false")
            return 0
        if got.isoformat() == prev_asof and not args.force:
            print(f"[run_daily] bhavcopy {got.isoformat()} already processed; nothing new.")
            _gh_out("changed", "false")
            return 0
        n = store_prices(df)
        dropped = purge_duplicate_days()
        pruned = prune_prices(config.RETENTION_BARS)
        asof = got.isoformat()
        print(f"[run_daily] Stored {n} rows for {asof}; dropped {dropped} stale-day row(s); "
              f"pruned {pruned} old row(s) (window={config.RETENTION_BARS} bars/symbol, "
              f"profile={params['PROFILE']})")

    fno = load_fno()
    stale = stale_symbols(config.STALE_BARS)
    if stale:
        print(f"[run_daily] skipping {len(stale)} symbol(s) with no data for "
              f">{config.STALE_BARS} candles")
    signals = scan_all(params, fno, stale)
    store_signals(signals)
    set_meta("last_run", datetime.now(IST).isoformat())
    set_meta("last_price_date", get_last_price_date() or "")
    snap = write_snapshot(signals, params, asof)
    write_csv(signals)

    print(f"[run_daily] {len(signals)} active signal(s); snapshot -> {snap}")
    for s in signals[:15]:
        print(f"   {s['symbol']:>12}  {s['direction']:<8} {s['state']:<9} {s['signal_date']}  "
              f"RSI2={s['pivot2_rsi']:.1f}  strength={s['strength']}")
    _gh_out("changed", "true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
