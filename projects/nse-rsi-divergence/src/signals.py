"""Turn raw divergences into scored, filtered signals (bullish and bearish).

Two states, both requiring the second pivot to have *turned*:
  * ``forming``   — the turn is fresh (the low is younger than ``PIVOT_ORDER`` bars).
  * ``confirmed`` — the low has ``PIVOT_ORDER`` bars settled behind it.

``resolved`` marks a setup that has done its job: RSI closed past the resolve
level on some bar since the signal (bullish > 60, bearish < 40).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config
from src.indicators import rsi
from src.divergence import detect_divergence

DIRECTIONS = ("bullish", "bearish")


def score(cand: dict, params: dict) -> float:
    """0–100 strength score (direction-aware).

    Components: RSI delta (40), depth of the price move (20),
    RSI level at the second pivot (25), pivot separation (15).
    """
    delta = abs(cand["pivot2_rsi"] - cand["pivot1_rsi"])
    p1, p2 = cand["pivot1_price"], cand["pivot2_price"]
    move_pct = abs(p1 - p2) / p1 * 100.0 if p1 else 0.0
    if cand["direction"] == "bullish":
        ceil = max(params["RSI_CEILING"], 1e-9)
        c_level = max(0.0, min((ceil - cand["pivot2_rsi"]) / ceil, 1.0)) * 25.0
    else:
        floor = params.get("RSI_FLOOR", 50.0)
        c_level = max(0.0, min((cand["pivot2_rsi"] - floor) / max(100.0 - floor, 1e-9), 1.0)) * 25.0
    c_rsi = min(delta / 15.0, 1.0) * 40.0
    c_move = min(move_pct / 10.0, 1.0) * 20.0
    c_sep = min(cand["sep"] / 20.0, 1.0) * 15.0
    return round(c_rsi + c_move + c_level + c_sep, 1)


def _finalize(cand: dict, symbol: str, df: pd.DataFrame, params: dict,
              fno: set | None, last_close: float, r: pd.Series) -> dict:
    cand["symbol"] = symbol
    cand["strength"] = score(cand, params)
    cand["profile"] = params["PROFILE"]
    cand["last_price"] = last_close
    cand["last_date"] = str(df["date"].iloc[-1])
    cand["age_bars"] = int(len(df) - 1 - cand["conf_idx"])
    cand["is_fno"] = bool(fno and symbol in fno)
    cand.setdefault("state", "confirmed")
    # invalidated if EITHER price OR RSI closes beyond the level set at the second
    # pivot, on any bar after it (closes only). Either break kills the divergence.
    after_c = df["close"].iloc[cand["conf_idx"] + 1:]
    after_r = r.iloc[cand["conf_idx"] + 1:]
    if cand["direction"] == "bullish":
        cand["invalidated"] = bool((after_c < cand["pivot2_price"]).any()
                                   or (after_r < cand["pivot2_rsi"]).any())
    else:
        cand["invalidated"] = bool((after_c > cand["pivot2_price"]).any()
                                   or (after_r > cand["pivot2_rsi"]).any())
    # resolved = the divergence has done its job: RSI closed past the level on any
    # bar since the signal (bullish > 60, bearish < 40), EOD closes only.
    r_since = r.iloc[cand["conf_idx"]:]
    thr = params.get("RESOLVE_RSI_BULL", 60.0) if cand["direction"] == "bullish" \
        else params.get("RESOLVE_RSI_BEAR", 40.0)
    hit = (r_since > thr) if cand["direction"] == "bullish" else (r_since < thr)
    cand["resolved"] = bool(hit.any())
    if cand["resolved"]:
        pos = int(np.argmax(hit.to_numpy()))
        cand["resolution_date"] = str(df["date"].iloc[cand["conf_idx"] + pos])
    else:
        cand["resolution_date"] = ""
    cand["max_rsi_since"] = round(float(r_since.max()), 1) if len(r_since) else None
    cand["min_rsi_since"] = round(float(r_since.min()), 1) if len(r_since) else None
    return cand


def scan_symbol(symbol: str, df: pd.DataFrame, params: dict, fno: set | None = None) -> list[dict]:
    """Return the symbol's confirmed and/or forming signals (0-4 items)."""
    if df is None or len(df) < params["MIN_HISTORY_BARS"]:
        return []

    last_close = float(df["close"].iloc[-1])
    if last_close < params["MIN_PRICE"]:
        return []

    if params.get("MIN_AVG_TURNOVER_LACS"):
        avg_turn = pd.to_numeric(df["turnover_lacs"], errors="coerce").tail(20).mean()
        if pd.notna(avg_turn) and avg_turn < params["MIN_AVG_TURNOVER_LACS"]:
            return []

    if params["GAP_GUARD_ENABLED"]:
        chg = df["close"].pct_change().abs()
        if (chg > params["GAP_GUARD_PCT"] / 100.0).any():
            return []

    r = rsi(df["close"], params["RSI_PERIOD"])

    out: list[dict] = []
    for direction in DIRECTIONS:
        cands = detect_divergence(df, r, params, direction)
        if not cands:
            continue
        conf = [c for c in cands if c["state"] == "confirmed"]
        form = [c for c in cands if c["state"] == "forming"]
        if conf:
            out.append(_finalize(max(conf, key=lambda c: c["conf_idx"]),
                                 symbol, df, params, fno, last_close, r))
        if form:
            out.append(_finalize(max(form, key=lambda c: c["conf_idx"]),
                                 symbol, df, params, fno, last_close, r))
    return out
