"""
Choosing which option contract to compute IV from.

A day's bhavcopy holds several expiries for the same (symbol, strike, option
type) — stocks carry monthly expiries (current / next / one further), indices
carry weeklies as well. Picking a row blindly mixes maturities, so the same
"IV" can come from a 2-day contract one day and a 57-day one the next, and a
contract expiring *today* (zero time value) blows up the solver.

This module always selects the ATM option on the CURRENT-MONTH expiry, rolled
to the next month once the current month's contract has expired or expires
today, and prefers a contract that actually traded.
"""

from datetime import datetime

from src.iv_calculator import calculate_iv

RISK_FREE_RATE = 0.05
IV_FLOOR = 5.0
IV_CAP = 150.0


def safe_float(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def parse_expiry(raw):
    """Parse an expiry string. Handles both '30-Mar-2026' and '2026-03-30'."""
    for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(raw), fmt)
        except (ValueError, TypeError):
            continue
    return None


def monthly_expiries(expiry_dates):
    """
    The monthly contract for each calendar month is the LAST expiry in that
    month. Returns a sorted list of (datetime, raw_string).
    """
    latest = {}
    for raw in expiry_dates:
        dt = parse_expiry(raw)
        if dt is None:
            continue
        key = (dt.year, dt.month)
        if key not in latest or dt > latest[key][0]:
            latest[key] = (dt, raw)
    return sorted(latest.values())


def compute_symbol_iv(stock_data, today_dt, risk_free_rate=RISK_FREE_RATE):
    """
    IV from the ATM option on the current-month expiry.

    stock_data : all rows for one symbol on one day (renamed columns:
                 SYMBOL, CLOSE, STRIKE_PR, OPTION_TYP, EXPIRY_DT,
                 UNDERLYING_PRICE; volume stays as TtlTradgVol)
    today_dt   : the trade date

    Returns (iv, spot, expiry_raw, strike, option_type) or None when there is
    no usable contract. Never fabricates a value — a symbol with no tradable
    current-month ATM option simply has no IV that day.
    """
    # --- spot ---
    spot = 0.0
    if 'UNDERLYING_PRICE' in stock_data.columns and len(stock_data):
        spot = safe_float(stock_data['UNDERLYING_PRICE'].iloc[0])
    if spot <= 0:
        fut = stock_data[stock_data['OPTION_TYP'] == 'XX']
        if len(fut):
            spot = safe_float(fut['CLOSE'].iloc[0])
    if spot <= 0 and len(stock_data):
        spot = safe_float(stock_data['CLOSE'].iloc[0])
    if spot <= 0:
        return None

    opts = stock_data[stock_data['OPTION_TYP'].isin(['CE', 'PE'])]
    if len(opts) == 0 or 'EXPIRY_DT' not in opts.columns:
        return None

    # --- current-month expiry (rolled if expired / expiring today) ---
    chosen = None
    for dt, raw in monthly_expiries(opts['EXPIRY_DT'].unique()):
        if (dt - today_dt).days >= 1:
            chosen = (dt, raw)
            break
    if chosen is None:
        return None
    expiry_dt, expiry_raw = chosen
    dte = (expiry_dt - today_dt).days

    ex = opts[opts['EXPIRY_DT'] == expiry_raw]
    if len(ex) == 0:
        return None

    strikes = [safe_float(s) for s in ex['STRIKE_PR'].unique()]
    if not strikes:
        return None
    atm = min(strikes, key=lambda x: abs(x - spot))

    volcol = 'TtlTradgVol' if 'TtlTradgVol' in ex.columns else ('VOL' if 'VOL' in ex.columns else None)

    def candidate(option_type, require_volume):
        rows = ex[(ex['STRIKE_PR'] == atm) & (ex['OPTION_TYP'] == option_type)]
        for _, r in rows.iterrows():
            price = safe_float(r['CLOSE'])
            vol = safe_float(r[volcol]) if volcol else 0.0
            if price > 0 and (vol > 0 or not require_volume):
                return r
        return None

    # Only a contract that actually traded gives a real IV — an untraded ATM
    # option carries a stale indicative price that produces garbage (this is
    # what pushed BAJAJHLDNG, BOSCHLTD, PRESTIGE etc. to the 150 clamp).
    row = None
    for option_type in ('CE', 'PE'):          # ATM CE, else ATM PE — traded only
        row = candidate(option_type, True)
        if row is not None:
            break
    if row is None:
        return None

    price = safe_float(row['CLOSE'])
    option_type = row['OPTION_TYP']
    if not (price > 0 and spot > 0 and atm > 0 and dte > 0):
        return None

    try:
        iv = calculate_iv(price, spot, atm, dte / 365.0, risk_free_rate, option_type)
    except Exception:
        return None

    return max(IV_FLOOR, min(IV_CAP, iv)), spot, expiry_raw, atm, option_type
