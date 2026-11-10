# NSE IVP/IVR Analysis

Automated daily analysis of Implied Volatility Percentile (IVP) and Implied Volatility Rank (IVR) for NSE F&O stocks.

## Features

- 📊 Fetches daily F&O bhavcopy from NSE
- 📈 Calculates IV, IVP, and IVR for all F&O stocks
- 📱 Sends **one** Telegram report per trading day, as soon as the bhavcopy is out
- 📗 Also sends an **Excel workbook** of the IVP/IVR matrix, colour-coded
- 🔁 Retries every 30 minutes from 18:00 to 00:00 IST until the data appears
- 🗓️ Skips NSE trading holidays automatically
- ⚠️ Alerts you if no data could be fetched by the end of the window
- ☁️ Runs automatically via GitHub Actions
- 📦 One JSON file per trading day in `data/daily/`

## How the daily alert works

The workflow fires on a 30-minute ladder — `18:00, 18:30, … 23:30, 00:00` IST,
Mon–Fri. Every run asks one question: *has today's report gone out yet?*

- **Trading holiday** (checked against NSE's holiday list) → send a one-off
  "market closed" notice on the first check of the day, then do nothing else.
- **Data is available** → compute IV/IVR/IVP, send the full report, record the
  day as sent in `data/state.json`, and stop. Later slots that day do nothing.
- **Data not published yet** (NSE posts the F&O bhavcopy around 18:00 IST, and
  as late as ~21:00 on monthly-expiry Thursdays) → exit quietly and wait for the
  next slot.
- **Nothing by midnight IST** → send a single "no data" alert and close the day.

So you get **exactly one report per trading day**, at the earliest slot where the
data exists — never a duplicate flood, and never a silent failure.

### Trading holidays

The day under report is checked against NSE's holiday list (`FO` segment), taken
live from NSE's `holiday-master` API with a bundled fallback in
`config/nse_holidays.json` for when the API is unreachable. On a holiday you get
a single **"NSE Trading Holiday"** notice on the first check of the day (sent
once — tracked in `data/state.json`), and nothing else; there's no spurious
late-night "no data" alert.

The bundled fallback is **refreshed weekly** — on the first run on/after Monday
18:00 IST, the live list is fetched and the file rewritten if anything changed
(the change is committed). If NSE is unreachable that week, the sync retries on
the next slot. When no list at all can be found for a year the check fails open
(assumes a trading day), so a missed holiday costs at most one alert rather than
a dropped report.

### Delivery guarantees

- A failed Telegram send (or missing credentials) makes the Actions run **fail
  (red)** instead of silently passing, and a note goes to
  `TELEGRAM_ERROR_CHAT_ID` when that secret is set.
- All dates are computed in **IST**, not the runner's UTC clock — important
  because GitHub frequently runs the late slots after midnight IST.

### Excel report

Alongside the Telegram text, each day's run builds `output/IVP_IVR_<date>.xlsx`
and sends it to the same chat as a document. It is the matrix layout: one block
per stock (ranked by today's IVP, highest first) showing **IVP** and **IVR** for
**every trading day on record** — the full rolling year, newest column first —
with a dark rule between stocks.

Each IVP/IVR row carries a 3-colour scale across all the date columns —
**highest green, lowest red** — so a stock's history reads at a glance.

Columns run `DAYS | STOCK | PARA. | <dates>`, with no rank column — stocks are
still ordered by today's IVP, highest first. Those three lead deliberately:
Excel can only freeze columns from the left edge, so putting them first means
they stay pinned while you scroll right through the year.

`DAYS` and `STOCK` are merged down across each stock's two parameter rows, so a
stock reads as one block; every cell is boxed with a thin border, and the rule
between stocks is half a row tall so it reads as a line.

Only ranked stocks appear (IVP is suppressed under 60 days of history); the
unranked ones still show in the Telegram text. If the workbook can't be built or
sent, the run goes red and `TELEGRAM_ERROR_CHAT_ID` is notified — the text report
is never re-sent as a result.

### Reliable timing (external trigger)

GitHub's `schedule` trigger is best-effort and runs from a shared queue. On this
repository it has been firing **anywhere from ~35 minutes to ~10 hours late**
(measured against the cron slot), so a report written for 18:00 IST can land
after midnight. Nothing in the workflow file can control this.

The fix is to trigger the workflow with `workflow_dispatch`, which starts
immediately, from an external timer — see
**[docs/external-trigger.md](docs/external-trigger.md)** for the exact setup
(a fine-grained token plus a free cron service).

The in-workflow `schedule` ladder is kept as a **fallback**: if the external
timer is ever down, you still get your report, just at GitHub's unpredictable
time. Because the workflow is idempotent, both firing together still yields
exactly one report.

## Setup

1. Clone repository
2. Install dependencies: `pip install -r requirements.txt`
3. Create `.env` file with Telegram credentials
4. Run: `python src/main.py`

### Secrets

| Secret | Purpose |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Chat that receives the daily report |
| `TELEGRAM_ERROR_CHAT_ID` | *(optional)* chat for failure / no-data alerts |

## Telegram Notification Example
