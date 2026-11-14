"""Build the participant-OI workbook.

Mirrors the analysis sheets of the old derivatives workbook — same column
layout, same group order — but without macros, without the hidden scratch sheet
and without the support/Power-Query plumbing. Everything is written as plain
values, so the file opens anywhere and needs no refresh.

Sheets: Nifty, conc, index fut, index opt, stock fut, stock opt, particip_oi.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import analysis
import store

OUT = Path(__file__).resolve().parent / "participant_oi.xlsx"
WINDOW = 120          # sessions shown on the analysis sheets

BOLD = Font(bold=True)
WHITE_BOLD = Font(bold=True, color="FFFFFF")
GROUP_FILL = PatternFill("solid", fgColor="1F3864")
SUB_FILL = PatternFill("solid", fgColor="D9E2F3")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)

INT = "#,##0"
PRICE = "#,##0.00"
RATIO = "0.0%"

CLIENTS = ("Client", "DII", "FII", "Pro")


def _pct(value):
    return None if value is None else round(value, 4)


def _series(history, closes, sessions=WINDOW):
    """The last `sessions` dates, oldest first, with metrics ready to write."""
    dates = sorted(history)[-sessions:]
    rows = []
    for i, d in enumerate(dates):
        rows.append({
            "date": d,
            "close": closes.get(d),
            "metrics": analysis.metrics_for(history[d]),
            "prev": history[dates[i - 1]] if i else {},
            "rows": history[d],
        })
    return rows


def _write_group(ws, col, top_row, title, sub_left, sub_right):
    """A merged group header with its two sub-headers and Long/Short row."""
    ws.merge_cells(start_row=top_row, start_column=col, end_row=top_row, end_column=col + 3)
    cell = ws.cell(row=top_row, column=col, value=title)
    cell.font = WHITE_BOLD
    cell.fill = GROUP_FILL
    cell.alignment = CENTER
    for offset in range(4):
        ws.cell(row=top_row, column=col + offset).fill = GROUP_FILL
    for offset, (label, span) in enumerate(((sub_left, 2), (sub_right, 2))):
        start = col + offset * 2
        ws.merge_cells(start_row=top_row + 1, start_column=start,
                       end_row=top_row + 1, end_column=start + 1)
        c = ws.cell(row=top_row + 1, column=start, value=label)
        c.font = BOLD
        c.fill = SUB_FILL
        c.alignment = CENTER
        for k in range(span):
            ws.cell(row=top_row + 1, column=start + k).fill = SUB_FILL
    for offset, label in enumerate(("Long", "Short", "Long", "Short")):
        c = ws.cell(row=top_row + 2, column=col + offset, value=label)
        c.font = BOLD
        c.alignment = CENTER


def _sheet_nifty(wb, rows):
    ws = wb.create_sheet("Nifty")
    for col, head in zip("ABCD", ("Date", "Close", "Change", "Change %")):
        c = ws[f"{col}1"]
        c.value = head
        c.font = WHITE_BOLD
        c.fill = GROUP_FILL
        c.alignment = CENTER
    closes = store.nifty_closes()
    for i, row in enumerate(rows, start=2):
        ws.cell(row=i, column=1, value=datetime.strptime(row["date"], "%Y-%m-%d").date())
        close = row["close"]
        ws.cell(row=i, column=2, value=close).number_format = PRICE
        earlier = [d for d in sorted(closes) if d < row["date"]]
        if close is not None and earlier:
            prev = closes[earlier[-1]]
            ws.cell(row=i, column=3, value=round(close - prev, 2)).number_format = PRICE
            ws.cell(row=i, column=4, value=round((close - prev) / prev, 6)).number_format = RATIO
    ws.freeze_panes = "A2"
    ws.column_dimensions["A"].width = 12
    for col in "BCD":
        ws.column_dimensions[col].width = 12
    return ws


def _sheet_futures(wb, name, rows, buckets, order):
    """index fut / stock fut: Day Action + Net OI per client."""
    ws = wb.create_sheet(name)
    ws["B1"] = f"{name.upper()} — net contracts"
    ws["B1"].font = BOLD
    for col, head in (("A", ""), ("B", "Date"), ("C", "Nifty Close"), ("D", "Change")):
        if head:
            c = ws[f"{col}2"]
            c.value = head
            c.font = WHITE_BOLD
            c.fill = GROUP_FILL
            c.alignment = CENTER

    long_key, short_key = buckets
    col = 6
    positions = {}
    for client in order:
        label = "Clients" if client == "Client" else client
        _write_group(ws, col, 1, f"{name.split()[0].title()} Fut {label}", "Day Action", "Net OI")
        positions[client] = col
        col += 5

    for i, row in enumerate(rows, start=4):
        ws.cell(row=i, column=1,
                value=datetime.strptime(row["date"], "%Y-%m-%d").strftime("%a"))
        ws.cell(row=i, column=2, value=datetime.strptime(row["date"], "%Y-%m-%d").date())
        ws.cell(row=i, column=3, value=row["close"]).number_format = PRICE
        if row["close"] is not None and i > 4:
            prev_close = rows[i - 5]["close"]
            if prev_close:
                ws.cell(row=i, column=4,
                        value=round(row["close"] - prev_close, 2)).number_format = PRICE
        for client, base in positions.items():
            today = row["rows"].get(client)
            prev = row["prev"].get(client)
            if not today:
                continue
            longs, shorts = today[long_key], today[short_key]
            ws.cell(row=i, column=base, value=(longs - prev[long_key]) if prev else None).number_format = INT
            ws.cell(row=i, column=base + 1, value=(shorts - prev[short_key]) if prev else None).number_format = INT
            ws.cell(row=i, column=base + 2, value=longs).number_format = INT
            ws.cell(row=i, column=base + 3, value=shorts).number_format = INT

    ws.freeze_panes = "F4"
    ws.column_dimensions["A"].width = 6
    for col_letter in ("B", "C", "D"):
        ws.column_dimensions[col_letter].width = 12
    return ws


def _sheet_options(wb, name, rows, order):
    """index opt / stock opt: Call and Put blocks per client."""
    ws = wb.create_sheet(name)
    ws["B1"] = f"{name.upper()} — net contracts"
    ws["B1"].font = BOLD
    for col, head in (("B", "Date"), ("C", "Nifty Close"), ("D", "Change")):
        c = ws[f"{col}2"]
        c.value = head
        c.font = WHITE_BOLD
        c.fill = GROUP_FILL
        c.alignment = CENTER

    prefix = "Index" if name == "index opt" else "Stock"
    blocks = {}
    col = 6
    for client in order:
        label = "Clients" if client == "Client" else client
        for side, (lk, sk) in (("Call", (f"Option {prefix} Call Long", f"Option {prefix} Call Short")),
                               ("Put", (f"Option {prefix} Put Long", f"Option {prefix} Put Short"))):
            _write_group(ws, col, 1, f"{label} {side}", "Day Action", f"{side} Net OI")
            blocks[(client, side)] = (col, lk, sk)
            col += 5

    for i, row in enumerate(rows, start=4):
        ws.cell(row=i, column=1,
                value=datetime.strptime(row["date"], "%Y-%m-%d").strftime("%a"))
        ws.cell(row=i, column=2, value=datetime.strptime(row["date"], "%Y-%m-%d").date())
        ws.cell(row=i, column=3, value=row["close"]).number_format = PRICE
        if row["close"] is not None and i > 4:
            prev_close = rows[i - 5]["close"]
            if prev_close:
                ws.cell(row=i, column=4,
                        value=round(row["close"] - prev_close, 2)).number_format = PRICE
        for (client, side), (base, lk, sk) in blocks.items():
            today = row["rows"].get(client)
            prev = row["prev"].get(client)
            if not today:
                continue
            ws.cell(row=i, column=base,
                    value=(today[lk] - prev[lk]) if prev else None).number_format = INT
            ws.cell(row=i, column=base + 1,
                    value=(today[sk] - prev[sk]) if prev else None).number_format = INT
            ws.cell(row=i, column=base + 2, value=today[lk]).number_format = INT
            ws.cell(row=i, column=base + 3, value=today[sk]).number_format = INT

    # Market OI and the FII put/call ratio, as the original sheet had.
    market_col = col
    ws.merge_cells(start_row=1, start_column=market_col, end_row=1, end_column=market_col + 2)
    c = ws.cell(row=1, column=market_col, value="Market OI")
    c.font = WHITE_BOLD
    c.fill = GROUP_FILL
    c.alignment = CENTER
    for k in range(3):
        ws.cell(row=1, column=market_col + k).fill = GROUP_FILL
    for offset, label in enumerate(("CE", "PE", "PCR")):
        cell = ws.cell(row=3, column=market_col + offset, value=label)
        cell.font = BOLD
        cell.fill = SUB_FILL
        cell.alignment = CENTER

    pcr_col = market_col + 4
    ws.merge_cells(start_row=1, start_column=pcr_col, end_row=1, end_column=pcr_col + 1)
    c = ws.cell(row=1, column=pcr_col, value="FII PCR")
    c.font = WHITE_BOLD
    c.fill = GROUP_FILL
    c.alignment = CENTER
    for k in range(2):
        ws.cell(row=1, column=pcr_col + k).fill = GROUP_FILL
    for offset, label in enumerate(("Put/Call", "Bull/Bear")):
        cell = ws.cell(row=3, column=pcr_col + offset, value=label)
        cell.font = BOLD
        cell.fill = SUB_FILL
        cell.alignment = CENTER

    cl_key, cs_key = f"Option {prefix} Call Long", f"Option {prefix} Call Short"
    pl_key, ps_key = f"Option {prefix} Put Long", f"Option {prefix} Put Short"
    for i, row in enumerate(rows, start=4):
        call_oi = sum(v[cl_key] + v[cs_key] for v in row["rows"].values())
        put_oi = sum(v[pl_key] + v[ps_key] for v in row["rows"].values())
        ws.cell(row=i, column=market_col, value=call_oi or None).number_format = INT
        ws.cell(row=i, column=market_col + 1, value=put_oi or None).number_format = INT
        if call_oi:
            ws.cell(row=i, column=market_col + 2,
                    value=round(put_oi / call_oi, 4)).number_format = "0.00"
        fii = row["rows"].get("FII")
        if fii:
            fii_call = fii[cl_key] + fii[cs_key]
            fii_put = fii[pl_key] + fii[ps_key]
            if fii_call:
                ratio = fii_put / fii_call
                ws.cell(row=i, column=pcr_col, value=round(ratio, 4)).number_format = "0.00"
                ws.cell(row=i, column=pcr_col + 1,
                        value="Bullish" if ratio > 1 else "Bearish")

    ws.freeze_panes = "F4"
    ws.column_dimensions["A"].width = 6
    for col_letter in ("B", "C", "D"):
        ws.column_dimensions[col_letter].width = 12
    return ws


def _sheet_conc(wb, rows):
    """Share of gross OI held by each client, per segment."""
    ws = wb.create_sheet("conc")
    ws["B2"] = "Date"
    ws["C2"] = "Nifty Close"
    ws["D2"] = "Change"

    # All four client types in every segment, so each row of shares sums to 100%.
    segments = [
        ("Index Options", 5, ("Client", "Pro", "FII", "DII"),
         ("Option Index Call Long", "Option Index Call Short",
          "Option Index Put Long", "Option Index Put Short")),
        ("Index Futures", 10, ("Client", "Pro", "FII", "DII"),
         ("Future Index Long", "Future Index Short")),
        ("Stock Futures", 15, ("Client", "Pro", "FII", "DII"),
         ("Future Stock Long", "Future Stock Short")),
        ("Stock Options", 20, ("Client", "Pro", "FII", "DII"),
         ("Option Stock Call Long", "Option Stock Call Short",
          "Option Stock Put Long", "Option Stock Put Short")),
    ]
    for title, start_col, clients, fields in segments:
        ws.merge_cells(start_row=1, start_column=start_col,
                       end_row=1, end_column=start_col + len(clients) - 1)
        c = ws.cell(row=1, column=start_col, value=title)
        c.font = WHITE_BOLD
        c.fill = GROUP_FILL
        c.alignment = CENTER
        for k in range(len(clients)):
            ws.cell(row=1, column=start_col + k).fill = GROUP_FILL
            sub = ws.cell(row=2, column=start_col + k,
                          value="Clients" if clients[k] == "Client" else clients[k])
            sub.font = BOLD
            sub.fill = SUB_FILL
            sub.alignment = CENTER

    ws["AC1"] = "Total (gross OI, contracts)"
    ws["AA1"].font = WHITE_BOLD
    ws["AA1"].fill = GROUP_FILL
    for offset, label in enumerate(("Index", "Stocks", "Index + Stocks")):
        c = ws.cell(row=2, column=29 + offset, value=label)
        c.font = BOLD
        c.fill = SUB_FILL
        c.alignment = CENTER

    for i, row in enumerate(rows, start=3):
        ws.cell(row=i, column=1,
                value=datetime.strptime(row["date"], "%Y-%m-%d").strftime("%a"))
        ws.cell(row=i, column=2, value=datetime.strptime(row["date"], "%Y-%m-%d").date())
        ws.cell(row=i, column=3, value=row["close"]).number_format = PRICE
        if row["close"] is not None and i > 3:
            prev_close = rows[i - 4]["close"]
            if prev_close:
                ws.cell(row=i, column=4,
                        value=round(row["close"] - prev_close, 2)).number_format = PRICE

        index_total = stock_total = 0
        for title, start_col, clients, fields in segments:
            gross = {}
            for client, values in row["rows"].items():
                gross[client] = sum(values[f] for f in fields)
            total = sum(gross.values())
            for offset, client in enumerate(clients):
                share = gross.get(client, 0) / total if total else None
                cell = ws.cell(row=i, column=start_col + offset, value=_pct(share))
                cell.number_format = RATIO
            if title.startswith("Index"):
                index_total += total
            else:
                stock_total += total

        ws.cell(row=i, column=29, value=index_total // 2 or None).number_format = INT
        ws.cell(row=i, column=30, value=stock_total // 2 or None).number_format = INT
        ws.cell(row=i, column=31, value=(index_total + stock_total) // 2 or None).number_format = INT

    ws.freeze_panes = "E3"
    ws.column_dimensions["A"].width = 6
    for col_letter in ("B", "C", "D"):
        ws.column_dimensions[col_letter].width = 12
    for col in range(5, 32):
        ws.column_dimensions[get_column_letter(col)].width = 9
    return ws


def _sheet_raw(wb, history):
    ws = wb.create_sheet("participant_oi")
    headers = ["Date", "Client Type"] + [f.replace("Option ", "Opt ").replace("Future ", "Fut ")
                                         for f in store.FIELDS]
    for col, head in enumerate(headers, start=1):
        c = ws.cell(row=1, column=col, value=head)
        c.font = WHITE_BOLD
        c.fill = GROUP_FILL
        c.alignment = CENTER
    row = 2
    for d in sorted(history):
        for client in CLIENTS:
            values = history[d].get(client)
            if not values:
                continue
            ws.cell(row=row, column=1, value=datetime.strptime(d, "%Y-%m-%d").date())
            ws.cell(row=row, column=2, value=client)
            for offset, field in enumerate(store.FIELDS, start=3):
                ws.cell(row=row, column=offset, value=values[field]).number_format = INT
            row += 1
    ws.freeze_panes = "C2"
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 12
    for col in range(3, 3 + len(store.FIELDS)):
        ws.column_dimensions[get_column_letter(col)].width = 13
    return ws


def build(history=None, closes=None, path=None):
    history = history or store.load()
    closes = closes if closes is not None else store.nifty_closes()
    rows = _series(history, closes)
    if not rows:
        raise SystemExit("no history to write")

    wb = Workbook()
    wb.remove(wb.active)
    _sheet_nifty(wb, rows)
    _sheet_conc(wb, rows)
    _sheet_futures(wb, "index fut", rows,
                   ("Future Index Long", "Future Index Short"),
                   ("Client", "DII", "Pro", "FII"))
    _sheet_options(wb, "index opt", rows, ("Client", "FII", "Pro", "DII"))
    _sheet_futures(wb, "stock fut", rows,
                   ("Future Stock Long", "Future Stock Short"),
                   ("Client", "FII", "DII", "Pro"))
    _sheet_options(wb, "stock opt", rows, ("Client", "Pro", "FII", "DII"))
    _sheet_raw(wb, history)

    target = Path(path) if path else OUT
    wb.save(target)
    return target


if __name__ == "__main__":
    print("written:", build())
