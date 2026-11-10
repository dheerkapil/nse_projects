"""Tests for fractal pivots and regular bullish-divergence detection."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src.divergence import find_pivot_lows, detect_divergence  # noqa: E402


def _params(**over):
    p = dict(
        PIVOT_ORDER=3, MIN_PIVOT_SEPARATION=5, LOOKBACK_BARS=120,
        MIN_HISTORY_BARS=20, MIN_PRICE_DROP_PCT=0.0, MIN_RSI_RISE=1.0,
        RSI_CEILING=55.0, RSI_FLOOR=45.0, DOWNTURN_GATE=False, UPTREND_GATE=False,
        DOWNTURN_EMA_SPAN=50, DOWNTURN_SLOPE_BARS=10, PIVOT_BASIS="close", PROFILE="loose",
    )
    p.update(over)
    return p


def test_find_pivot_lows():
    vals = np.array([10, 9, 8, 7, 6, 5, 6, 7, 8, 9, 10, 9, 8, 7, 6, 5, 4, 5, 6, 7, 8], dtype=float)
    piv = find_pivot_lows(vals, order=3)
    assert 5 in piv and 16 in piv, piv


def test_bullish_divergence_detected():
    n = 40
    lows = np.full(n, 120.0)
    lows[7:14] = [118, 114, 110, 100, 110, 114, 118]      # pivot low = 100 @ idx 10
    lows[22:29] = [114, 110, 106, 95, 106, 110, 114]      # lower low = 95  @ idx 25
    closes = lows + 5
    rsi_vals = np.full(n, 50.0)
    rsi_vals[10] = 30.0                                    # RSI low
    rsi_vals[25] = 40.0                                    # higher RSI low

    df = pd.DataFrame({
        "date": [f"2026-01-{i+1:02d}" for i in range(n)],
        "open": closes, "high": closes + 1, "low": lows, "close": closes,
    })
    cands = detect_divergence(df, pd.Series(rsi_vals), _params())
    assert len(cands) == 1, cands
    c = cands[0]
    # pivots are detected on the CLOSE series by default, and closes = lows + 5
    assert c["pivot1_price"] == 105.0 and c["pivot2_price"] == 100.0
    assert c["pivot1_rsi"] == 30.0 and c["pivot2_rsi"] == 40.0


def test_no_divergence_when_rsi_confirms():
    """Price lower low AND RSI lower low is NOT bullish divergence."""
    n = 40
    lows = np.full(n, 120.0)
    lows[7:14] = [118, 114, 110, 100, 110, 114, 118]
    lows[22:29] = [114, 110, 106, 95, 106, 110, 114]
    closes = lows + 5
    rsi_vals = np.full(n, 50.0)
    rsi_vals[10] = 40.0
    rsi_vals[25] = 30.0                                   # RSI lower low -> no signal
    df = pd.DataFrame({
        "date": [f"2026-01-{i+1:02d}" for i in range(n)],
        "open": closes, "high": closes + 1, "low": lows, "close": closes,
    })
    assert detect_divergence(df, pd.Series(rsi_vals), _params()) == []


def test_separation_filter():
    """Two lows too close together must be rejected."""
    n = 40
    lows = np.full(n, 120.0)
    lows[7:14] = [118, 114, 110, 100, 110, 114, 118]      # idx 10
    lows[11:18] = [114, 110, 106, 95, 106, 110, 114]      # idx 14, only 4 bars later
    closes = lows + 5
    rsi_vals = np.full(n, 50.0)
    rsi_vals[10] = 30.0
    rsi_vals[14] = 40.0
    df = pd.DataFrame({
        "date": [f"2026-01-{i+1:02d}" for i in range(n)],
        "open": closes, "high": closes + 1, "low": lows, "close": closes,
    })
    # min separation 5 -> reject; min separation 3 -> accept
    assert detect_divergence(df, pd.Series(rsi_vals), _params(MIN_PIVOT_SEPARATION=5)) == []
    assert len(detect_divergence(df, pd.Series(rsi_vals), _params(MIN_PIVOT_SEPARATION=3))) == 1


if __name__ == "__main__":
    test_find_pivot_lows()
    test_bullish_divergence_detected()
    test_no_divergence_when_rsi_confirms()
    test_separation_filter()
    print("test_divergence: OK")
