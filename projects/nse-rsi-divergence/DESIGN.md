# NSE RSI-Divergence Screener — Design Doc

**Status:** Built and live. Daily GitHub Actions run; web dashboard on Render.
**Look & feel:** dark-first dashboard (Material palette, card layout, login screen).

---

## 1. Purpose

Scan every NSE equity — and tag the **F&O** subset — for **regular RSI divergence**
(bullish and bearish) and surface the *currently actionable* setups on a web dashboard.

- **Bullish:** price makes a **lower low** while RSI makes a **higher low**.
- **Bearish:** price makes a **higher high** while RSI makes a **lower high**.

Daily / end-of-day system (bhavcopy is EOD). Not intraday.

---

## 2. Data sources

- **NSE full equity bhavcopy** (`sec_bhavdata_full_DDMMYYYY.csv`), one file per trading day.
  Per-symbol open, high, low, close, prev-close, volume, turnover. Only the **EQ** series.
- **F&O universe:** NSE market-lots file (`fo_mktlots.csv`), refreshed **daily**; the
  committed list is rewritten only when the symbol set actually changes.
- **History:** ~1 year backfilled on the first run only; thereafter one bhavcopy per day.
  The price DB is cached between runs. Steady state ≈ **two small requests per day**.

### Corporate-action guard
Bhavcopy prices are **unadjusted**. A split/bonus creates an artificial single-day gap that
fakes a lower low and poisons RSI history. **Guard:** if a symbol's close moves more than
`GAP_GUARD_PCT` (default 35%) in one day, exclude it from the scan.

---

## 3. Indicator

- **RSI:** Wilder's RSI, period **14**, on daily **closes**.
- Validated against TradingView: Wilder-14 on closes matches TradingView to within a few
  tenths (differences are data-feed level, not method). The SMA-based "Cutler" variant does
  **not** match — confirming Wilder is the correct method.

---

## 4. Pattern

### Pivot basis — closes, not intraday lows
Pivots are detected on the **settled (close)** price series (`PIVOT_BASIS = close`).
An earlier build used the intraday **low**; that sampled RSI on the wrong bar and produced
false positives (e.g. KPEL). Pivots and RSI are now read on the **same close bar**, so both
reconcile with TradingView.

### Definition
At two confirmed pivots:
- **Bullish:** `close2 < close1` (lower low) and `rsi2 > rsi1` (higher RSI low).
- **Bearish:** `close2 > close1` (higher high) and `rsi2 < rsi1` (lower RSI high).

### Pivots
- **Fractal:** a bar that is the unique extreme within `PIVOT_ORDER` bars either side.
- **Confirmed only:** usable only after `PIVOT_ORDER` bars have passed.
- **Min separation:** the two pivots must be ≥ `MIN_PIVOT_SEPARATION` bars apart.

### Gates
- Bullish: **downtrend gate** (price below a falling EMA) — a bullish divergence matters at
  the end of a decline.
- Bearish: **uptrend gate** (price above a rising EMA).
- Both gates are **on in `tight`, off in `loose`**.

---

## 5. Signal rules — the fixed constitution

These rules are **fixed**. They are **not** adjusted per symbol or per outcome.

1. **Pivot basis:** closes (settled price), not intraday low.
2. **Divergence (regular):** bullish = lower low + higher RSI low; bearish = higher high +
   lower RSI high.
3. **Confirmation:** a pivot is usable only after `PIVOT_ORDER` bars; the signal fires on the
   confirmation bar (second pivot + `PIVOT_ORDER`).
4. **Invalidation (hard, permanent):** a signal is invalidated the moment price **closes**
   beyond the level that defined it, on **any** bar after confirmation —
   bullish: a close **below** the second-pivot low; bearish: a close **above** the
   second-pivot high. Invalidation is an **event**; it does not un-happen. A later recovery
   does **not** revive the signal.
5. **No age limit:** a signal stays as long as it is not invalidated.
6. **Played-out signals are retained:** a move in the trade direction does not retire a
   signal on its own.
7. **Ordering:** most recently confirmed first (recency), strength as tiebreak.
8. **Views:** `Live` = not invalidated (default); `All` = everything, invalidated rows marked.

### Rationale
A divergence is a **falsifiable statement**. The second-pivot level is its falsification line:
if price closes through it, the statement is proven wrong, and a wrong statement does not
become true because price later wanders back. Adjusting a rule *because of one name's outcome*
is hindsight / curve-fitting and destroys the meaning of the signal — the list stops being a
signal and becomes a highlight reel.

### Amendment policy
A rule changes only as a **versioned, population-wide decision** — backtested across all
names, decided **in advance**, dated in the Change Log (§11). Never per symbol. Parameter
*tuning* is legitimate when justified by aggregate evidence and applied uniformly; it is
illegitimate when driven by a single stock's result.

---

## 6. Strictness profiles

One `PROFILE` switch (`loose` | `tight`); **default = `tight`**.

| Parameter              | Loose | Tight | Meaning                                       |
|------------------------|-------|-------|-----------------------------------------------|
| `MIN_RSI_RISE`         | 1.0   | 5.0   | RSI must move this much between the pivots    |
| `MIN_PRICE_DROP_PCT`   | 0.0   | 2.0   | Depth of the price move (%)                   |
| `RSI_CEILING` (bull)   | 55    | 35    | 2nd-pivot RSI must be below this              |
| `RSI_FLOOR` (bear)     | 45    | 65    | 2nd-pivot RSI must be above this              |
| Downtrend gate (bull)  | off   | on    | Require a preceding decline                   |
| Uptrend gate (bear)    | off   | on    | Require a preceding advance                   |

All values live in `config.py`, overridable by env vars.

---

## 7. Scoring

Each signal gets a **0–100 strength score** (direction-aware) to rank within a view:

- magnitude of the RSI move between pivots (40),
- depth of the price move (20),
- RSI level at the second pivot — lower = stronger for bullish, higher = stronger for bearish (25),
- pivot separation / timing quality (15).

Default dashboard ordering is **recency-first**, with strength as tiebreak.

---

## 8. Output — web dashboard

Dark-first (no white flash), card layout, login screen. Three toolbar toggles:

- **Universe:** `All` | `F&O`
- **Direction:** `Bullish` | `Bearish`
- **View:** `Live` | `All`

**Columns:** Symbol · Signal date · Entry (close at confirmation) · Last · % chg ·
RSI now · Pivot-1 (date/price/RSI) · Pivot-2 (date/price/RSI) · Strength · Age.
Symbols link to their TradingView chart. F&O rows carry an **F&O** tag; invalidated rows
(in the `All` view) are greyed and tagged **invalid**.

---

## 9. Config parameters (all in `config.py`)

```
PROFILE                 loose | tight        (default: tight)
RSI_PERIOD              14
PIVOT_ORDER             5
PIVOT_BASIS             close | low         (default: close)
MIN_PIVOT_SEPARATION    5
LOOKBACK_BARS           120
MIN_RSI_RISE            1.0 / 5.0
MIN_PRICE_DROP_PCT      0.0 / 2.0
RSI_CEILING             55 / 35
RSI_FLOOR               45 / 65
DOWNTURN_GATE           off / on
UPTREND_GATE            off / on
MAX_SIGNAL_AGE_DAYS     10   (kept in config; not applied as a filter)
GAP_GUARD_PCT           35
MIN_PRICE               20
MIN_AVG_TURNOVER_LACS   100
FNO_FILE                config/fno_stocks.json
BACKFILL_DAYS           ~250
```

---

## 10. Architecture

```
nse-rsi-divergence/
├── config.py                    # every knob
├── run_daily.py                 # fetch -> store -> scan -> persist -> snapshot
├── scripts/
│   ├── backfill.py              # one-off history load
│   ├── refresh_fno.py           # daily F&O universe refresh
│   └── summarize.py             # run-summary markdown
├── src/
│   ├── downloader.py            # NSE bhavcopy fetch + parse
│   ├── database.py              # SQLite price/signal store
│   ├── indicators.py            # Wilder RSI, EMA
│   ├── divergence.py            # pivots + bullish/bearish detection
│   └── signals.py               # scoring, invalidation, F&O tagging
├── web/app.py                   # Flask dashboard + login
├── web/templates/               # index.html, login.html
├── config/fno_stocks.json       # F&O universe (auto-refreshed)
├── .github/workflows/daily.yml  # daily run
└── tests/
```

---

## 11. Change Log

- **2026-10-15**
  - Pivots moved from intraday **low** to **close** (settled) — `PIVOT_BASIS = close`.
  - **Bearish** divergence added; signals now carry a `direction`.
  - **F&O universe** added (`config/fno_stocks.json`), auto-refreshed daily.
  - Signals carry `is_fno` and `invalidated` flags.
  - **Invalidation rule adopted** (§5.4): close beyond the second-pivot level on any bar
    after confirmation, permanent.
  - Dashboard: Universe / Direction / View toggles; **recency-first** sort; dark by default;
    "Data as of" stat removed; timestamp without seconds.
  - `MAX_SIGNAL_AGE_DAYS` retained in config but **not applied** as a filter (no age limit).

---

## 12. Roadmap

1. **Phase 1 (done):** data → RSI → divergence (both directions) → signals → web dashboard.
2. **Phase 2:** Telegram notifications.
3. **Phase 3:** hidden / positive-reversal divergence as a labelled second type; proper
   corporate-action adjustment; backtesting of signal outcomes.
