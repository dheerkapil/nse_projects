#!/usr/bin/env python3
"""
GIFT Nifty OI + Nifty underlying fetcher (scheduled hourly 17:00-23:00 IST).

Each run:
  * weekends / coded holidays -> nothing
  * if today's OI AND Nifty rows are already in -> nothing (no further fetches)
  * otherwise walk the last LOOKBACK weekdays (newest first) and fill EVERY
    missing day -- today's file may not be published yet, but older gaps still
    get filled.  (Earlier versions returned early on that, which is why gaps
    could persist.)
Both files come from nseix.com, so there is no external price dependency.
"""
import os, csv, sys, time, datetime as dt
import urllib.request, http.cookiejar

ROOT   = os.path.dirname(os.path.abspath(__file__))
DATA   = os.path.join(ROOT, "data")
RAW    = os.path.join(DATA, "raw")
MASTER = os.path.join(DATA, "oi_master.csv")
NIFTY  = os.path.join(DATA, "nifty_daily.csv")
HOLID  = os.path.join(DATA, "holidays.txt")
BASE   = "https://www.nseix.com/api/content/daily_report"
PAGE   = "https://www.nseix.com/markets/reports"
UA     = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124 Safari/537.36")
MINSIZE = 5000
LOOKBACK = 15

os.makedirs(RAW, exist_ok=True)
_cj = http.cookiejar.CookieJar()
_op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_cj))
_op.addheaders = [("User-Agent", UA), ("Referer", PAGE)]

def ist_today():
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)).date()

def canon(s):
    try: return dt.datetime.strptime(s.strip(), "%d-%b-%Y").strftime("%d-%b-%Y")
    except Exception: return s.strip()

def load_holidays():
    hol = set()
    if os.path.exists(HOLID):
        for line in open(HOLID):
            line = line.split("#")[0].strip()
            if line:
                try: hol.add(dt.datetime.strptime(line, "%d-%b-%Y").date())
                except Exception: pass
    return hol

def warm():
    try: _op.open(PAGE, timeout=30).read()
    except Exception: pass

def recent_weekdays(n):
    d, out = ist_today(), []
    while len(out) < n:
        if d.weekday() < 5: out.append(d)
        d -= dt.timedelta(days=1)
    return out

def _get(url, path, minsize):
    if os.path.exists(path) and os.path.getsize(path) > minsize:
        return path
    for a in range(3):
        try:
            data = _op.open(url, timeout=40).read()
            if len(data) > minsize:
                open(path, "wb").write(data); return path
        except Exception:
            time.sleep(5 * (a + 1))
    return None

def get_oi(day):
    ds = day.strftime("%d%m%Y")
    return _get(f"{BASE}/G_COMBINED_OI_{ds}.csv", os.path.join(RAW, f"G_COMBINED_OI_{ds}.csv"), MINSIZE)

def get_ul(day):
    ds = day.strftime("%d%m%Y")
    return _get(f"{BASE}/G_T1_UL_PRICE_{ds}.csv", os.path.join(RAW, f"G_T1_UL_PRICE_{ds}.csv"), 100)

def parse_oi(path):
    rows = list(csv.reader(open(path, encoding="utf-8", errors="ignore")))
    date = canon(rows[0][0]); fut = {}
    for r in rows[1:]:
        if len(r) >= 7 and r[0] == "FUTIDX" and r[1] == "NIFTY":
            v = r[6].strip().lstrip("-"); fut[r[2]] = int(v) if v.isdigit() else 0
    return (date, fut) if fut else (None, None)

def parse_ul(path):
    for r in csv.reader(open(path, encoding="utf-8", errors="ignore")):
        if len(r) >= 3 and r[1].strip().upper() == "NIFTY":
            try: return canon(r[0]), float(r[2])
            except Exception: return None, None
    return None, None

def seen(path):
    if not os.path.exists(path): return set()
    return {canon(r["date"]) for r in csv.DictReader(open(path))}

def append(path, header, row):
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        # lineterminator="\n": the excel dialect default is \r\n, which left the
        # appended tail with CRLF endings while the seeded body used LF.
        w = csv.writer(f, lineterminator="\n")
        if new: w.writerow(header)
        w.writerow(row)

def _date_key(s):
    try: return (0, dt.datetime.strptime(s, "%d-%b-%Y"))
    except Exception: return (1, s)

def normalise(path, header):
    """Rewrite a date-keyed CSV in chronological order with LF endings.

    main() backfills the last LOOKBACK weekdays newest-first, so a run that
    fills several gaps appends them in descending date order. Sorting on write
    keeps "last row == newest" true and makes the file self-healing. Idempotent:
    an already-sorted file is rewritten byte-identically, so git sees no diff.
    """
    if not os.path.exists(path):
        return 0
    try:
        rows = list(csv.DictReader(open(path, newline="")))
        seen_d = {}
        for r in rows:
            d = canon(r.get("date", ""))
            if d: seen_d[d] = r
        ordered = [seen_d[k] for k in sorted(seen_d, key=_date_key)]
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=header, lineterminator="\n")
            w.writeheader()
            for r in ordered:
                w.writerow({k: r.get(k, "") for k in header})
        return len(ordered)
    except Exception as e:
        print(f"normalise({os.path.basename(path)}) skipped: {e}")
        return 0

def do_day(day, have_oi, have_nx):
    ds = canon(day.strftime("%d-%b-%Y"))
    need_oi, need_nx = ds not in have_oi, ds not in have_nx
    if not need_oi and not need_nx:
        return 0                                   # already have it - no download
    added = 0
    if need_oi:
        p = get_oi(day)
        if p:
            date, fut = parse_oi(p)
            if date and date not in have_oi:
                append(MASTER, ["date", "nifty_fut_total_oi"], [date, sum(fut.values())])
                have_oi.add(date); added += 1
                print(f"{date}: OI {sum(fut.values()):,}")
    if need_nx:
        q = get_ul(day)
        if q:
            date, val = parse_ul(q)
            if date and date not in have_nx:
                append(NIFTY, ["date", "nifty"], [date, val])
                have_nx.add(date); added += 1
                print(f"{date}: nifty {val}")
    return added

def main():
    today = ist_today()
    hol = load_holidays()
    have_oi, have_nx = seen(MASTER), seen(NIFTY)
    tds = canon(today.strftime("%d-%b-%Y"))
    skip_today = today.weekday() >= 5 or today in hol
    if not skip_today and tds in have_oi and tds in have_nx:
        print(f"already have {today} - no further fetches today"); return
    if skip_today:
        print(f"{today} is a weekend/holiday - backfilling gaps only")

    warm()
    added = 0
    for day in recent_weekdays(LOOKBACK):          # newest first; fills ALL gaps
        if day.weekday() >= 5 or day in hol: continue
        if skip_today and day == today: continue
        added += do_day(day, have_oi, have_nx)
    if added == 0:
        print("nothing new yet - the next run will retry")
    normalise(MASTER, ["date", "nifty_fut_total_oi"])
    normalise(NIFTY, ["date", "nifty"])
    print(f"done - added {added}; master {len(have_oi)} dates, nifty {len(have_nx)} dates")

if __name__ == "__main__":
    main()
