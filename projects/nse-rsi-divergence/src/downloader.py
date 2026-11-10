"""NSE bhavcopy downloader.

Fetches the daily full bhavcopy CSV from NSE archives and returns a normalised
DataFrame of equity-series OHLCV rows (EQ, and the other equity-ish series such
as BE/BZ/SM/ST, so a series switch never makes a name vanish).
"""
from __future__ import annotations

import io
import time
from datetime import date

import pandas as pd
import requests

import config


def _fmt(d: date) -> str:
    return d.strftime("%d%m%Y")


def bhavcopy_url(d: date) -> str:
    return config.BHAVCOPY_URL.format(ddmmyyyy=_fmt(d))


def fetch_bhavcopy(d: date, session: requests.Session | None = None) -> pd.DataFrame | None:
    """Download and parse the bhavcopy for a single date.

    Returns a DataFrame with columns:
        symbol, date, open, high, low, close, prev_close, volume, turnover_lacs
    or None if the file is unavailable (holiday / not yet published).
    """
    url = bhavcopy_url(d)
    sess = session or requests.Session()
    last_err: Exception | None = None
    for attempt in range(config.REQUEST_RETRIES):
        try:
            resp = sess.get(url, headers=config.HTTP_HEADERS, timeout=config.REQUEST_TIMEOUT)
            if resp.status_code == 404:
                return None  # no trading day / not published yet
            resp.raise_for_status()
            return _parse(resp.content, d)
        except requests.RequestException as e:  # transient
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    if last_err:
        raise last_err
    return None


def _parse(content: bytes, d: date) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(content), encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]

    rename = {
        "SYMBOL": "symbol", "SERIES": "series", "DATE1": "date_raw",
        "PREV_CLOSE": "prev_close", "OPEN_PRICE": "open", "HIGH_PRICE": "high",
        "LOW_PRICE": "low", "CLOSE_PRICE": "close", "TTL_TRD_QNTY": "volume",
        "TURNOVER_LACS": "turnover_lacs",
    }
    df = df.rename(columns=rename)

    needed = ["symbol", "series", "open", "high", "low", "close", "prev_close", "volume"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(f"bhavcopy missing columns: {missing}")

    # The NSE archive serves the PREVIOUS trading day's file (HTTP 200) for
    # non-trading dates. Trust the file's own DATE1, not the requested date, so
    # holidays are not stored as duplicates of the prior day.
    if "date_raw" in df.columns:
        raw = df["date_raw"].astype(str).str.strip()
        fdates = pd.to_datetime(raw, format="%d-%b-%Y", errors="coerce").dropna()
        if not fdates.empty and fdates.dt.date.iloc[0] != d:
            return None

    df = df[df["series"].astype(str).str.strip().isin(config.BHAVCOPY_SERIES)].copy()
    df["symbol"] = df["symbol"].astype(str).str.strip()
    df["date"] = d.isoformat()

    for c in ["open", "high", "low", "close", "prev_close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "turnover_lacs" not in df.columns:
        df["turnover_lacs"] = pd.NA
    else:
        df["turnover_lacs"] = pd.to_numeric(df["turnover_lacs"], errors="coerce")

    df = df.dropna(subset=["close"])
    return df[
        ["symbol", "date", "open", "high", "low", "close", "prev_close", "volume", "turnover_lacs"]
    ].reset_index(drop=True)
