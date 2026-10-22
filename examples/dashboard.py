"""Run the pipeline locally for two platforms and render a performance dashboard.

    python examples/dashboard.py

The SQL below mirrors the dbt models (fct_channel_daily, mart_campaign_performance)
in SQLite syntax, so the whole flow runs without cloud credentials. In a real setup
the same views would come from dbt in BigQuery and feed Looker Studio.
"""

from __future__ import annotations

import sqlite3
import tempfile
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from pipeline.load import SQLiteLoader
from pipeline.run import run
from pipeline.sources.fake import FakeAdsSource

ROOT = Path(__file__).resolve().parents[1]
COLORS = {"meta": "#3B5BDB", "google_ads": "#2F9E44"}

FCT_CHANNEL_DAILY = """
select date, platform,
       sum(spend) as spend, sum(conversions) as conversions, sum(conversion_value) as revenue,
       sum(conversion_value) / nullif(sum(spend), 0) as roas
from ads_daily group by 1, 2 order by 1, 2
"""

CAMPAIGN_PERFORMANCE = """
select platform, campaign_name,
       sum(spend) as spend, sum(conversion_value) as revenue,
       sum(conversion_value) / nullif(sum(spend), 0) as roas,
       sum(spend) / nullif(sum(conversions), 0) as cpa
from ads_daily where date >= :since group by 1, 2 order by roas desc
"""


def kpis(df: pd.DataFrame) -> dict[str, float]:
    s, r, c = df["spend"].sum(), df["revenue"].sum(), df["conversions"].sum()
    return {"Spend": s, "Revenue": r, "ROAS": r / s, "CPA": s / c}


def main(start=date(2026, 1, 1), end=date(2026, 6, 30)):
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "ads.db")
        loader = SQLiteLoader(db)
        for platform in ["meta", "google_ads"]:
            run(FakeAdsSource(platform), loader, start, end)
        conn = sqlite3.connect(db)
        daily = pd.read_sql(FCT_CHANNEL_DAILY, conn, parse_dates=["date"])
        last30_start = (pd.Timestamp(end) - pd.Timedelta(days=29)).date().isoformat()
        campaigns = pd.read_sql(CAMPAIGN_PERFORMANCE, conn, params={"since": last30_start})
        conn.close()

    end_ts = pd.Timestamp(end)
    cur = daily[daily["date"] > end_ts - pd.Timedelta(days=30)]
    prev = daily[(daily["date"] <= end_ts - pd.Timedelta(days=30)) & (daily["date"] > end_ts - pd.Timedelta(days=60))]
    k_cur, k_prev = kpis(cur), kpis(prev)

    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig = plt.figure(figsize=(12, 7.6), dpi=120)
    gs = fig.add_gridspec(3, 4, height_ratios=[0.55, 1.3, 1.3], hspace=0.6, wspace=0.35)
    bottom = gs[2, :].subgridspec(1, 2, wspace=0.75)
    fig.suptitle("Paid media performance · last 30 days", x=0.06, ha="left", fontsize=14, fontweight="bold")

    fmt = {"Spend": "€{:,.0f}", "Revenue": "€{:,.0f}", "ROAS": "{:.2f}", "CPA": "€{:.2f}"}
    lower_is_better = {"CPA"}
    for i, (name, value) in enumerate(k_cur.items()):
        ax = fig.add_subplot(gs[0, i])
        ax.axis("off")
        change = value / k_prev[name] - 1
        good = (change < 0) if name in lower_is_better else (change > 0)
        ax.text(0, 0.85, name, fontsize=10, color="#868E96", transform=ax.transAxes)
        ax.text(0, 0.3, fmt[name].format(value), fontsize=18, fontweight="bold", transform=ax.transAxes)
        ax.text(0, -0.05, f"{change:+.1%} vs prior 30d", fontsize=9, color="#2F9E44" if good else "#E03131", transform=ax.transAxes)

    ax = fig.add_subplot(gs[1, :])
    for platform, g in daily.groupby("platform"):
        g = g.set_index("date")["spend"].rolling(7).mean()
        ax.plot(g.index, g / 1000, color=COLORS[platform], lw=2, label=platform)
    ax.set_title("Daily spend by platform (7-day average, €k)", loc="left")
    ax.legend(frameon=False, fontsize=9)
    ax.grid(alpha=0.25)

    ax = fig.add_subplot(bottom[0, 0])
    roas = daily.copy()
    roas["week"] = roas["date"].dt.to_period("W").dt.start_time
    weekly = roas.groupby(["week", "platform"])[["spend", "revenue"]].sum().reset_index()
    for platform, g in weekly.groupby("platform"):
        ax.plot(g["week"], g["revenue"] / g["spend"], color=COLORS[platform], lw=2, marker="o", ms=3, label=platform)
    ax.set_title("Weekly ROAS", loc="left")
    ax.grid(alpha=0.25)
    ax.tick_params(axis="x", labelrotation=30)

    ax = fig.add_subplot(bottom[0, 1])
    campaigns["label"] = campaigns["campaign_name"].str.split("|").str[0].str.strip() + " · " + campaigns["platform"]
    campaigns = campaigns.sort_values("roas")
    ax.barh(campaigns["label"], campaigns["roas"], color=[COLORS[p] for p in campaigns["platform"]])
    for y, v in enumerate(campaigns["roas"]):
        ax.text(v + 0.02, y, f"{v:.2f}", va="center", fontsize=8)
    ax.axvline(1, color="black", lw=0.8, ls=":")
    ax.set_title("ROAS by campaign (last 30 days)", loc="left")
    ax.grid(alpha=0.25, axis="x")

    out = ROOT / "images" / "dashboard.png"
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out, bbox_inches="tight")
    print(f"wrote {out}")
    print(pd.DataFrame({"last 30d": k_cur, "prior 30d": k_prev}).round(2))


if __name__ == "__main__":
    main()
