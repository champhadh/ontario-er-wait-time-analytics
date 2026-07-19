"""Render a static dashboard preview image for the README (Power BI stand-in)."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MART = ROOT / "data" / "processed" / "mart_hospital_month.csv"
OUT = ROOT / "docs" / "dashboard_preview.png"


def main() -> None:
    df = pd.read_csv(MART, parse_dates=["period_date"])
    latest = df["period_date"].max()
    snap = df[df["period_date"] == latest].copy()

    # Volume-weighted provincial wait by month
    df["w"] = df["avg_wait_physician_hrs"] * df["volume_physician_assess"]
    trend = (
        df.groupby("period_date", as_index=False)
        .agg(w=("w", "sum"), v=("volume_physician_assess", "sum"))
    )
    trend["avg_wait"] = trend["w"] / trend["v"]

    by_hosp = (
        snap.dropna(subset=["avg_wait_physician_hrs"])
        .sort_values("avg_wait_physician_hrs", ascending=True)
        .tail(12)
    )

    pct_within = snap["pct_within_target_low"].mean()
    over_target = (snap["avg_los_low_urgency_hrs"] > 4).mean()

    fig = plt.figure(figsize=(12, 7.2), facecolor="#f7f5f2")
    fig.suptitle(
        "Ontario ER Wait-Time Analytics",
        fontsize=16,
        fontweight="bold",
        color="#1a2e35",
        x=0.03,
        ha="left",
        y=0.98,
    )
    fig.text(
        0.03,
        0.935,
        f"Demo dashboard preview · latest period {latest.strftime('%b %Y')} · replace with Power BI export",
        fontsize=9,
        color="#5a6a70",
    )

    # KPI cards
    ax_k1 = fig.add_axes([0.03, 0.78, 0.22, 0.12])
    ax_k2 = fig.add_axes([0.27, 0.78, 0.22, 0.12])
    ax_k3 = fig.add_axes([0.51, 0.78, 0.22, 0.12])
    ax_k4 = fig.add_axes([0.75, 0.78, 0.22, 0.12])

    def kpi(ax, label, value, fmt):
        ax.set_facecolor("#e8eef0")
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.text(0.06, 0.62, label, fontsize=8, color="#5a6a70", transform=ax.transAxes)
        ax.text(0.06, 0.18, fmt.format(value), fontsize=18, fontweight="bold", color="#1a2e35", transform=ax.transAxes)

    kpi(ax_k1, "Avg wait to physician", trend["avg_wait"].iloc[-1], "{:.1f} hrs")
    kpi(ax_k2, "% within target (low urg.)", pct_within / 100, "{:.0%}")
    kpi(ax_k3, "% sites over 4h target", over_target, "{:.0%}")
    kpi(ax_k4, "Hospitals in snapshot", len(snap), "{:.0f}")

    # Trend
    ax1 = fig.add_axes([0.07, 0.42, 0.55, 0.30])
    ax1.plot(trend["period_date"], trend["avg_wait"], color="#0b6e4f", linewidth=2.2)
    ax1.fill_between(trend["period_date"], trend["avg_wait"], alpha=0.12, color="#0b6e4f")
    ax1.axhline(2.0, color="#c45c26", linestyle="--", linewidth=1, label="2h reference")
    ax1.set_title("Provincial avg wait to physician assessment", fontsize=10, loc="left", color="#1a2e35")
    ax1.set_ylabel("Hours")
    ax1.legend(frameon=False, fontsize=8)
    ax1.set_facecolor("#f7f5f2")
    ax1.grid(axis="y", color="#d0d5d8", linewidth=0.6)
    for spine in ("top", "right"):
        ax1.spines[spine].set_visible(False)

    # Hospital bars
    ax2 = fig.add_axes([0.68, 0.12, 0.29, 0.60])
    ax2.barh(by_hosp["hospital_name"], by_hosp["avg_wait_physician_hrs"], color="#1f4e5f")
    ax2.set_title("Wait to physician (latest month)", fontsize=10, loc="left", color="#1a2e35")
    ax2.set_xlabel("Hours")
    ax2.set_facecolor("#f7f5f2")
    ax2.grid(axis="x", color="#d0d5d8", linewidth=0.6)
    for spine in ("top", "right"):
        ax2.spines[spine].set_visible(False)
    ax2.tick_params(axis="y", labelsize=7)

    # Region breakdown
    ax3 = fig.add_axes([0.07, 0.12, 0.55, 0.22])
    region = (
        snap.groupby("oh_region", as_index=False)
        .agg(
            wait=("avg_wait_physician_hrs", "mean"),
            within=("pct_within_target_low", "mean"),
        )
        .sort_values("wait")
    )
    ax3.bar(region["oh_region"], region["within"], color="#3d7c6e")
    ax3.set_ylim(0, 100)
    ax3.yaxis.set_major_formatter(mtick.PercentFormatter())
    # matplotlib PercentFormatter expects 0-1 if xmax=1; our data is 0-100
    ax3.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    ax3.set_title("% patients within low-urgency target by region", fontsize=10, loc="left", color="#1a2e35")
    ax3.set_facecolor("#f7f5f2")
    ax3.grid(axis="y", color="#d0d5d8", linewidth=0.6)
    for spine in ("top", "right"):
        ax3.spines[spine].set_visible(False)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
