"""Turn the raw participant-OI rows into the numbers the report needs."""

from __future__ import annotations

from fetch import FIELDS

CLIENTS = ("Client", "DII", "FII", "Pro")
LABELS = {"Client": "Client", "DII": "DII", "FII": "FII", "Pro": "Pro"}


def metrics_for(day_rows):
    """Per-client nets for one session, keyed by client type."""
    out = {}
    for client, v in day_rows.items():
        idx_fut_net = v["Future Index Long"] - v["Future Index Short"]
        stk_fut_net = v["Future Stock Long"] - v["Future Stock Short"]
        idx_call = v["Option Index Call Long"] - v["Option Index Call Short"]
        idx_put = v["Option Index Put Long"] - v["Option Index Put Short"]
        stk_call = v["Option Stock Call Long"] - v["Option Stock Call Short"]
        stk_put = v["Option Stock Put Long"] - v["Option Stock Put Short"]
        gross = v["Future Index Long"] + v["Future Index Short"]
        out[client] = {
            "idx_fut_net": idx_fut_net,
            "idx_fut_long_share": (v["Future Index Long"] / gross) if gross else None,
            "stk_fut_net": stk_fut_net,
            "idx_call_net": idx_call,
            "idx_put_net": idx_put,
            "stk_call_net": stk_call,
            "stk_put_net": stk_put,
        }
    return out


def previous_date(dates, target):
    earlier = [d for d in sorted(dates) if d < target]
    return earlier[-1] if earlier else None


def day_actions(history, target):
    """today's metrics plus the change against the previous stored session."""
    today = metrics_for(history[target])
    prev_day = previous_date(history, target)
    prev = metrics_for(history[prev_day]) if prev_day else {}
    delta = {}
    for client, m in today.items():
        p = prev.get(client, {})
        delta[client] = {k: (m[k] - p[k]) if k in p and p[k] is not None else None
                         for k in m if k != "idx_fut_long_share"}
    return today, delta, prev_day


def extremes(history, target, client, key, window=60):
    """Where today's value sits in the recent window (min, max, rank)."""
    dates = [d for d in sorted(history) if d <= target][-window:]
    series = []
    for d in dates:
        m = metrics_for(history[d]).get(client, {}).get(key)
        if m is not None:
            series.append(m)
    if not series:
        return None
    value = series[-1]
    return {
        "value": value,
        "min": min(series),
        "max": max(series),
        "pctile": round(100 * sum(1 for x in series if x <= value) / len(series)),
        "sessions": len(series),
    }


def market_totals(day_rows):
    """Sum across the four client types, per bucket."""
    return {f: sum(v[f] for v in day_rows.values()) for f in FIELDS}
