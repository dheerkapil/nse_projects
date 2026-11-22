"""Download and parse one session of the NSE F&O bhavcopy (UDiFF format)."""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import date

import requests

URL = ("https://nsearchives.nseindia.com/content/fo/"
       "BhavCopy_NSE_FO_0_0_0_{ymd}_F_0000.csv.zip")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"}


def fetch(day: date):
    """Stock-option rows for `day`, or None if the file isn't published yet."""
    url = URL.format(ymd=day.strftime("%Y%m%d"))
    try:
        resp = requests.get(url, headers=HEADERS, timeout=90)
    except requests.RequestException as exc:
        print(f"{day}: download failed ({exc})")
        return None
    if resp.status_code != 200 or len(resp.content) < 5000:
        print(f"{day}: not published yet (HTTP {resp.status_code})")
        return None
    try:
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
    except zipfile.BadZipFile:
        print(f"{day}: not a zip - treating as not published")
        return None
    name = zf.namelist()[0]
    text = zf.read(name).decode("utf-8-sig", "ignore")
    rows = [r for r in csv.DictReader(io.StringIO(text)) if r["FinInstrmTp"] == "STO"]
    print(f"{day}: {len(rows):,} stock-option rows downloaded")
    return rows
