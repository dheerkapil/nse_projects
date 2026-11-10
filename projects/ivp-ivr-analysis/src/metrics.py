import pandas as pd
import numpy as np

from src.config import MIN_HISTORY_DAYS

def calculate_ivr(current_iv, historical_ivs):
    """
    Calculate IV Rank: (Current - Low) / (High - Low) * 100
    """
    if len(historical_ivs) == 0:
        return 50.0
    
    high = max(historical_ivs)
    low = min(historical_ivs)
    
    if high == low:
        return 50.0
    
    return ((current_iv - low) / (high - low)) * 100

def calculate_ivp(current_iv, historical_ivs):
    """
    Calculate IV Percentile: (% of days IV was below current)
    """
    if len(historical_ivs) == 0:
        return 50.0
    
    count_below = sum(1 for iv in historical_ivs if iv < current_iv)
    total = len(historical_ivs)
    
    return (count_below / total) * 100

def compute_iv_rank_percentile(current_iv, window_ivs):
    """
    IV Rank and IV Percentile for the current reading, computed over a window
    that INCLUDES the current reading.

    Why the current reading must be in the window: IVR normalises against the
    window's own high/low. If the window holds only *prior* observations, a day
    that sets a new high pushes the ratio past 1 (IVR > 100) and a new low drops
    it below 0. Including the current value makes the result bounded to
    [0, 100] by construction — no clamping required.

    A rank built on a handful of observations is noise, so when the window holds
    fewer than MIN_HISTORY_DAYS values we return (None, None) rather than publish
    a misleading number.

    Returns (ivr, ivp), each rounded to 1 dp, or (None, None).
    """
    obs = [v for v in window_ivs if v is not None]
    if len(obs) < MIN_HISTORY_DAYS:
        return None, None

    high, low = max(obs), min(obs)
    if high == low:
        ivr = 50.0
    else:
        ivr = (current_iv - low) / (high - low) * 100.0

    below = sum(1 for v in obs if v < current_iv)
    ivp = below / len(obs) * 100.0

    return round(ivr, 1), round(ivp, 1)

def get_high_ivp_stocks(metrics, threshold=80):
    """Get stocks with IVP above threshold"""
    return [s for s in metrics if s['ivp'] >= threshold]

def get_low_ivp_stocks(metrics, threshold=20):
    """Get stocks with IVP below threshold"""
    return [s for s in metrics if s['ivp'] <= threshold]
