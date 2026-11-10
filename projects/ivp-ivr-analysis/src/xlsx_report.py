"""Excel matrix report — the IVP/IVR sheet in the user's template layout.

Layout (one block per stock, ranked by today's IVP, highest first):

    DAYS | STOCK | PARA. | <d0> | <d-1> | <d-2> | … | <d-n>
     252 |   X   |  IVP  |  98% |  92%  |  95%  | … |  71%
         |       |  IVR  |  100 |  95   |  96   | … |  63
    ─────────────────────────────────────────────────────────────  (navy rule)

DAYS, STOCK and PARA. are the first three columns so they are what stays pinned
when the sheet scrolls right; the dates scroll underneath them. (Excel/Sheets
can only freeze columns from the left edge, so the columns that must stay
visible have to come first.)

There is one column per trading day on record — the full rolling year of
per-day files, not just the most recent few.

Each IVP/IVR row carries a 3-colour scale (red → yellow → green) across the
date columns, so within a stock the highest reading is green and the lowest
red — the same conditional formatting the template uses.

IVP is written as a fraction with a '0%' number format (0.98 → "98%"), matching
the template; IVR is written as a plain 0-100 number.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from src.database import DB_PATH

SEPARATOR_FILL = PatternFill("solid", fgColor="FF002060")
HEADER_FONT = Font(bold=True)
CENTER = Alignment(horizontal="center", vertical="center")

# Thin box around every cell so the grid is readable. The lower half of a merged
# RANK/STOCK/DAYS cell drops its top edge, so the two parameter rows read as one
# cell (this is how the template does it).
_THIN = Side(style="thin")
BORDER_ALL = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
BORDER_MERGED_LOWER = Border(left=_THIN, right=_THIN, bottom=_THIN)

# Red (min) → Yellow (50th pct) → Green (max): identical to the template.
COLOR_SCALE = ColorScaleRule(
    start_type="min", start_color="FFF8696B",
    mid_type="percentile", mid_value=50, mid_color="FFFFEB84",
    end_type="max", end_color="FF63BE7B",
)

FIRST_DATE_COL = 4                       # column D
# DAYS / STOCK / PARA. lead so they are what stays pinned while the dates scroll.
FIXED_WIDTHS = {1: 5.7, 2: 13.3, 3: 6.4}
DATE_COL_WIDTH = 8.1
SEPARATOR_HEIGHT = 7.5                   # half a normal row


def _recent_dates(conn, target_date, n_days=None):
    """
    Dates from daily_metrics up to and including `target_date`, newest first.

    `n_days=None` means every date on record — the full rolling year.
    """
    if n_days is None:
        rows = conn.execute(
            "SELECT DISTINCT date FROM daily_metrics WHERE date <= ? "
            "ORDER BY date DESC",
            (target_date,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT DISTINCT date FROM daily_metrics WHERE date <= ? "
            "ORDER BY date DESC LIMIT ?",
            (target_date, n_days),
        ).fetchall()
    return [r[0] for r in rows]



def _header_label(iso_date):
    """2026-11-06 → 06.11.26 (matches the template)."""
    return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d.%m.%y")


def build_report(path, target_date, n_days=None):
    """
    Write the report to `path`. Returns the number of stocks written (0 if the
    database has nothing for this date).

    `n_days=None` (the default) includes every trading day on record.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        dates = _recent_dates(conn, target_date, n_days)
        if not dates:
            print(f"xlsx: no metrics on or before {target_date}")
            return 0

        marks = ",".join("?" * len(dates))
        rows = conn.execute(
            f"SELECT date, symbol, iv_percentile, iv_rank FROM daily_metrics "
            f"WHERE date IN ({marks})",
            dates,
        ).fetchall()
        hist = dict(conn.execute(
            "SELECT symbol, COUNT(DISTINCT date) FROM daily_iv GROUP BY symbol"
        ).fetchall())
    finally:
        conn.close()

    by_symbol = {}
    for date, symbol, ivp, ivr in rows:
        by_symbol.setdefault(symbol, {})[date] = (ivp, ivr)

    today = dates[0]
    ranked = [
        (sym, per_date)
        for sym, per_date in by_symbol.items()
        if per_date.get(today, (None, None))[0] is not None
    ]
    ranked.sort(key=lambda item: (-item[1][today][0], item[0]))

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"

    n_cols = 3 + len(dates)
    last_col = get_column_letter(n_cols)

    # ── header ──
    headers = ["DAYS", "STOCK", "PARA."] + [_header_label(d) for d in dates]
    for col, text in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=text)
        cell.font = HEADER_FONT
        cell.alignment = CENTER
        cell.border = BORDER_ALL

    for col, width in FIXED_WIDTHS.items():
        ws.column_dimensions[get_column_letter(col)].width = width

    # Pin DAYS, STOCK and PARA. (plus the header row); the dates scroll under
    # them. Excel can only freeze from the left edge, so they lead.
    ws.freeze_panes = "D2"
    for col in range(FIRST_DATE_COL, n_cols + 1):
        ws.column_dimensions[get_column_letter(col)].width = DATE_COL_WIDTH

    # ── one 3-row block per stock ──
    row = 2
    for symbol, per_date in ranked:
        ivp_row, ivr_row, sep_row = row, row + 1, row + 2

        # DAYS and STOCK are merged across the IVP and IVR rows, so each stock
        # reads as one block rather than two. PARA. stays split (IVP/IVR).
        ws.cell(row=ivp_row, column=1, value=hist.get(symbol, 0))
        ws.cell(row=ivp_row, column=2, value=symbol)
        for col in (1, 2):
            ws.merge_cells(start_row=ivp_row, start_column=col,
                           end_row=ivr_row, end_column=col)

        ws.cell(row=ivp_row, column=3, value="IVP")
        ws.cell(row=ivr_row, column=3, value="IVR")

        for i, date in enumerate(dates):
            ivp, ivr = per_date.get(date, (None, None))

            ivp_cell = ws.cell(
                row=ivp_row, column=FIRST_DATE_COL + i,
                value=(round(ivp / 100.0, 4) if ivp is not None else None),
            )
            ivp_cell.number_format = "0%"

            ws.cell(
                row=ivr_row, column=FIRST_DATE_COL + i,
                value=(round(ivr) if ivr is not None else None),
            )

        # colour scale per parameter row, across the date columns
        first_col_letter = get_column_letter(FIRST_DATE_COL)
        ws.conditional_formatting.add(
            f"{first_col_letter}{ivp_row}:{last_col}{ivp_row}", COLOR_SCALE)
        ws.conditional_formatting.add(
            f"{first_col_letter}{ivr_row}:{last_col}{ivr_row}", COLOR_SCALE)

        # centre every cell and box it so the grid is distinct
        for r in (ivp_row, ivr_row):
            for col in range(1, n_cols + 1):
                cell = ws.cell(row=r, column=col)
                cell.alignment = CENTER
                if r == ivr_row and col in (1, 2):
                    cell.border = BORDER_MERGED_LOWER
                else:
                    cell.border = BORDER_ALL

        # dark rule under each stock — half height, so it reads as a line
        ws.row_dimensions[sep_row].height = SEPARATOR_HEIGHT
        for col in range(1, n_cols + 1):
            cell = ws.cell(row=sep_row, column=col)
            cell.fill = SEPARATOR_FILL
            cell.border = BORDER_ALL

        row += 3

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    print(f"xlsx: wrote {len(ranked)} stocks ({len(dates)} dates) to {path}")
    return len(ranked)
