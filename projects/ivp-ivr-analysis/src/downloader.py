"""NSE F&O bhavcopy download.

Two things this module is careful about:

* **Not-published is not the same as failed.** The UDiFF F&O bhavcopy is posted
  around 18:00 IST (later on monthly-expiry Thursdays), so during the early
  evening slots an HTTP 404 simply means "not out yet" — the caller should try
  again later, not treat the day as broken. A network error, by contrast, is
  transient and worth retrying inside the same run.

* **A downloaded file is validated before it is trusted.** A 200 response that
  turns out to be an HTML error page or a truncated archive is treated as an
  error rather than silently processed into garbage IVs.
"""

import time
import zipfile
from datetime import datetime, timedelta
from io import BytesIO

import pandas as pd
import requests

# Result statuses returned by fetch_bhavcopy()
OK = "ok"
NOT_PUBLISHED = "not_published"
ERROR = "error"

_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

# Columns the downstream contract-picker needs to do its job.
_REQUIRED_COLS = {'TckrSymb', 'ClsPric', 'StrkPric', 'OptnTp', 'XpryDt'}
_MIN_ROWS = 50          # a real F&O bhavcopy has thousands of rows


def _urls(date_str):
    return [
        f"https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{date_str}_F_0000.csv.zip",
        f"https://nsearchives.nseindia.com/content/fo/bhavcopy_nse_fo_0_0_0_{date_str}_f_0000.csv.zip",
    ]


def _parse_zip(content):
    """Return a validated DataFrame, or raise ValueError."""
    with zipfile.ZipFile(BytesIO(content)) as z:
        csv_files = [f for f in z.namelist() if f.endswith('.csv')]
        if not csv_files:
            raise ValueError("no CSV inside the archive")
        with z.open(csv_files[0]) as f:
            df = pd.read_csv(f)

    missing = _REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(f"missing expected columns: {sorted(missing)}")
    if len(df) < _MIN_ROWS:
        raise ValueError(f"only {len(df)} rows — looks truncated")
    return df


def fetch_bhavcopy(date, attempts=3, backoff=5):
    """
    Download the F&O bhavcopy for `date` (a datetime/date).

    Returns (df, status):
        (DataFrame, OK)            — validated data
        (None, NOT_PUBLISHED)      — NSE has no file for this date (404)
        (None, ERROR)              — network/parse failure after all attempts
    """
    date_str = date.strftime("%Y%m%d")

    for attempt in range(1, attempts + 1):
        saw_404 = False
        for url in _urls(date_str):
            try:
                print(f"Downloading F&O bhavcopy: {url} (attempt {attempt}/{attempts})")
                r = requests.get(url, timeout=60, headers=_HEADERS, allow_redirects=True)
            except requests.RequestException as e:
                print(f"  network error: {e}")
                continue

            if r.status_code == 404:
                saw_404 = True
                continue
            if r.status_code != 200:
                print(f"  HTTP {r.status_code}")
                continue

            try:
                df = _parse_zip(r.content)
            except Exception as e:
                print(f"  downloaded file rejected: {e}")
                continue

            print(f"  OK — {len(df)} rows")
            return df, OK

        if saw_404:
            # A genuine "not published yet" — no point hammering NSE in this run.
            print(f"  no bhavcopy published for {date_str} (HTTP 404)")
            return None, NOT_PUBLISHED

        if attempt < attempts:
            print(f"  retrying in {backoff}s...")
            time.sleep(backoff)

    print(f"  giving up on {date_str} after {attempts} attempts")
    return None, ERROR


def download_fno_bhavcopy(date=None):
    """Back-compat wrapper: DataFrame on success, else None."""
    df, _ = fetch_bhavcopy(date or datetime.now())
    return df


def download_historical_bhavcopy(start_date, end_date):
    """Download F&O bhavcopy for a date range (used by the backfill script)."""
    all_data = []
    current = start_date

    while current <= end_date:
        if current.weekday() < 5:                       # skip weekends
            print(f"Processing: {current.strftime('%Y-%m-%d')}")
            df, _ = fetch_bhavcopy(current, attempts=2)
            if df is not None and not df.empty:
                df['date'] = current.strftime('%Y-%m-%d')
                all_data.append(df)
            time.sleep(3)
        current += timedelta(days=1)

    if all_data:
        return pd.concat(all_data, ignore_index=True)
    return None
