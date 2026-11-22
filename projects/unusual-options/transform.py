"""Turn one session's raw bhavcopy rows into the sheet's rows.

Filters, in order:
  1. change in open interest must be non-zero, so Vol/COI is defined and positive
  2. the strike must be OTM by at least N_STRIKES strikes on its side
  3. change in open interest must be at least N_COI contracts (lots)
"""

from __future__ import annotations

from collections import defaultdict

N_STRIKES = 3
N_COI = 5


def select(rows, n_strikes=N_STRIKES, n_coi=N_COI):
    """Return rows in the sheet's 20-field layout."""
    strikes = defaultdict(set)
    spot = {}
    for r in rows:
        try:
            k, s = float(r["StrkPric"]), float(r["UndrlygPric"])
        except ValueError:
            continue
        strikes[(r["TckrSymb"], r["XpryDt"], r["OptnTp"])].add(round(k))
        spot[r["TckrSymb"]] = s

    keep = set()
    for (sym, xpry, typ), ks in strikes.items():
        s = spot.get(sym)
        if not s:
            continue
        ordered = (sorted(k for k in ks if k > s) if typ == "CE"
                   else sorted((k for k in ks if k < s), reverse=True))
        for k in ordered[n_strikes:]:
            keep.add((sym, xpry, typ, k))

    out = []
    for r in rows:
        try:
            lot = float(r["NewBrdLotQty"]); coi = float(r["ChngInOpnIntrst"])
            vol = float(r["TtlTradgVol"]); oi = float(r["OpnIntrst"])
            strk = float(r["StrkPric"]); und = float(r["UndrlygPric"])
        except ValueError:
            continue
        if not lot or not coi:
            continue
        vol_coi = vol / (coi / lot)
        if not (vol_coi > 0):
            continue
        strike = int(round(strk))
        if (r["TckrSymb"], r["XpryDt"], r["OptnTp"], strike) not in keep:
            continue
        coi_lots = coi / lot
        if coi_lots < n_coi:
            continue
        out.append([r["TradDt"], r["XpryDt"], r["TckrSymb"], strike, r["OptnTp"],
                    r["FinInstrmNm"], r["OpnPric"], r["HghPric"], r["LwPric"],
                    r["ClsPric"], r["LastPric"], r["PrvsClsgPric"], und,
                    r["SttlmPric"], oi / lot, coi_lots, vol, lot, vol_coi,
                    strike - und])
    return out
