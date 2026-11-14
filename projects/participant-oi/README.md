# Participant OI

Participant-wise open interest for NSE equity derivatives — who is positioned
where, and how that changed today. Replaces the manual refresh loop in
`derivatives_data_longerterm_new_site.xlsm`.

Source: NSE's `fao_participant_oi_<DDMMYYYY>.csv`, published with the end-of-day
bhavcopy (usually by 18:30 IST, as late as ~21:00 on expiry days).

## What it produces

One Telegram message per session plus a chart:

- **Index futures** — net contracts per client (FII, Client, Pro, DII), the day's
  change, and each client's long share of its own book.
- **Index options** — net call and put contracts per client, with day changes.
- **Stock futures** — net contracts per client.
- **Percentile** — where FII index futures sit in the last 60 sessions.
- **Chart** — Nifty close against FII and Client net index futures.

## Layout

```
fetch.py       # download + parse one session (4 client rows)
store.py       # history CSV, trading calendar, state, price file
analysis.py    # nets, day actions, percentiles
report.py      # Telegram text + chart
run_daily.py   # fetch missing sessions, then report
data/
  participant_oi.csv   # the record: one row per (date, client)
  state.json           # last date sent
```

`data/participant_oi.csv` carries history from **2022-03-21**, seeded from the
old workbook, in the same column order so the two can be compared row for row.

## Running it

```bash
python run_daily.py                 # fill missing sessions, then post
python run_daily.py --no-telegram   # print the report instead of sending
python run_daily.py --date 2026-11-12
python run_daily.py --skip-if-sent  # what the scheduled runs use
python run_daily.py --lookback 60   # widen the backfill window
```

Every run first backfills any missing weekday in the lookback window, so a late
bhavcopy or a missed trigger self-heals the next day. Nothing is ever sent twice
for the same date.

## Dependencies on the rest of the repo

- **Trading calendar** — `projects/common/nse_holidays.json`, shared with
  IVP/price-movers. Holidays are skipped; if the file is missing, only weekends
  are skipped.
- **Nifty close** — read from `projects/gift-nifty-oi/data/nifty_daily.csv`
  (same repo, no network). If it is absent or lags, the price line is simply
  omitted from the chart and the text drops the Nifty line; the OI numbers are
  unaffected.

## Notes

- Long and short always balance across clients, so the message reports the
  **change in total index-futures OI** (buildup or unwinding) rather than a
  meaningless long/short total.
- The NSE file carries two extra total columns; they are dropped, matching the
  old workbook's twelve buckets.
