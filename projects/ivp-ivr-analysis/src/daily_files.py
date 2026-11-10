"""
Per-day reading files:  data/daily/<date>.json

Design note
-----------
Each trading day gets its OWN file, written once and never rewritten. That way
git stores every day exactly once, so the repo grows by the size of the data
(roughly 25 KB/day, ~6 MB/year) and never by duplicated history.

These files are the durable backup AND the source of truth for rebuilding the
SQLite database on a fresh CI runner (which starts empty every time).
"""

import json
import sqlite3
from pathlib import Path

from src.config import YEAR_TRADING_DAYS

ROOT = Path(__file__).resolve().parent.parent
DAILY_DIR = ROOT / "data" / "daily"
DB_PATH = ROOT / "data" / "iv_history.db"


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _hist_counts(conn):
    """{symbol: number of distinct dates} for the hist_days field."""
    rows = conn.execute(
        "SELECT symbol, COUNT(DISTINCT date) FROM daily_iv GROUP BY symbol"
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def export_date(date, conn=None, hist=None):
    """Write data/daily/<date>.json for one date. Returns number of stocks written."""
    owns = conn is None
    if conn is None:
        conn = _connect()
    if hist is None:
        hist = _hist_counts(conn)

    rows = conn.execute(
        """SELECT symbol, current_iv, iv_rank, iv_percentile
           FROM daily_metrics WHERE date = ? ORDER BY symbol""",
        (date,),
    ).fetchall()

    if rows:
        stocks = [
            {
                "symbol": r["symbol"],
                "iv": round(r["current_iv"], 1) if r["current_iv"] is not None else None,
                "ivr": round(r["iv_rank"], 1) if r["iv_rank"] is not None else None,
                "ivp": round(r["iv_percentile"], 1) if r["iv_percentile"] is not None else None,
                "hist_days": hist.get(r["symbol"], 0),
            }
            for r in rows
        ]
    else:
        # No metrics computed for this day – fall back to raw IV readings.
        ivs = conn.execute(
            "SELECT symbol, iv FROM daily_iv WHERE date = ? ORDER BY symbol", (date,)
        ).fetchall()
        if not ivs:
            if owns:
                conn.close()
            return 0
        stocks = [
            {
                "symbol": r["symbol"],
                "iv": round(r["iv"], 1) if r["iv"] is not None else None,
                "ivr": None,
                "ivp": None,
                "hist_days": hist.get(r["symbol"], 0),
            }
            for r in ivs
        ]

    if owns:
        conn.close()

    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"date": date, "stocks": stocks}
    (DAILY_DIR / f"{date}.json").write_text(
        json.dumps(payload, separators=(",", ":"))
    )
    return len(stocks)


def export_all(keep_last=None):
    """Export dates present in the DB to their own files.

    keep_last=N publishes only the most recent N trading days — used after a
    backfill that deliberately collected extra warm-up days (needed to compute
    a rank) but should only publish the rolling year.
    """
    conn = _connect()
    dates = [r[0] for r in conn.execute("SELECT DISTINCT date FROM daily_iv ORDER BY date")]
    if keep_last:
        dates = dates[-keep_last:]
    hist = _hist_counts(conn)
    total = 0
    for d in dates:
        total += export_date(d, conn=conn, hist=hist)
    conn.close()
    print(f"Exported {len(dates)} day files ({total} stock-rows) to {DAILY_DIR}")
    return len(dates)


def prune_files(keep_last=YEAR_TRADING_DAYS):
    """Delete per-day files older than the most recent `keep_last` days.

    Keeps data/daily a true rolling year instead of letting it grow forever.
    """
    files = sorted(DAILY_DIR.glob("*.json"))
    stale = files[:-keep_last] if keep_last else []
    for f in stale:
        f.unlink()
    if stale:
        print(f"pruned {len(stale)} file(s) older than the last {keep_last} days")
    return len(stale)


def latest_date():
    conn = _connect()
    row = conn.execute("SELECT MAX(date) FROM daily_iv").fetchone()
    conn.close()
    return row[0] if row and row[0] else None


def bootstrap_from_files():
    """
    Rebuild daily_iv + daily_metrics from data/daily/*.json.

    The per-day files are the source of truth; the SQLite DB is a scratch store
    that a fresh runner starts without. If no files exist yet we leave the DB
    untouched (so the committed DB still acts as a fallback).
    """
    files = sorted(DAILY_DIR.glob("*.json"))
    if not files:
        print("bootstrap: no per-day files found – leaving DB as-is")
        return 0

    iv_rows, metric_rows = [], []
    for f in files:
        try:
            payload = json.loads(f.read_text())
        except Exception as e:
            print(f"bootstrap: skipping {f.name}: {e}")
            continue
        date = payload.get("date") or f.stem
        for s in payload.get("stocks", []):
            sym, iv = s.get("symbol"), s.get("iv")
            if not sym or iv is None:
                continue
            iv_rows.append((date, sym, float(iv), 0.0, "", 0.0, "CE"))
            if s.get("ivr") is not None and s.get("ivp") is not None:
                metric_rows.append(
                    (date, sym, float(s["ivr"]), float(s["ivp"]), float(iv))
                )

    conn = _connect()
    conn.execute("DELETE FROM daily_iv")
    conn.execute("DELETE FROM daily_metrics")
    conn.executemany(
        """INSERT OR REPLACE INTO daily_iv
           (date, symbol, iv, spot, expiry, strike, option_type)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        iv_rows,
    )
    conn.executemany(
        """INSERT OR REPLACE INTO daily_metrics
           (date, symbol, iv_rank, iv_percentile, current_iv)
           VALUES (?, ?, ?, ?, ?)""",
        metric_rows,
    )
    conn.commit()
    conn.close()
    print(
        f"bootstrap: loaded {len(files)} files -> "
        f"{len(iv_rows)} IV rows, {len(metric_rows)} metric rows"
    )
    return len(files)
