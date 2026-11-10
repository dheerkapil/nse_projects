#!/usr/bin/env python3
"""Render the daily signal snapshot as a Markdown table for the GitHub Actions
run summary ($GITHUB_STEP_SUMMARY). Symbols link to their TradingView chart.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAP = ROOT / "output" / "daily_signals.json"


def _num(v, fmt="{:.2f}"):
    try:
        return fmt.format(float(v))
    except (TypeError, ValueError):
        return "—"


def main() -> int:
    if not SNAP.exists():
        print("_No signal snapshot found._")
        return 0

    d = json.loads(SNAP.read_text())
    sigs = d.get("signals", [])

    print(f"## NSE RSI-divergence signals — {d.get('asof', '?')}")
    print()
    print(f"**Profile:** `{d.get('profile', '?')}` · **Active signals:** {len(sigs)}")
    print()

    if not sigs:
        print("_No active signals._")
        return 0

    sigs = sorted(sigs, key=lambda s: (s.get("signal_date", ""), s.get("strength", 0)), reverse=True)
    print("| Symbol | Dir | State | Signal date | Entry (₹) | Last (₹) | % chg | RSI₂ | Strength | Age |")
    print("|---|---|---|---|---:|---:|---:|---:|---:|---:|")
    for s in sigs:
        sym = s.get("symbol", "?")
        link = f"[{sym}](https://www.tradingview.com/chart/?symbol=NSE:{sym})"
        entry, last = s.get("price"), s.get("last_price")
        try:
            pct = (float(last) - float(entry)) / float(entry) * 100.0
            pct_s = f"{pct:+.1f}%"
        except (TypeError, ValueError, ZeroDivisionError):
            pct_s = "—"
        age = s.get("age_bars")
        print(
            f"| {link} | {s.get('direction', '—')} | {s.get('state', 'confirmed')} | {s.get('signal_date', '—')} | {_num(entry)} | {_num(last)} | "
            f"{pct_s} | {_num(s.get('pivot2_rsi'), '{:.1f}')} | "
            f"{_num(s.get('strength'), '{:.0f}')} | {age if age is not None else '—'}d |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
