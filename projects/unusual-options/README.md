# Unusual options

Far-OTM stock options with fresh open interest, delivered as a workbook. This is
the automated version of the manual `unusual_options.xlsx` loop: download the
day's F&O bhavcopy, filter, append to history, rebuild the workbook, send it.

## What it keeps

NSE's UDiFF F&O bhavcopy, filtered to `FinInstrmTp = "STO"` (stock options), then:

1. **OTM only** — a call must sit above spot, a put below it.
2. **Beyond the first N strikes** — the N strikes nearest the money on each side
   are dropped, so "OTM" means genuinely far out, not one rupee away.
3. **Vol/COI > 0** — the change in open interest must be positive, which excludes
   every contract that unwound or held flat.
4. **COI ≥ N contracts** — drops dust.

Both N values live on the workbook's Parameters sheet and at the top of
`transform.py`.

## The workbook

| sheet | content |
|---|---|
| `Parameters` | the two thresholds used for this build |
| `Sheet1` | URL builder for the month's bhavcopies |
| `Sheet2` | the rows, sorted by COI/OI then COI, both descending |

`Sheet2` holds the last 60 sessions, but the table's filter is pinned to the
latest one — the rest are hidden, not removed. Clear the filter on `TradDt` to
see them. The two traded-value columns carry a red→yellow→green scale; the
contract-name and Gap columns are hidden.

## Storage

History is one gzipped CSV per month under `data/`, 20 base columns only — the
three derived columns are recomputed at build time. That's about 140 KB a
session, or ~35 MB a year. The raw bhavcopies are **not** kept: they're public,
7 MB each, and would be 1.8 GB a year in git. The workbook isn't committed
either; it goes to Telegram.

## Running

```
python run_daily.py --skip-if-sent     # what the schedule does
python run_daily.py --no-telegram      # build locally
python run_daily.py --lookback 60      # backfill a wider window
```

Needs `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. Reads the shared NSE holiday
calendar from `projects/common/nse_holidays.json`, so it won't look for sessions
on market holidays.
