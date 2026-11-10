# NSE RSI-Divergence Screener

Scans every NSE equity for **regular bullish RSI divergence** — the swing-buy setup
where price prints a *lower low* but RSI refuses to and prints a *higher low* — and
surfaces the freshest, strongest setups on a web dashboard.

Price source: **NSE full equity bhavcopy** (end-of-day). Daily/positional, not intraday.

> Not investment advice. Signals are a screen, not a recommendation — do your own diligence.

## How it works

1. **Fetch** — download the daily `sec_bhavdata_full` bhavcopy from NSE (EQ series only).
2. **Store** — append to a SQLite price history (~1 year backfilled on first run).
3. **Compute** — Wilder RSI(14) on daily closes.
4. **Detect** — find confirmed fractal pivot lows, then flag pairs where price makes a
   lower low and RSI makes a higher low (with configurable strictness).
5. **Score & persist** — rank each signal 0–100, keep it active for a freshness window,
   and publish a JSON snapshot the dashboard reads.

### Strictness profiles

One switch (`PROFILE=loose|tight`) drives the thresholds:

| Parameter            | Loose | Tight |
|----------------------|-------|-------|
| `MIN_RSI_RISE`       | 1.0   | 5.0   |
| `MIN_PRICE_DROP_PCT` | 0.0   | 2.0   |
| `RSI_CEILING`        | 55    | 35    |
| Downturn gate        | off   | on    |

Structural params (`PIVOT_ORDER=5`, `MIN_PIVOT_SEPARATION=5`, `LOOKBACK_BARS=120`,
`MAX_SIGNAL_AGE_DAYS=10`) live in `config.py`.

### Corporate-action guard

Bhavcopy prices are unadjusted; a split/bonus fakes a "lower low". Symbols with a
single-day move beyond `GAP_GUARD_PCT` (default 35%) are skipped. Heuristic — proper
adjustment is a future refinement.

## Layout

```
config.py               # every tunable knob
run_daily.py            # fetch -> store -> scan -> snapshot
scripts/backfill.py     # one-off ~1yr history load
src/
  downloader.py         # NSE bhavcopy fetch + parse
  database.py           # SQLite prices/signals store
  indicators.py         # Wilder RSI
  divergence.py         # fractal pivots + divergence scan
  signals.py            # scoring + universe filters
web/
  app.py                # Flask dashboard + login
  templates/            # index.html, login.html
tests/                  # RSI + divergence unit tests
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env          # set APP_PASSWORD and SESSION_SECRET_KEY

# one-off history load (~1 year)
python scripts/backfill.py --days 365

# daily run
python run_daily.py

# dashboard
python web/app.py             # http://localhost:8000
```

## Tests

```bash
python tests/test_indicators.py
python tests/test_divergence.py
```

## Deploy (matches the existing stack)

- **GitHub Actions** (`.github/workflows/daily.yml`) runs the scan after market close and
  commits `output/daily_signals.json`.
- **Render** runs `web/app.py` via gunicorn (see `Procfile`); the dashboard reads the
  committed snapshot. Set `APP_PASSWORD` and `SESSION_SECRET_KEY` in Render's env.

## Roadmap

- **Phase 2:** Telegram notifications.
- **Phase 3:** hidden/positive-reversal divergence as a labelled second type; proper
  corporate-action adjustment; backtesting of signal outcomes.
