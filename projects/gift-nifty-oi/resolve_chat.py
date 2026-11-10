#!/usr/bin/env python3
"""Print the Telegram chat id to send to. Uses TELEGRAM_CHAT_ID if set,
otherwise resolves it from the bot's recent updates."""
import os, json, urllib.request

tok = os.environ.get("TELEGRAM_BOT_TOKEN", "")
chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
if chat:
    print(chat); raise SystemExit
if not tok:
    raise SystemExit
try:
    d = json.load(urllib.request.urlopen(
        f"https://api.telegram.org/bot{tok}/getUpdates", timeout=30))
    for u in reversed(d.get("result", [])):
        m = u.get("message") or u.get("channel_post") or {}
        c = m.get("chat", {})
        if c.get("id"):
            print(c["id"]); break
except Exception as e:
    print("resolve failed:", e)
