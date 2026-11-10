"""Technical indicators. Wilder's RSI, on daily closes."""
from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's Relative Strength Index (canonical implementation).

    Seeded with the simple average of the first ``period`` gains/losses, then
    smoothed with Wilder's recursion. Matches the standard StockCharts values.
    Leading values are NaN until ``period`` observations are available.
    """
    close = pd.Series(close).astype(float)
    n = len(close)
    out = pd.Series(np.nan, index=close.index, dtype=float)
    if n <= period:
        return out

    delta = close.diff()
    gain = delta.clip(lower=0.0).to_numpy()
    loss = (-delta).clip(lower=0.0).to_numpy()

    avg_gain = np.full(n, np.nan)
    avg_loss = np.full(n, np.nan)
    avg_gain[period] = np.nanmean(gain[1:period + 1])
    avg_loss[period] = np.nanmean(loss[1:period + 1])

    for i in range(period + 1, n):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gain[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + loss[i]) / period

    for i in range(period, n):
        ag, al = avg_gain[i], avg_loss[i]
        if al == 0 and ag == 0:
            out.iloc[i] = 50.0
        elif al == 0:
            out.iloc[i] = 100.0
        else:
            rs = ag / al
            out.iloc[i] = 100.0 - (100.0 / (1.0 + rs))
    return out


def ema(series, span: int) -> pd.Series:
    return pd.Series(series).astype(float).ewm(span=span, adjust=False).mean()


def atr(high, low, prev_close, period: int = 14) -> pd.Series:
    """Wilder's Average True Range on daily bars.

    TR = max(high-low, |high-prev_close|, |low-prev_close|), smoothed with Wilder's
    recursion (seeded with the simple average of the first ``period`` TRs).
    """
    high = pd.Series(high).astype(float)
    low = pd.Series(low).astype(float)
    prev_close = pd.Series(prev_close).astype(float)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    n = len(tr)
    out = pd.Series(np.nan, index=tr.index, dtype=float)
    if n < period:
        return out
    out.iloc[period - 1] = tr.iloc[:period].mean()
    for i in range(period, n):
        out.iloc[i] = (out.iloc[i - 1] * (period - 1) + tr.iloc[i]) / period
    return out
