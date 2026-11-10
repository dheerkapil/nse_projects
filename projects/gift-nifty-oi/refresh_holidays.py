#!/usr/bin/env python3
"""
Refresh the coded NSE IX (GIFT Nifty) holiday list from nseix.com, weekly.
Unions whatever it finds with the existing list, so a parse miss never
drops a known holiday. Standard library only.
"""
import re, os, urllib.request, http.cookiejar, datetime as dt

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
HOL  = os.path.join(DATA, "holidays.txt")
URL  = "https://www.nseix.com/resources/holidays"
UA   = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
MON  = {m.lower(): i for i, m in enumerate(
        ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], 1)}

def existing():
    s = set()
    if os.path.exists(HOL):
        for l in open(HOL):
            l = l.split("#")[0].strip()
            if l:
                try: s.add(dt.datetime.strptime(l, "%d-%b-%Y").date())
                except Exception: pass
    return s

def fetch_dates():
    out = set()
    try:
        cj = http.cookiejar.CookieJar()
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        op.addheaders = [("User-Agent", UA)]
        html = op.open(URL, timeout=40).read().decode("utf-8", "ignore")
        for m in re.finditer(r'(\d{1,2})[\s\-/]+([A-Za-z]{3,9})[\s\-/]+(\d{4})', html):
            d, mo, y = m.groups()
            mi = MON.get(mo[:3].lower())
            if mi:
                try:
                    d0 = dt.date(int(y), mi, int(d))
                    # only plausible trading-day closures: weekdays, within +/-2 years
                    if d0.weekday() < 5 and (dt.date.today() - dt.timedelta(days=730)) <= d0 <= (dt.date.today() + dt.timedelta(days=730)):
                        out.add(d0)
                except Exception: pass
    except Exception as e:
        print("fetch failed:", e)
    return out

def main():
    found = fetch_dates()
    print("dates parsed from nseix.com:", len(found))
    all_dates = sorted(existing() | found)
    os.makedirs(DATA, exist_ok=True)
    with open(HOL, "w") as f:
        f.write("# NSE IX (GIFT Nifty) trading closures - one date per line (DD-MMM-YYYY)\n")
        f.write("# weekends are skipped automatically; auto-refreshed weekly\n")
        for d in all_dates:
            f.write(d.strftime("%d-%b-%Y") + "\n")
    print("holiday list now has", len(all_dates), "dates")

if __name__ == "__main__":
    main()
