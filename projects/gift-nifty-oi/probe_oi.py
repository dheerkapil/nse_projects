#!/usr/bin/env python3
"""Availability probe for the NSE IX daily GIFT Nifty report files.

Answers one question per file: does the report for a given trading date exist,
and what does the server say its publication time is?  It never downloads a
report - it sends a ranged request for a single byte and reads only the response
headers, then closes the connection without touching the body.

Two modes:

* default (first-seen logging): appends one row per newly seen file to
  data/probe_log.csv with the IST/UTC time it was first observed.
* BACKFILL=1: writes data/upload_times.csv with one row per file across
  LOOKBACK weekdays, including the server's Last-Modified header converted to
  IST.  This reconstructs publication times for past days in a single run.
"""
import csv
import datetime as dt
import email.utils
import http.cookiejar
import os
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, "data", "probe_log.csv")
BACKFILL_OUT = os.path.join(ROOT, "data", "upload_times.csv")
BASE = "https://www.nseix.com/api/content/daily_report"
PAGE = "https://www.nseix.com/markets/reports"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")

# (file prefix, minimum plausible size in bytes)
FILES = [("G_COMBINED_OI", 5000), ("G_T1_UL_PRICE", 100)]
LOOKBACK = int(os.environ.get("LOOKBACK", "6"))       # weekdays to inspect
BACKFILL = os.environ.get("BACKFILL", "").strip().lower() in ("1", "true", "yes")
PROBE_UNTIL = dt.date(2026, 11, 3)                    # first-seen mode only
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

_cj = http.cookiejar.CookieJar()
_op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_cj))
_op.addheaders = [("User-Agent", UA), ("Referer", PAGE)]


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def gmt_to_ist(value):
    """'Mon, 26 Oct 2026 16:14:58 GMT' -> '27-Oct-2026 21:44:58 IST'."""
    try:
        stamp = email.utils.parsedate_to_datetime(value)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=dt.timezone.utc)
        return stamp.astimezone(IST).strftime("%d-%b-%Y %H:%M:%S IST")
    except Exception:
        return ""


def probe(url):
    """Return (status, size_bytes, last_modified). The body is never read."""
    req = urllib.request.Request(url, headers={"Range": "bytes=0-0",
                                               "Accept": "*/*"})
    try:
        resp = _op.open(req, timeout=40)
    except urllib.error.HTTPError as exc:
        hdr = exc.headers or {}
        return exc.code, None, hdr.get("Last-Modified", "")
    except Exception as exc:                       # network / proxy problems
        return "ERR:" + type(exc).__name__, None, ""
    status, hdr = resp.status, resp.headers
    size = None
    content_range = hdr.get("Content-Range", "")   # e.g. "bytes 0-0/123456"
    if "/" in content_range:
        tail = content_range.rsplit("/", 1)[1].strip()
        if tail.isdigit():
            size = int(tail)
    if size is None:
        length = (hdr.get("Content-Length") or "").strip()
        if length.isdigit():
            size = int(length)
    last_modified = hdr.get("Last-Modified", "")
    resp.close()                                   # body deliberately unread
    return status, size, last_modified


def recent_weekdays(n):
    day = utcnow().astimezone(IST).date()
    out = []
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day)
        day -= dt.timedelta(days=1)
    return out


def warm():
    try:                                           # cookies, like fetch_oi.py
        _op.open(PAGE, timeout=30).read(2000)
    except Exception:
        pass


def run_backfill():
    warm()
    stamp = utcnow().astimezone(IST)
    rows = []
    for day in recent_weekdays(LOOKBACK):
        code = day.strftime("%d%m%Y")
        label = day.strftime("%d-%b-%Y")
        for prefix, min_size in FILES:
            status, size, last_modified = probe("%s/%s_%s.csv" % (BASE, prefix, code))
            present = (isinstance(status, int) and status in (200, 206)
                       and (size or 0) >= min_size)
            rows.append([label, prefix, "yes" if present else "no", status, size,
                         last_modified, gmt_to_ist(last_modified),
                         stamp.strftime("%Y-%m-%d %H:%M:%S")])
            print("%s %s present=%s status=%s size=%s published=%s"
                  % (label, prefix, present, status, size, gmt_to_ist(last_modified)))
    os.makedirs(os.path.dirname(BACKFILL_OUT), exist_ok=True)
    with open(BACKFILL_OUT, "w", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["file_date", "kind", "present", "status", "size",
                         "last_modified_utc", "published_ist", "probed_at_ist"])
        writer.writerows(rows)
    print("wrote %s (%d rows)" % (BACKFILL_OUT, len(rows)))
    return 0


def run_first_seen():
    stamp = utcnow()
    if stamp.astimezone(IST).date() > PROBE_UNTIL:
        print("probe window closed on %s - nothing to do" % PROBE_UNTIL)
        return 0
    warm()
    known = set()
    if os.path.exists(LOG):
        with open(LOG, newline="") as fh:
            for row in csv.DictReader(fh):
                known.add((row.get("file_date", ""), row.get("kind", "")))
    fresh = []
    for day in recent_weekdays(LOOKBACK):
        code = day.strftime("%d%m%Y")
        label = day.strftime("%d-%b-%Y")
        for prefix, min_size in FILES:
            status, size, last_modified = probe("%s/%s_%s.csv" % (BASE, prefix, code))
            present = (isinstance(status, int) and status in (200, 206)
                       and (size or 0) >= min_size)
            if present and (label, prefix) not in known:
                fresh.append([label, prefix,
                              stamp.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S"),
                              stamp.strftime("%Y-%m-%d %H:%M:%S"),
                              status, size, last_modified])
                print("%s %s: NEW (published %s)"
                      % (label, prefix, gmt_to_ist(last_modified)))
            else:
                print("%s %s: present=%s status=%s" % (label, prefix, present, status))
    if fresh:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        new_file = not os.path.exists(LOG)
        with open(LOG, "a", newline="") as fh:
            writer = csv.writer(fh, lineterminator="\n")
            if new_file:
                writer.writerow(["file_date", "kind", "first_seen_ist",
                                 "first_seen_utc", "status", "size",
                                 "last_modified"])
            writer.writerows(fresh)
        print("logged %d new file(s)" % len(fresh))
    else:
        print("no newly published file this run")
    return 0


def main():
    return run_backfill() if BACKFILL else run_first_seen()


if __name__ == "__main__":
    raise SystemExit(main())
