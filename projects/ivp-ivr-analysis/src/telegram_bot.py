import os
import requests

from src.config import IV_WINDOW_DAYS, MIN_HISTORY_DAYS


def credentials_present():
    """True when both the bot token and the report chat id are configured."""
    return bool(os.environ.get('TELEGRAM_BOT_TOKEN') and os.environ.get('TELEGRAM_CHAT_ID'))


def _post(bot_token, chat_id, message):
    """POST one message to Telegram. Returns (ok, detail)."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'Markdown'}
    try:
        print(f"📤 Sending message to {chat_id} (length: {len(message)} chars)")
        response = requests.post(url, json=payload, timeout=15)
        print(f"📥 Response status: {response.status_code}")
        if response.status_code == 200:
            print("✅ Telegram notification sent successfully!")
            return True, "ok"
        detail = f"HTTP {response.status_code}: {response.text[:300]}"
        print(f"❌ Telegram API error: {detail}")
        return False, detail
    except Exception as e:
        print(f"❌ Exception sending Telegram message: {e}")
        return False, str(e)


def send_telegram_message(message, chat_id=None):
    """Send a single message via the Telegram bot to the report chat."""
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = chat_id or os.environ.get('TELEGRAM_CHAT_ID')

    if not bot_token or not chat_id:
        print("❌ Telegram credentials not found in environment "
              "(TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)")
        return False

    ok, _ = _post(bot_token, chat_id, message)
    return ok


def send_error_notification(message):
    """
    Send to TELEGRAM_ERROR_CHAT_ID when set, else to the normal chat.

    Returns True when the message went out. If no credentials exist at all this
    returns False — the caller decides how loud to be about it.
    """
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_ERROR_CHAT_ID') or os.environ.get('TELEGRAM_CHAT_ID')
    if not bot_token or not chat_id:
        return False
    ok, _ = _post(bot_token, chat_id, message)
    return ok


def send_telegram_document(path, caption=""):
    """
    Send a file (the Excel workbook) to the report chat via sendDocument.

    Returns True on success. A caption is sent as plain text — no parse_mode —
    so a filename or date can never break Markdown parsing.
    """
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if not bot_token or not chat_id:
        print("❌ Telegram credentials not found (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    try:
        with open(path, "rb") as fh:
            files = {
                "document": (
                    os.path.basename(path), fh,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            }
            data = {"chat_id": chat_id, "caption": caption}
            print(f"📤 Sending document {os.path.basename(path)}")
            response = requests.post(url, data=data, files=files, timeout=60)
        print(f"📥 Response status: {response.status_code}")
        if response.status_code == 200:
            print("✅ Document sent successfully!")
            return True
        print(f"❌ Telegram document error: {response.status_code} - {response.text[:200]}")
        return False
    except Exception as e:
        print(f"❌ Exception sending document: {e}")
        return False


def holiday_message(date_str, name=""):
    """The one-off notice sent on the first check of a trading holiday."""
    when = f" ({name})" if name else ""
    return (f"🗓️ *NSE Trading Holiday* — {date_str}\n\n"
            f"Markets are closed today{when}, so there is no bhavcopy and no "
            f"IVP/IVR report.\n\n"
            f"The next report will go out on the next trading day.")


def _cell(value, decimals=1, suffix=""):
    """Format a metric, rendering a missing (gated) value as an em dash."""
    if value is None:
        return "—"
    if isinstance(value, (int, float)):
        return f"{value:.{decimals}f}{suffix}" if decimals is not None else f"{value}{suffix}"
    return f"{value}{suffix}"


def _table(rows, symw):
    """
    Build a fixed-width table. Every line has identical width and is returned
    as a monospace block (triple backticks) so columns line up regardless of
    how many digits a value has.
    """
    cols = (symw, 5, 6, 7, 5)  # SYMBOL  IVP  IVR  IV  DAYS
    fmt = " ".join(f"{{:>{w}}}" if i else f"{{:<{w}}}" for i, w in enumerate(cols))

    head = fmt.format("STOCK", "IVP", "IVR", "IV", "DAYS")
    sep = " ".join("-" * w for w in cols)
    body = [fmt.format(*r) for r in rows]
    return "```\n" + "\n".join([head, sep] + body) + "\n```"


def format_results(stock_metrics, date, total_days=0, oldest=None, newest=None):
    """Return a list of messages (each <= 4096 chars) to send."""
    if not stock_metrics:
        return ["No data available for today"]

    ranked = sorted([s for s in stock_metrics if s.get('ivp') is not None],
                    key=lambda x: x['ivp'], reverse=True)
    unranked = [s for s in stock_metrics if s.get('ivp') is None]

    coverage_line = ""
    if total_days > 0 and oldest and newest:
        coverage_line = f"📅 Historical data: {total_days} days – from {oldest} to {newest}\n\n"
    elif total_days > 0:
        coverage_line = f"📅 Historical data: {total_days} days\n\n"

    header = f"📊 *NSE IVP/IVR Report* - {date}\n\n"
    header += coverage_line
    header += f"*Total symbols: {len(stock_metrics)}*\n\n"
    header += "*Sorted by IV Percentile (Highest → Lowest)*\n\n"

    # symbol column sized to the actual data (keeps the table narrow and aligned)
    symw = max(6, min(14, max(len(s['symbol']) for s in stock_metrics)))

    # rows as plain tuples
    table_rows = []
    for s in ranked:
        table_rows.append((
            s['symbol'][:symw],
            f"{int(round(s['ivp']))}%",
            _cell(s.get('ivr')),
            _cell(s.get('iv')),
            str(s.get('hist_days', 0)),
        ))
    for s in unranked:
        table_rows.append((
            s['symbol'][:symw],
            "—", "—", _cell(s.get('iv')), str(s.get('hist_days', 0)),
        ))

    # chunk the rows; Telegram caps a message at 4096 chars
    chunk_size = 45
    messages = []
    n = len(table_rows)
    for i in range(0, n, chunk_size):
        chunk = table_rows[i:i + chunk_size]
        block = _table(chunk, symw)
        if i == 0:
            full_msg = header + block
        else:
            full_msg = "*Continued...*\n\n" + block
        if i + chunk_size >= n:
            full_msg += "\n\n" + footer_text(ranked, unranked)
        messages.append(full_msg)

    return messages


def footer_text(sorted_metrics, unranked=None):
    """Generate recommendations and warnings (common for all)"""
    unranked = unranked or []
    high_ivp = [s for s in sorted_metrics if s['ivp'] >= 80]
    low_ivp = [s for s in sorted_metrics if s['ivp'] <= 20]

    footer = ""
    if high_ivp:
        footer += f"\n🔴 *High IVP (>80%)*: {', '.join([s['symbol'] for s in high_ivp[:5]])}"
        if len(high_ivp) > 5:
            footer += f" and {len(high_ivp)-5} more"
        footer += "\n   *Consider credit spreads*"

    if low_ivp:
        footer += f"\n\n🟢 *Low IVP (<20%)*: {', '.join([s['symbol'] for s in low_ivp[:5]])}"
        if len(low_ivp) > 5:
            footer += f" and {len(low_ivp)-5} more"
        footer += "\n   *Consider debit spreads*"

    if unranked:
        footer += (f"\n\n⚠️ *Not ranked (<{MIN_HISTORY_DAYS} days of history)*: "
                   f"{', '.join([s['symbol'] for s in unranked[:5]])}")
        if len(unranked) > 5:
            footer += f" and {len(unranked)-5} more"
        footer += "\n   Shown with IV only; IVP/IVR suppressed until enough history."

    return footer
