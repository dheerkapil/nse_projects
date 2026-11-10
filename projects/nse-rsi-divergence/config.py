"""Central configuration for the NSE RSI-Divergence buy-signal screener.

Every consequential knob lives here so you can tune the screener without
touching the engine. Values can be overridden with environment variables.
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # dotenv is optional
    pass

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------
DB_PATH = os.getenv("DB_PATH", str(DATA_DIR / "market.db"))

# --------------------------------------------------------------------------
# Price source: NSE full equity bhavcopy (EOD close/high/low for every symbol)
# --------------------------------------------------------------------------
BHAVCOPY_URL = (
    "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"
)
# Series to keep. All equity-ish series, so a name that switches EQ -> BE (trade
# for trade) or lives on the SME platform never vanishes from the data. Only the
# government-securities series (GS/GB) are excluded.
BHAVCOPY_SERIES = {s.strip() for s in os.getenv(
    "BHAVCOPY_SERIES", "EQ,BE,BZ,SM,ST,IV,RR,E1").split(",") if s.strip()}
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/csv,application/csv,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}
REQUEST_TIMEOUT = 30
REQUEST_RETRIES = 3

# --------------------------------------------------------------------------
# Universe filters — keeps the signal list liquid and tradable
# --------------------------------------------------------------------------
MIN_PRICE = float(os.getenv("MIN_PRICE", "20"))                      # ignore penny stocks
MIN_AVG_TURNOVER_LACS = float(os.getenv("MIN_AVG_TURNOVER", "100"))  # liquidity floor
MIN_HISTORY_BARS = int(os.getenv("MIN_HISTORY_BARS", "60"))          # enough bars for RSI
STALE_BARS = int(os.getenv("STALE_BARS", "10"))                      # drop names with no data for N candles
RETENTION_BARS = int(os.getenv("RETENTION_BARS", "330"))             # rolling price window per symbol

# F&O universe (NSE symbols with futures & options)
FNO_FILE = os.getenv("FNO_FILE", str(PROJECT_ROOT / "config" / "fno_stocks.json"))

# --------------------------------------------------------------------------
# RSI
# --------------------------------------------------------------------------
RSI_PERIOD = int(os.getenv("RSI_PERIOD", "14"))
ATR_PERIOD = int(os.getenv("ATR_PERIOD", "14"))
ATR_MULT = float(os.getenv("ATR_MULT", "1.0"))   # confirm a turned low on a k*ATR bounce (closes)
RESOLVE_RSI_BULL = float(os.getenv("RESOLVE_RSI_BULL", "60"))  # bullish: resolved once RSI closes above
RESOLVE_RSI_BEAR = float(os.getenv("RESOLVE_RSI_BEAR", "40"))  # bearish: resolved once RSI closes below

# --------------------------------------------------------------------------
# Pattern detection (structural — same across profiles)
# --------------------------------------------------------------------------
PIVOT_ORDER = int(os.getenv("PIVOT_ORDER", "5"))            # bars that settle a turned low
PIVOT_BASIS = os.getenv("PIVOT_BASIS", "close").lower()     # close | low  (price series for pivots)
FLAT_TOL_PCT = float(os.getenv("FLAT_TOL_PCT", "0.2"))     # flat top/bottom allowance (%)
MIN_PIVOT_SEPARATION = int(os.getenv("MIN_PIVOT_SEPARATION", "5"))  # bars between lows
LOOKBACK_BARS = int(os.getenv("LOOKBACK_BARS", "120"))      # scan window for pivots
MAX_SIGNAL_AGE_DAYS = int(os.getenv("MAX_SIGNAL_AGE_DAYS", "10"))   # freshness window

# Downtrend gate
DOWNTURN_EMA_SPAN = int(os.getenv("DOWNTURN_EMA_SPAN", "50"))
DOWNTURN_SLOPE_BARS = int(os.getenv("DOWNTURN_SLOPE_BARS", "10"))

# --------------------------------------------------------------------------
# Corporate-action gap guard (bhavcopy prices are unadjusted)
# --------------------------------------------------------------------------
GAP_GUARD_ENABLED = os.getenv("GAP_GUARD_ENABLED", "true").lower() == "true"
GAP_GUARD_PCT = float(os.getenv("GAP_GUARD_PCT", "35"))     # single-day move % threshold

# --------------------------------------------------------------------------
# Strictness profiles
# --------------------------------------------------------------------------
PROFILE = os.getenv("PROFILE", "tight").lower()             # loose | tight

PROFILES = {
    "loose": {
        "MIN_RSI_RISE": 1.0,        # bullish: RSI must rise this much between the lows
        "MIN_PRICE_DROP_PCT": 0.0,  # bullish: depth of the lower price low (%)
        "RSI_CEILING": 55.0,        # bullish: 2nd-pivot RSI must be below this
        "RSI_FLOOR": 45.0,          # bearish: 2nd-pivot RSI must be above this
        "DOWNTURN_GATE": False,     # bullish: require a preceding decline
        "UPTREND_GATE": False,      # bearish: require a preceding advance
    },
    "tight": {
        "MIN_RSI_RISE": 1.0,
        "MIN_PRICE_DROP_PCT": 0.0,
        "RSI_CEILING": 35.0,
        "RSI_FLOOR": 65.0,
        "DOWNTURN_GATE": True,
        "UPTREND_GATE": True,
    },
}


def active_params() -> dict:
    """Return the full parameter set for the active profile (env-overridable)."""
    if PROFILE not in PROFILES:
        raise ValueError(f"Unknown PROFILE '{PROFILE}'. Use 'loose' or 'tight'.")
    params = dict(PROFILES[PROFILE])
    params.update(
        PROFILE=PROFILE,
        RSI_PERIOD=RSI_PERIOD,
        ATR_PERIOD=ATR_PERIOD,
        ATR_MULT=ATR_MULT,
        RESOLVE_RSI_BULL=RESOLVE_RSI_BULL,
        RESOLVE_RSI_BEAR=RESOLVE_RSI_BEAR,
        PIVOT_ORDER=PIVOT_ORDER,
        PIVOT_BASIS=PIVOT_BASIS,
        FLAT_TOL_PCT=FLAT_TOL_PCT,
        MIN_PIVOT_SEPARATION=MIN_PIVOT_SEPARATION,
        LOOKBACK_BARS=LOOKBACK_BARS,
        MAX_SIGNAL_AGE_DAYS=MAX_SIGNAL_AGE_DAYS,
        DOWNTURN_EMA_SPAN=DOWNTURN_EMA_SPAN,
        DOWNTURN_SLOPE_BARS=DOWNTURN_SLOPE_BARS,
        GAP_GUARD_ENABLED=GAP_GUARD_ENABLED,
        GAP_GUARD_PCT=GAP_GUARD_PCT,
        MIN_PRICE=MIN_PRICE,
        MIN_AVG_TURNOVER_LACS=MIN_AVG_TURNOVER_LACS,
        MIN_HISTORY_BARS=MIN_HISTORY_BARS,
    )
    # allow env overrides of profile thresholds
    for k in ("MIN_RSI_RISE", "MIN_PRICE_DROP_PCT", "RSI_CEILING"):
        if os.getenv(k):
            params[k] = float(os.getenv(k))
    return params


# --------------------------------------------------------------------------
# Optional Telegram delivery (Phase 2 — leave blank to disable)
# --------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# --------------------------------------------------------------------------
# Web app
# --------------------------------------------------------------------------
APP_PASSWORD = os.getenv("APP_PASSWORD", "change-me-please")
SESSION_SECRET = os.getenv("SESSION_SECRET_KEY", "change-me-please")
