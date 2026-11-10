"""Daily IVP/IVR report driver.

One report per trading day
--------------------------
The workflow fires on a 30-minute ladder from 18:00 to 00:00 IST. Every run
asks the same question — "has the report for today's trading day gone out yet?"
— and answers it from data/state.json, which the workflow commits. The first
run that finds the day's bhavcopy computes, sends the full report and records
the day as sent; every later run sees that and exits silently. So the user gets
exactly one report, as soon as the data is available, no matter how many slots
fire (or how late GitHub runs them).

Each report is two deliveries: the Telegram text, then the Excel workbook
(output/IVP_IVR_<date>.xlsx, built by src/xlsx_report.py).

If no data has appeared by the time the window closes (midnight IST), a single
"no data" alert is sent instead, and the day is closed.

Trading holidays are detected up front (see src/holidays.py): on a holiday the
run sends a single "market closed" notice on the first check of the day, then
does nothing else — no report, no retries, no "no data" alert. The bundled
holiday list is refreshed weekly, on the first run on/after Monday 18:00 IST.

Loud failure
------------
A send that fails is never swallowed: the run exits non-zero so the Actions job
goes red, and a note is pushed to TELEGRAM_ERROR_CHAT_ID (when configured).
"""

import sys
import sqlite3
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from src.config import (
    load_config, IV_WINDOW_DAYS, TRIM_KEEP_DAYS,
    now_ist, trading_day_for, window_closed,
)
from src.downloader import fetch_bhavcopy, OK, NOT_PUBLISHED, ERROR
from src.database import (
    init_database, store_daily_iv, store_daily_metrics,
    get_historical_ivs, get_symbol_history_count, get_data_coverage,
    trim_old_data, DB_PATH,
)
from src.metrics import compute_iv_rank_percentile
from src.contracts import compute_symbol_iv
from src.state import (
    already_sent, mark_sent, already_failed, mark_failed,
    holiday_notified, mark_holiday_notified,
    get_holiday_sync_week, set_holiday_sync_week,
)
from src.holidays import (
    is_trading_holiday, sync_holiday_list, should_sync, week_key,
)
from src.telegram_bot import (
    send_telegram_message, send_error_notification, send_telegram_document,
    format_results, credentials_present, holiday_message,
)
from src.xlsx_report import build_report

RISK_FREE_RATE = 0.05


# ── metric computation ────────────────────────────────────
def compute_and_store_metrics(date):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT symbol, iv FROM daily_iv WHERE date = ?", (date,)
    ).fetchall()
    conn.close()
    if not rows:
        return []

    stock_metrics = []
    for symbol, current_iv in rows:
        hist_data = get_historical_ivs(symbol, days=IV_WINDOW_DAYS)
        window_ivs = hist_data['iv'].tolist() if len(hist_data) > 0 else []
        ivr, ivp = compute_iv_rank_percentile(current_iv, window_ivs)
        store_daily_metrics(date, symbol, ivr, ivp, current_iv)
        stock_metrics.append({
            'symbol': symbol,
            'iv': round(current_iv, 1),
            'ivr': ivr,
            'ivp': ivp,
            'hist_days': get_symbol_history_count(symbol),
        })
    return stock_metrics


def load_metrics_for_date(date):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """SELECT symbol, current_iv, iv_rank, iv_percentile
           FROM daily_metrics WHERE date = ?""",
        (date,),
    ).fetchall()
    conn.close()
    if not rows:
        return []
    return [
        {
            'symbol': symbol,
            'iv': round(iv, 1),
            'ivr': ivr,
            'ivp': ivp,
            'hist_days': get_symbol_history_count(symbol),
        }
        for symbol, iv, ivr, ivp in rows
    ]


def process_bhavcopy(bhavcopy, date_str):
    """Compute and store IV + IVR/IVP for every symbol in one day's bhavcopy."""
    column_mapping = {
        'TckrSymb': 'SYMBOL',
        'ClsPric': 'CLOSE',
        'StrkPric': 'STRIKE_PR',
        'OptnTp': 'OPTION_TYP',
        'XpryDt': 'EXPIRY_DT',
        'UndrlygPric': 'UNDERLYING_PRICE',
    }
    rename_dict = {o: n for o, n in column_mapping.items() if o in bhavcopy.columns}
    if rename_dict:
        bhavcopy = bhavcopy.rename(columns=rename_dict)

    if 'OPTION_TYP' not in bhavcopy.columns:
        print("No OPTION_TYP column — cannot process this file")
        return 0

    options_data = bhavcopy[bhavcopy['OPTION_TYP'].isin(['CE', 'PE'])]
    if len(options_data) == 0:
        print("No options found in bhavcopy")
        return 0

    symbols = options_data['SYMBOL'].unique()
    today_dt = datetime.strptime(date_str, "%Y-%m-%d")

    # Group once instead of filtering the whole frame per symbol (O(n) not O(n²)).
    by_symbol = {sym: g for sym, g in bhavcopy.groupby('SYMBOL')}

    processed = 0
    for symbol in symbols:
        stock_data = by_symbol.get(symbol)
        if stock_data is None or len(stock_data) == 0:
            continue
        try:
            picked = compute_symbol_iv(stock_data, today_dt, RISK_FREE_RATE)
            if picked is None:
                continue
            current_iv, spot, expiry, atm_strike, option_type = picked
            store_daily_iv(date_str, symbol, current_iv, spot, str(expiry), atm_strike, option_type)

            hist_data = get_historical_ivs(symbol, days=IV_WINDOW_DAYS)
            window_ivs = hist_data['iv'].tolist() if len(hist_data) > 0 else []
            ivr, ivp = compute_iv_rank_percentile(current_iv, window_ivs)
            store_daily_metrics(date_str, symbol, ivr, ivp, current_iv)
            processed += 1
        except Exception as e:
            print(f"Error with {symbol}: {e}")
            continue
    print(f"Processed {processed} symbols for {date_str}")
    return processed


# ── delivery ──────────────────────────────────────────────
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


def deliver_xlsx(date_str):
    """Build the Excel matrix and send it to Telegram. Returns True on success."""
    path = OUTPUT_DIR / f"IVP_IVR_{date_str}.xlsx"
    try:
        n = build_report(path, date_str)
    except Exception as e:
        print(f"❌ Could not build the Excel report: {e}")
        send_error_notification(
            f"⚠️ *IVP/IVR Excel failed* — could not build the workbook for "
            f"{date_str}: {e}"
        )
        return False

    if not n:
        print("❌ Excel report has no rows")
        send_error_notification(
            f"⚠️ *IVP/IVR Excel failed* — no rows for {date_str}."
        )
        return False

    ok = send_telegram_document(str(path), caption=f"📊 IVP/IVR data — {date_str}")
    if not ok:
        send_error_notification(
            f"⚠️ *IVP/IVR Excel failed* — the workbook for {date_str} could not be sent."
        )
    return ok


def deliver_report(date_str, when, stock_metrics):
    """
    Send the text report, then the Excel workbook.

    Returns:
        "ok"          — text and Excel both delivered; the day is closed.
        "text_failed" — nothing marked sent; the next slot retries.
        "xlsx_failed" — text delivered and the day closed, but the Excel file
                        did not go out (the run still goes red so it is noticed,
                        without re-sending the text).
    """
    coverage = get_data_coverage()
    total_days, oldest, newest = coverage if coverage and coverage[0] else (0, None, None)
    messages = format_results(stock_metrics, date_str, total_days, oldest, newest)

    print(f"Sending {len(messages)} Telegram message(s) for {date_str}...")
    ok = True
    for idx, msg in enumerate(messages):
        print(f"Sending part {idx+1}/{len(messages)}")
        if not send_telegram_message(msg):
            ok = False

    if not ok:
        send_error_notification(
            f"⚠️ *IVP/IVR delivery failed* — one or more messages for {date_str} "
            f"did not send. The run is marked failed and will retry on the next slot."
        )
        return "text_failed"

    mark_sent(date_str, when.isoformat())
    print(f"Text report for {date_str} delivered.")

    if not deliver_xlsx(date_str):
        print("=== Text delivered, but the Excel file failed — day closed. ===")
        return "xlsx_failed"

    print(f"=== Report for {date_str} delivered (text + Excel) — day closed. ===")
    return "ok"


def deliver_no_data(date_str, when, status):
    """Send the end-of-window 'no data' alert. Returns True if it went out."""
    reason = {
        NOT_PUBLISHED: "NSE never published a bhavcopy for this date (HTTP 404) — "
                       "it may have been a market holiday.",
        ERROR: "every download attempt failed (network or file-parse error).",
    }.get(status, "no usable data was found.")

    msg = (f"⚠️ *NSE IVP/IVR Report* — {date_str}\n\n"
           f"No report could be generated: {reason}\n\n"
           f"The retry window (18:00–24:00 IST) has closed. "
           f"Nothing more will be sent for {date_str}.")
    if send_error_notification(msg):
        mark_failed(date_str, when.isoformat())
        print(f"=== Sent 'no data' alert for {date_str} — day closed. ===")
        return True
    print("❌ Could not deliver the 'no data' alert either.")
    return False


# ── entry point ───────────────────────────────────────────
def main():
    now = now_ist()
    target = trading_day_for(now)
    target_str = target.strftime("%Y-%m-%d")
    print(f"=== NSE IVP/IVR run — {now:%Y-%m-%d %H:%M %Z} "
          f"(trading day under report: {target_str}) ===")

    load_config()
    init_database()

    # Weekly holiday-list refresh: first run on/after Monday 18:00 IST. Keeps
    # the bundled fallback in config/nse_holidays.json in step with NSE.
    if should_sync(now, get_holiday_sync_week()):
        ok, changed, count = sync_holiday_list(now.year)
        if ok:
            set_holiday_sync_week(week_key(now), now.isoformat())
            print(f"Weekly holiday sync complete (changed={changed}, {count} entries).")
        else:
            print("Weekly holiday sync could not reach NSE — will retry on the next slot.")

    if not credentials_present():
        print("❌ TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — cannot send any alert.")
        return 1

    # Trading holiday? Send a one-off notice on the first check of the day, then
    # do nothing else — no report, no retries, no end-of-window alert.
    holiday, holiday_name = is_trading_holiday(target)
    if holiday:
        if holiday_notified(target_str):
            print(f"{target_str} is a trading holiday ({holiday_name}) — already notified.")
            return 0
        print(f"{target_str} is an NSE trading holiday ({holiday_name}) — sending holiday notice.")
        if send_telegram_message(holiday_message(target_str, holiday_name)):
            mark_holiday_notified(target_str, now.isoformat())
            return 0
        print("❌ Could not deliver the holiday notice.")
        return 1

    # Already handled today? Nothing to do.
    if already_sent(target_str):
        print(f"Report for {target_str} already sent — exiting quietly.")
        return 0

    bhavcopy, status = fetch_bhavcopy(target)

    if status == OK and bhavcopy is not None:
        process_bhavcopy(bhavcopy, target_str)
        stock_metrics = load_metrics_for_date(target_str) or compute_and_store_metrics(target_str)
        if not stock_metrics:
            send_error_notification(
                f"⚠️ *IVP/IVR error* — the bhavcopy for {target_str} downloaded fine "
                f"but produced no IVs. Nothing was sent; the run will retry."
            )
            return 1
        outcome = deliver_report(target_str, now, stock_metrics)
        if outcome == "text_failed":
            return 1
        trim_old_data(TRIM_KEEP_DAYS)
        return 0 if outcome == "ok" else 1

    # No usable data this run.
    if window_closed(now):
        if already_failed(target_str):
            print(f"'No data' alert for {target_str} already sent — exiting quietly.")
            return 0
        return 0 if deliver_no_data(target_str, now, status) else 1

    print(f"No report for {target_str} yet (status={status}); will retry on the next slot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
