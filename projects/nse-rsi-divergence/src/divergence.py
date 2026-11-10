"""RSI-divergence scanning on settled closes (bullish and bearish).

A low/high only counts once it has **turned**: the close is lower (higher) than
the previous bar AND the next close is higher (lower). Until it turns it is just
the running extreme and is never shown — a low that can still be taken out is not
a low yet. A regular divergence is between two consecutive *turned* lows/highs:
price lower (higher) with RSI higher (lower).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.indicators import ema, atr


def _atr_series(df: pd.DataFrame, params: dict):
    """ATR array if an ATR-based confirmation is enabled, else None."""
    if not (params.get("ATR_MULT") or 0.0):
        return None
    if not {"high", "low", "prev_close"}.issubset(df.columns):
        return None
    return atr(df["high"], df["low"], df["prev_close"],
               params.get("ATR_PERIOD", 14)).to_numpy(dtype=float)


def _bounced(closes: np.ndarray, atr_vals, b: int, mult: float, bullish: bool) -> bool:
    """True if the close moved ``mult`` x ATR off ``b`` *before* making a lower/higher close."""
    if atr_vals is None or mult <= 0 or np.isnan(atr_vals[b]):
        return False
    need = mult * atr_vals[b]
    for t in range(b + 1, len(closes)):
        if bullish:
            if closes[t] >= closes[b] + need:
                return True
            if closes[t] < closes[b]:      # a lower close kills the bounce
                return False
        else:
            if closes[t] <= closes[b] - need:
                return True
            if closes[t] > closes[b]:
                return False
    return False


def _find_pivots(values: np.ndarray, order: int, kind: str) -> list[int]:
    n = len(values)
    out: list[int] = []
    for i in range(order, n - order):
        window = values[i - order : i + order + 1]
        if np.isnan(window).any():
            continue
        v = values[i]
        if kind == "low":
            if v == window.min() and int((window == v).sum()) == 1:
                out.append(i)
        else:
            if v == window.max() and int((window == v).sum()) == 1:
                out.append(i)
    return out


def find_pivot_lows(values: np.ndarray, order: int) -> list[int]:
    """Indices that are the unique lowest bar within ``order`` bars either side."""
    return _find_pivots(values, order, "low")


def find_pivot_highs(values: np.ndarray, order: int) -> list[int]:
    """Indices that are the unique highest bar within ``order`` bars either side."""
    return _find_pivots(values, order, "high")


def _turned_lows(series: np.ndarray) -> list[int]:
    """Bars whose close is lower than the previous bar and the next close is higher."""
    return [i for i in range(1, len(series) - 1)
            if series[i] < series[i - 1] and series[i] < series[i + 1]]


def _turned_highs(series: np.ndarray) -> list[int]:
    """Bars whose close is higher than the previous bar and the next close is lower."""
    return [i for i in range(1, len(series) - 1)
            if series[i] > series[i - 1] and series[i] > series[i + 1]]


def detect_divergence(df: pd.DataFrame, rsi: pd.Series, params: dict,
                      direction: str = "bullish") -> list[dict]:
    """Scan one symbol's history for regular divergences of the given direction.

    ``df``: columns date, high, low, close (ascending). ``rsi`` aligned to it.
    Pivots are turned closes; the latest pivot only counts once it has turned.
    Returns one candidate per consecutive turned pair that diverges.
    """
    order = params["PIVOT_ORDER"]
    lookback = params["LOOKBACK_BARS"]
    min_sep = params["MIN_PIVOT_SEPARATION"]

    closes = df["close"].to_numpy(dtype=float)
    dates = df["date"].to_numpy()
    r = rsi.to_numpy(dtype=float)
    n = len(df)
    if n < max(params["MIN_HISTORY_BARS"], order * 2 + 2):
        return []

    bullish = direction == "bullish"
    basis = params.get("PIVOT_BASIS", "close")
    series = closes if basis == "close" else (
        df["low"].to_numpy(dtype=float) if bullish else df["high"].to_numpy(dtype=float))

    turns = _turned_lows(series) if bullish else _turned_highs(series)
    start = max(1, n - lookback - order)
    turns = [t for t in turns if t >= start]
    if len(turns) < 2:
        return []

    gate = params["DOWNTURN_GATE"] if bullish else params.get("UPTREND_GATE", params["DOWNTURN_GATE"])
    ema_vals = ema(closes, params["DOWNTURN_EMA_SPAN"]).to_numpy() if gate else None
    flat = params.get("FLAT_TOL_PCT", 0.0) / 100.0   # flat top/bottom allowance
    rsi_delta = params["MIN_RSI_RISE"]
    atr_vals = _atr_series(df, params)
    mult = params.get("ATR_MULT", 0.0) or 0.0

    candidates: list[dict] = []
    for a, b in zip(turns[:-1], turns[1:]):
        if b - a < min_sep:
            continue
        if np.isnan(r[a]) or np.isnan(r[b]):
            continue
        if bullish:
            if not (series[b] <= series[a] * (1.0 + flat)):  # lower close (or flat)
                continue
            if not (r[b] > r[a] + rsi_delta):                # higher RSI low
                continue
            if not (r[b] < params["RSI_CEILING"]):
                continue
        else:
            if not (series[b] >= series[a] * (1.0 - flat)):  # higher close (or flat)
                continue
            if not (r[b] < r[a] - rsi_delta):                # lower RSI high
                continue
            if not (r[b] > params.get("RSI_FLOOR", 50.0)):
                continue
        if gate and ema_vals is not None:
            lb = params["DOWNTURN_SLOPE_BARS"]
            if b - lb < 0:
                continue
            if bullish:
                if not (closes[b] < ema_vals[b] and ema_vals[b] < ema_vals[b - lb]):
                    continue
            else:
                if not (closes[b] > ema_vals[b] and ema_vals[b] > ema_vals[b - lb]):
                    continue
        conf = b + 1                    # the turn is known on the bar after the low
        # confirmed once the low has settled (order bars behind it) OR the close
        # has moved ATR_MULT x ATR off it — whichever comes first. Else forming.
        settled = (n - 1 - b) >= order
        state = "confirmed" if (settled or _bounced(closes, atr_vals, b, mult, bullish)) else "forming"
        candidates.append({
            "symbol": None,
            "direction": direction,
            "state": state,
            "signal_date": str(dates[conf]),
            "price": float(closes[conf]),
            "rsi": float(r[conf]),
            "pivot1_date": str(dates[a]), "pivot1_price": float(series[a]), "pivot1_rsi": float(r[a]),
            "pivot2_date": str(dates[b]), "pivot2_price": float(series[b]), "pivot2_rsi": float(r[b]),
            "sep": int(b - a),
            "conf_idx": int(conf),
        })
    return candidates
