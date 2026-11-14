"""Build the Telegram message and the price-versus-positioning chart."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import analysis
import store

CHART = Path(__file__).resolve().parent / "chart.png"


def _fmt(n, sign=True):
    if n is None:
        return "-"
    if sign:
        return f"{n:+,}" if n else "0"
    return f"{n:,}"


def _pct(share):
    return "-" if share is None else f"{share * 100:.0f}%"


def build_text(history, target, closes):
    today, delta, prev_day = analysis.day_actions(history, target)
    day_rows = history[target]
    totals = analysis.market_totals(day_rows)

    stamp = datetime.strptime(target, "%Y-%m-%d")
    lines = [f"<b>Participant OI — {stamp.strftime('%d %b %Y')}</b>"]

    close = closes.get(target)
    prev_close = None
    if close is not None:
        earlier = [d for d in sorted(closes) if d < target]
        if earlier:
            prev_close = closes[earlier[-1]]
    if close is not None:
        if prev_close:
            chg = close - prev_close
            lines.append(f"Nifty {close:,.2f} ({chg:+,.2f}, {chg / prev_close * 100:+.2f}%)")
        else:
            lines.append(f"Nifty {close:,.2f}")
    lines.append(f"<i>vs {prev_day or 'no earlier session'}</i>")
    lines.append("")

    lines.append("<b>Index futures</b> — net contracts, long share")
    for client in ("FII", "Client", "Pro", "DII"):
        m = today.get(client)
        if not m:
            continue
        d = delta.get(client, {}).get("idx_fut_net")
        lines.append(f"  {client:<7}{_fmt(m['idx_fut_net']):>12}  "
                     f"({_fmt(d)})  long {_pct(m['idx_fut_long_share'])}")
    lines.append("")

    lines.append("<b>Index options</b> — net contracts (calls / puts)")
    for client in ("FII", "Client", "Pro", "DII"):
        m = today.get(client)
        if not m:
            continue
        dc = delta.get(client, {}).get("idx_call_net")
        dp = delta.get(client, {}).get("idx_put_net")
        lines.append(f"  {client:<7}calls {_fmt(m['idx_call_net']):>11} ({_fmt(dc)})"
                     f"   puts {_fmt(m['idx_put_net']):>11} ({_fmt(dp)})")
    lines.append("")

    lines.append("<b>Stock futures</b> — net contracts")
    for client in ("FII", "Client", "Pro", "DII"):
        m = today.get(client)
        if not m:
            continue
        d = delta.get(client, {}).get("stk_fut_net")
        lines.append(f"  {client:<7}{_fmt(m['stk_fut_net']):>12}  ({_fmt(d)})")
    lines.append("")

    # Where FII index futures sit in the recent window - the workbook's
    # "Price v/s Index Futures" idea, in one line.
    ex = analysis.extremes(history, target, "FII", "idx_fut_net")
    if ex:
        lines.append(f"<b>FII index futures</b> at the {ex['pctile']}th percentile "
                     f"of the last {ex['sessions']} sessions "
                     f"(min {_fmt(ex['min'])}, max {_fmt(ex['max'])})")
    # Long and short always balance across clients, so the useful figure is the
    # change in total index-futures OI: buildup or unwinding.
    prev_rows = history.get(prev_day) if prev_day else None
    if prev_rows:
        prev_total = analysis.market_totals(prev_rows)["Future Index Long"]
        change = totals["Future Index Long"] - prev_total
        lines.append(f"<i>Index futures OI {totals['Future Index Long']:,} "
                     f"({change:+,}) — {'buildup' if change > 0 else 'unwinding'}</i>")
    else:
        lines.append(f"<i>Index futures OI {totals['Future Index Long']:,}</i>")
    return "\n".join(lines)


def build_chart(history, closes, sessions=90):
    """Nifty close against FII and Client net index futures."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    dates = sorted(history)[-sessions:]
    if len(dates) < 5:
        return None

    # Price may lag the OI series (or be missing entirely); plot the gaps.
    price = [closes.get(d) for d in dates]

    def break_gaps(values, max_days=5):
        """Insert None where consecutive sessions are more than `max_days` apart,
        so a backfill gap does not draw a straight line across the hole."""
        out = []
        for i, d in enumerate(dates):
            if i:
                prev = datetime.strptime(dates[i - 1], "%Y-%m-%d")
                cur = datetime.strptime(d, "%Y-%m-%d")
                if (cur - prev).days > max_days:
                    out.append(None)
            out.append(values[i])
        return out
    fii, client = [], []
    for d in dates:
        m = analysis.metrics_for(history[d])
        fii.append(m.get("FII", {}).get("idx_fut_net"))
        client.append(m.get("Client", {}).get("idx_fut_net"))
    price = break_gaps(price)
    fii = break_gaps(fii)
    client = break_gaps(client)

    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=130)
    ax.plot(dates, price, color="#1f77b4", linewidth=1.8, label="Nifty close")
    ax.set_ylabel("Nifty", color="#1f77b4")
    ax.tick_params(axis="y", labelcolor="#1f77b4")
    ax.grid(alpha=0.25)

    ax2 = ax.twinx()
    ax2.plot(dates, fii, color="#d62728", linewidth=1.3, label="FII net index fut")
    ax2.plot(dates, client, color="#2ca02c", linewidth=1.3, label="Client net index fut")
    ax2.axhline(0, color="grey", linewidth=0.8, linestyle=":")
    ax2.set_ylabel("Net contracts", color="#444")
    ax2.tick_params(axis="y", labelcolor="#444")

    step = max(1, len(dates) // 10)
    ax.set_xticks(dates[::step])
    ax.set_xticklabels([datetime.strptime(d, "%Y-%m-%d").strftime("%d %b")
                        for d in dates[::step]], rotation=0, fontsize=8)
    ax.set_title(f"Price v/s Index Futures — last {len(dates)} sessions", fontsize=11)

    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(CHART)
    plt.close(fig)
    return CHART
