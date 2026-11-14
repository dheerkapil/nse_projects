"""Download and parse one session of NSE participant-wise open interest.

Source: https://nsearchives.nseindia.com/content/nsccl/fao_participant_oi_DDMMYYYY.csv

The file holds one row per client type (Client, DII, FII, Pro) plus a TOTAL row.
It is published with the end-of-day bhavcopy, usually by 18:30 IST and as late
as ~21:00 on expiry days.
"""

from __future__ import annotations

import csv
import io
from datetime import date

import requests

URL = ("https://nsearchives.nseindia.com/content/nsccl/"
       "fao_participant_oi_{ddmmyyyy}.csv")

CLIENTS = ("Client", "DII", "FII", "Pro")

# The twelve buckets we keep, in the order the workbook used them.
FIELDS = [
    "Future Index Long", "Future Index Short",
    "Future Stock Long", "Future Stock Short",
    "Option Index Call Long", "Option Index Put Long",
    "Option Index Call Short", "Option Index Put Short",
    "Option Stock Call Long", "Option Stock Put Long",
    "Option Stock Call Short", "Option Stock Put Short",
]

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36"),
    "Accept": "text/csv,application/csv,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def _norm(name: str) -> str:
    return " ".join(str(name).replace("\ufeff", "").split())


def fetch(day: date, timeout: int = 30):
    """Rows for `day`, or None if the file is not published yet."""
    url = URL.format(ddmmyyyy=day.strftime("%d%m%Y"))
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
    except requests.RequestException as exc:
        print(f"{day}: request failed ({exc})")
        return None
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        print(f"{day}: HTTP {resp.status_code}")
        return None

    text = resp.content.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if len(rows) < 3:
        print(f"{day}: file too short ({len(rows)} lines)")
        return None

    # Line 1 is a title, line 2 is the header.
    header = [_norm(h) for h in rows[1]]
    index = {name: i for i, name in enumerate(header)}
    missing = [f for f in FIELDS if f not in index]
    if missing:
        print(f"{day}: unexpected header, missing {missing}")
        return None

    out = []
    for raw in rows[2:]:
        if not raw:
            continue
        client = _norm(raw[0])
        if client not in CLIENTS:
            continue
        record = {"date": day.isoformat(), "client": client}
        for field in FIELDS:
            value = raw[index[field]].strip().replace(",", "")
            record[field] = int(float(value)) if value else 0
        out.append(record)
    return out or None
