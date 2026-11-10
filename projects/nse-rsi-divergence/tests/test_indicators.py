"""Tests for the RSI indicator (canonical Wilder values)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src.indicators import rsi  # noqa: E402

# Standard dataset used across RSI references; the expected value is the
# canonical 14-period Wilder RSI, hand-derived from the first 14 changes.
CLOSES = [
    44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
    45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64,
    46.21, 46.25, 45.71, 46.45, 45.78, 45.35, 44.03, 44.18, 44.22, 44.57,
    43.42, 42.66, 43.13,
]


def _reference_rsi(closes, period=14):
    """Independent, naive Wilder RSI used to cross-check the module."""
    closes = [float(c) for c in closes]
    n = len(closes)
    out = [float("nan")] * n
    if n <= period:
        return out
    gains, losses = [], []
    for i in range(1, n):
        ch = closes[i] - closes[i - 1]
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))

    def rsi_of(ag, al):
        if al == 0 and ag == 0:
            return 50.0
        if al == 0:
            return 100.0
        return 100.0 - 100.0 / (1.0 + ag / al)

    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    out[period] = rsi_of(ag, al)
    for i in range(period + 1, n):
        ag = (ag * (period - 1) + gains[i - 1]) / period
        al = (al * (period - 1) + losses[i - 1]) / period
        out[i] = rsi_of(ag, al)
    return out


def test_rsi_canonical_value():
    # avg gain over first 14 changes = 3.34/14; avg loss = 1.40/14
    # RS = 2.3857 -> RSI = 100 - 100/(1+RS) = 70.46
    r = rsi(pd.Series(CLOSES), 14)
    assert abs(r.iloc[14] - 70.46) < 0.05, r.iloc[14]


def test_rsi_matches_reference_implementation():
    ref = _reference_rsi(CLOSES, 14)
    got = rsi(pd.Series(CLOSES), 14).to_numpy()
    for i in range(len(CLOSES)):
        if np.isnan(ref[i]):
            assert np.isnan(got[i])
        else:
            assert abs(ref[i] - got[i]) < 1e-9


def test_rsi_bounds_and_leading_nans():
    r = rsi(pd.Series(CLOSES), 14)
    assert r.iloc[:14].isna().all()
    assert ((r.dropna() >= 0) & (r.dropna() <= 100)).all()


def test_rsi_monotonic_edges():
    up = rsi(pd.Series(np.arange(1, 40, dtype=float)), 14)
    assert up.dropna().iloc[-1] == 100.0
    down = rsi(pd.Series(np.arange(40, 1, -1, dtype=float)), 14)
    assert down.dropna().iloc[-1] == 0.0


if __name__ == "__main__":
    test_rsi_canonical_value()
    test_rsi_matches_reference_implementation()
    test_rsi_bounds_and_leading_nans()
    test_rsi_monotonic_edges()
    print("test_indicators: OK")
