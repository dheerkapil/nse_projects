# GIFT Nifty OI

Automated tracking of **GIFT Nifty (NSE IX) futures open interest**, with a chart
pushed to Telegram. Two years of daily history, all sourced from NSE IX.

## Triggers
All triggers are outside GitHub's scheduler, which is best-effort and drops runs.

| what | who fires it | when |
|---|---|---|
| `gift-oi.yml` daily chart | external cron (cron-job.org) | `30 16-23 * * 1-5` Asia/Kolkata - first attempt 16:30 IST, then hourly to 23:30 |
| `gift-oi.yml` fallback | GitHub `schedule` | `30 11-17 * * 1-5` (17:00-23:00 IST) |
| `refresh-holidays.yml` | external cron (cron-job.org) | Mondays 08:30 IST |

The external jobs POST to `.../actions/workflows/<file>/dispatches` with a
fine-grained PAT scoped to this repo (`Actions: read and write`) and body
`{"ref":"main"}`. **If that token expires, nothing runs at all** - keep the
cron-job.org failure notifications on.

Overlapping runs are harmless: every run diffs the working tree first, so once
the day's rows are committed the later runs find nothing to do and exit. A
`concurrency` group (`gift-nifty-oi`) serialises runs so two of them can never
race on `git push` or post the chart twice.

## How it runs
`fetch_oi.py` runs on every trigger:
- skips weekends and coded holidays (`data/holidays.txt`)
- fetches the day's `G_COMBINED_OI_<DDMMYYYY>.csv` (open interest) **and**
  `G_T1_UL_PRICE_<DDMMYYYY>.csv` (NIFTY underlying)
- appends to `data/oi_master.csv` and `data/nifty_daily.csv` (deduped by date)
- once the day's rows are in, later runs that day fetch nothing
- backfills any missed recent weekdays (15-weekday look-back)

`plot_chart.py` then builds `chart.png` - GIFT futures OI vs Nifty 50 spot.
Width scales with the data length (~0.052 in/day): ~13 in for a year, ~26 in for two.
It refuses to emit a chart with fewer than 30 points.

On days new data lands, the chart is posted to Telegram (Bot API). The send step
uses `curl --fail-with-body` and checks `"ok":true` in the response, so a
Telegram error fails the run instead of being swallowed. The commit only happens
after a successful send, so the next hourly run retries instead of the chart
being lost. Any failure also pings the same Telegram chat with a link to the run.

`refresh_holidays.py` refreshes the holiday list from NSE IX.

## Files
| file | purpose |
|---|---|
| `data/oi_master.csv` | OI series: `date,nifty_fut_total_oi` (two years) |
| `data/nifty_daily.csv` | Nifty 50 closes: `date,nifty` (two years) |
| `data/holidays.txt` | NSE IX trading closures |
| `fetch_oi.py` | daily fetcher (OI + Nifty) |
| `plot_chart.py` | chart builder |
| `resolve_chat.py` | Telegram chat-id resolver |
| `refresh_holidays.py` | holiday list refresh |
| `.github/workflows/gift-oi.yml` | daily chart job |
| `.github/workflows/refresh-holidays.yml` | holiday refresh job |
| `.github/workflows/telegram-note.yml` | sends an arbitrary note to Telegram |

## Secrets
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

## Notes
- Everything comes from **nseix.com** (OI + underlying), so there is no external
  price dependency - Yahoo returns garbage to cloud runners.
- Raw NSE IX files are **not** committed (`.gitignore`); only the derived series
  is kept, so the repo stays tiny.
- If the holiday list is ever wrong, the 15-weekday backfill self-heals it.
- On NSE trading holidays GIFT Nifty still trades but the NIFTY index publishes
  no close, so those days have an `oi_master` row and no `nifty_daily` row. The
  inner join in `plot_chart.py` drops them by design - they are not data gaps.
