"""Render the workbook: Parameters, Sheet1 (URL builder), Sheet2 (data)."""

from __future__ import annotations

import os
from datetime import date, timedelta

from openpyxl import Workbook
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.filters import AutoFilter, DateGroupItem, FilterColumn, Filters
from openpyxl.worksheet.table import Table

from transform import N_COI, N_STRIKES

PREFIX = "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_"
SUFFIX = "_F_0000.csv.zip"
HEADERS = ["TradDt", "XpryDt", "TckrSymb", "StrkPric", "OptnTp", "FinInstrmNm", "OpnPric",
           "HghPric", "LwPric", "ClsPric", "LastPric", "PrvsClsgPric", "UndrlygPric",
           "SttlmPric", "OI lots", "COI lots", "COI/OI", "TtlTradgVol", "NewBrdLotQty",
           "Vol/COI", "Traded Value by Vol", "Traded Value by COI", "Gap"]
WIDTHS = [9.85546875, 10, 14.5703125, 10, 9.85546875, 23, 10.28515625, 10, 9, 9.140625, 10,
          13.85546875, 13.5703125, 11.28515625, 9, 12.42578125, 10, 13.42578125, 16.42578125,
          10.28515625, 20, 20, 6.85546875]
ACCT2 = '_ * #,##0.00_ ;_ * \\-#,##0.00_ ;_ * "-"??_ ;_ @_'
FMT = {1: "d-mmm-yy", 2: "d-mmm-yy", 15: ACCT2, 16: ACCT2, 17: "0.0000", 20: "0.00",
       21: "#,##0", 22: "#,##0", 23: ACCT2}
FLOAT_COLS = {7, 8, 9, 10, 11, 12, 13, 14}

F_BOLD_WHITE = Font(name="Calibri", size=11, bold=True, color="FFFFFFFF")
F_BOLD = Font(name="Calibri", size=11, bold=True)
F_NOTE = Font(name="Calibri", size=9, italic=True)
HEAD_FILL = PatternFill("solid", fgColor="FF1F3864")


def _parameters(wb):
    sp = wb.active
    sp.title = "Parameters"
    for col, head in (("A", "Parameter"), ("B", "Value")):
        c = sp[f"{col}1"]
        c.value = head
        c.font = F_BOLD_WHITE
        c.fill = HEAD_FILL
        c.alignment = Alignment(horizontal="center")
    sp["A2"] = "No. of Strikes to consider"; sp["B2"] = N_STRIKES
    sp["A3"] = "No. of Threshold Contracts"; sp["B3"] = N_COI
    for r in (2, 3):
        sp[f"A{r}"].font = F_BOLD
        sp[f"B{r}"].alignment = Alignment(horizontal="center")
    sp["A5"] = ("Strikes: rows within this many strikes of the money are dropped, on the call "
                "side and the put side separately, per symbol and expiry.")
    sp["A6"] = ("Threshold: rows whose change in open interest is below this many contracts "
                "(lots) are dropped.")
    sp["A7"] = ("The data sheet shows the latest session only; the other sessions are in the "
                "sheet, hidden by the filter on TradDt. Clear that filter to see them.")
    sp["A8"] = "These values were used to build this file; changing them requires rebuilding it."
    for r in (5, 6, 7, 8):
        sp[f"A{r}"].font = F_NOTE
    sp.column_dimensions["A"].width = 118
    sp.column_dimensions["B"].width = 12


def _urls(wb, first, last):
    s1 = wb.create_sheet("Sheet1")
    d, r = first, 1
    while d <= last:
        s1.cell(row=r, column=1, value=PREFIX)
        s1.cell(row=r, column=2, value=f'=TEXT(E{r},"yyyymmdd")')
        s1.cell(row=r, column=3, value=SUFFIX)
        s1.cell(row=r, column=4, value=f'=A{r}&B{r}&C{r}')
        s1.cell(row=r, column=5, value=d).number_format = "d-mmm-yy"
        r += 1
        d += timedelta(days=1)
    for col, w in zip("ABCDE", [87.7109375, 9.140625, 14.5703125, 87.7109375, 9.85546875]):
        s1.column_dimensions[col].width = w


def build(rows, path):
    """rows: 20-field history rows. Writes the workbook and returns the path."""
    # sort: COI/OI descending, then COI descending
    rows = sorted(rows, key=lambda r: (-(float(r[15]) / float(r[14]) if float(r[14]) else 0),
                                       -float(r[15])))

    wb = Workbook()
    _parameters(wb)
    latest = max(r[0] for r in rows)
    d = date.fromisoformat(latest)
    _urls(wb, date(d.year, d.month, 1), date(d.year + (d.month == 12), d.month % 12 + 1, 1)
          - timedelta(days=1))

    s2 = wb.create_sheet("Sheet2")
    for i, h in enumerate(HEADERS, start=1):
        s2.cell(row=1, column=i, value=h)

    for n, row in enumerate(rows, start=2):
        cls = float(row[9]); oi_lots = float(row[14]); coi_lots = float(row[15])
        vol = float(row[16]); lot = float(row[17])
        coi_oi = round(coi_lots / oi_lots, 4) if oi_lots else None
        values = [row[0], row[1], row[2], int(row[3]), row[4], row[5],
                  float(row[6]), float(row[7]), float(row[8]), cls,
                  float(row[10]), float(row[11]), float(row[12]), float(row[13]),
                  oi_lots, coi_lots, coi_oi, vol, lot, round(float(row[18]), 2),
                  round(cls * vol * lot), round(coi_lots * lot * cls), float(row[19])]
        for i, v in enumerate(values, start=1):
            if i in (1, 2):
                y, m, dd = v.split("-")
                cell = s2.cell(row=n, column=i, value=date(int(y), int(m), int(dd)))
            elif i == 4:
                cell = s2.cell(row=n, column=i, value=int(v))
            elif i in FLOAT_COLS or i in (15, 16, 17, 20, 23):
                cell = s2.cell(row=n, column=i, value=v)
            else:
                cell = s2.cell(row=n, column=i, value=v)
            fmt = FMT.get(i)
            if fmt:
                cell.number_format = fmt
        if row[0] != latest:
            s2.row_dimensions[n].hidden = True

    for col, w in zip(range(1, len(WIDTHS) + 1), WIDTHS):
        s2.column_dimensions[get_column_letter(col)].width = w
    s2.column_dimensions["F"].hidden = True
    s2.column_dimensions[get_column_letter(len(HEADERS))].hidden = True

    last_row = len(rows) + 1
    ref = f"A1:{get_column_letter(len(HEADERS))}{last_row}"
    y, m, dd = (int(x) for x in latest.split("-"))
    tbl = Table(displayName="data", ref=ref)
    tbl.autoFilter = AutoFilter(
        ref=ref,
        filterColumn=[FilterColumn(colId=0, filters=Filters(
            dateGroupItem=[DateGroupItem(year=y, month=m, day=dd, dateTimeGrouping="day")]))])
    s2.add_table(tbl)

    for col in ("U", "V"):
        s2.conditional_formatting.add(
            f"{col}2:{col}{last_row}",
            ColorScaleRule(start_type="min", start_color="F8696B",
                           mid_type="percentile", mid_value=50, mid_color="FFEB84",
                           end_type="max", end_color="63BE7B"))

    wb.calculation.fullCalcOnLoad = True
    wb.active = 0
    wb.save(path)
    _patch_styles(path)
    return path


def _patch_styles(path):
    """Excel always writes <dxfs count="0"/>; openpyxl omits it, and Excel then
    repairs the styles part on open."""
    import zipfile
    tmp = path + ".tmp"
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "xl/styles.xml":
                txt = data.decode("utf-8")
                if "<dxfs" not in txt:
                    txt = txt.replace("</cellStyles>", '</cellStyles><dxfs count="0"/>', 1)
                    data = txt.encode("utf-8")
            zout.writestr(item, data)
    os.replace(tmp, path)
