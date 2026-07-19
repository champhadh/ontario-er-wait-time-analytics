"""
Ontario ER Wait-Time Analytics — local GUI

Run:
    streamlit run app.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
MART_CSV = ROOT / "data" / "processed" / "mart_hospital_month.csv"
DQ_REPORT = ROOT / "reports" / "data_quality_report.txt"
PIPELINE = ROOT / "etl" / "run_pipeline.py"

INK = "#111827"
MUTED = "#374151"
LINE = "#111827"
BAR = "#1f4e5f"

st.set_page_config(
    page_title="Ontario ER Wait Times",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      .stApp { background: #ffffff; color: #111827; }
      .block-container { padding-top: 1.75rem; padding-bottom: 2rem; max-width: 1100px; }
      h1 {
        font-size: 1.85rem !important;
        font-weight: 700 !important;
        color: #111827 !important;
        margin-bottom: 0.2rem !important;
      }
      .subtitle { color: #374151; font-size: 1rem; margin-bottom: 1.4rem; }
      label, .stSelectbox label { color: #111827 !important; font-weight: 600 !important; }
      [data-testid="stMetric"] {
        background: #f3f4f6;
        border: 1px solid #d1d5db;
        padding: 1rem 1.1rem;
        border-radius: 8px;
      }
      [data-testid="stMetricLabel"] p {
        color: #111827 !important;
        font-size: 0.95rem !important;
        font-weight: 600 !important;
      }
      [data-testid="stMetricValue"] {
        color: #111827 !important;
        font-size: 1.75rem !important;
        font-weight: 700 !important;
      }
      div[data-testid="stHorizontalBlock"] { gap: 0.75rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def load_mart(mtime: float) -> pd.DataFrame:
    df = pd.read_csv(MART_CSV, parse_dates=["period_date"])
    return df.sort_values(["period_date", "hospital_name"])


def weighted_avg(df: pd.DataFrame, value_col: str, weight_col: str) -> float | None:
    sub = df.dropna(subset=[value_col, weight_col])
    if sub.empty or sub[weight_col].sum() == 0:
        return None
    return float((sub[value_col] * sub[weight_col]).sum() / sub[weight_col].sum())


def run_pipeline(source: str) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(PIPELINE), "--source", source],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def clean_chart(fig: go.Figure, height: int = 380, left_margin: int = 16) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(color=INK, size=14),
        title=dict(font=dict(size=17, color=INK, family="Arial"), x=0, xanchor="left"),
        margin=dict(l=left_margin, r=40, t=48, b=40),
        height=height,
        showlegend=False,
    )
    fig.update_xaxes(
        showgrid=False,
        title_font=dict(size=13, color=INK),
        tickfont=dict(size=13, color=INK),
        linecolor="#9ca3af",
        ticks="outside",
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor="#e5e7eb",
        title_font=dict(size=13, color=INK),
        tickfont=dict(size=13, color=INK),
        linecolor="#9ca3af",
    )
    return fig


def main() -> None:
    st.title("Ontario ER Wait Times")
    st.markdown(
        '<p class="subtitle">Average wait to see a physician · Jul 2024 to Jul 2026</p>',
        unsafe_allow_html=True,
    )

    if not MART_CSV.exists():
        st.warning("No data yet. Expand **Data refresh** below and run the pipeline.")
    else:
        df_all = load_mart(MART_CSV.stat().st_mtime)

        regions = ["All regions"] + sorted(df_all["oh_region"].dropna().unique().tolist())
        months = sorted(df_all["period_date"].dropna().unique())

        f1, f2 = st.columns(2)
        with f1:
            region = st.selectbox("Region", regions, index=0)
        with f2:
            month_labels = [pd.Timestamp(m).strftime("%b %Y") for m in months]
            month_idx = len(months) - 1
            selected_label = st.selectbox("Month", month_labels, index=month_idx)
            selected_month = months[month_labels.index(selected_label)]

        df = df_all.copy()
        if region != "All regions":
            df = df[df["oh_region"] == region]
        snap = df[df["period_date"] == selected_month]

        if snap.empty:
            st.info("No hospitals for this filter.")
            return

        avg_wait = weighted_avg(snap, "avg_wait_physician_hrs", "volume_physician_assess")
        pct_within = snap["pct_within_target_low"].mean()
        over_target = (snap["avg_los_low_urgency_hrs"] > 4).mean()

        k1, k2, k3 = st.columns(3)
        k1.metric("Avg wait to physician", f"{avg_wait:.1f} hrs" if avg_wait is not None else "—")
        k2.metric("Seen within target", f"{pct_within:.0f}%" if pd.notna(pct_within) else "—")
        k3.metric("Hospitals over 4h target", f"{over_target:.0%}" if pd.notna(over_target) else "—")

        st.write("")

        trend_base = df_all if region == "All regions" else df_all[df_all["oh_region"] == region]
        trend = (
            trend_base.assign(w=trend_base["avg_wait_physician_hrs"] * trend_base["volume_physician_assess"])
            .groupby("period_date", as_index=False)
            .agg(w=("w", "sum"), v=("volume_physician_assess", "sum"))
        )
        trend["avg_wait"] = trend["w"] / trend["v"]

        fig_trend = px.line(
            trend,
            x="period_date",
            y="avg_wait",
            markers=True,
            labels={"period_date": "", "avg_wait": "Hours"},
            title="Wait to physician over time",
        )
        fig_trend.update_traces(line_color=LINE, line_width=3, marker=dict(size=8, color=LINE))
        fig_trend.add_hline(
            y=2.0,
            line_dash="dot",
            line_color="#4b5563",
            annotation_text="2 hr reference",
            annotation_font=dict(size=12, color=INK),
        )
        fig_trend.update_xaxes(dtick="M3", tickformat="%b %Y")
        st.plotly_chart(
            clean_chart(fig_trend, 360),
            use_container_width=True,
            config={"displayModeBar": False},
        )

        by_hosp = (
            snap.dropna(subset=["avg_wait_physician_hrs"])
            .sort_values("avg_wait_physician_hrs", ascending=True)
        )
        fig_hosp = px.bar(
            by_hosp,
            x="avg_wait_physician_hrs",
            y="hospital_name",
            orientation="h",
            labels={"avg_wait_physician_hrs": "Hours", "hospital_name": ""},
            title=f"Wait to physician by hospital — {selected_label}",
            text="avg_wait_physician_hrs",
        )
        fig_hosp.update_traces(
            marker_color=BAR,
            texttemplate="%{text:.1f}",
            textposition="outside",
            textfont=dict(size=13, color=INK),
            cliponaxis=False,
        )
        fig_hosp.update_yaxes(tickfont=dict(size=14, color=INK))
        height = max(420, 32 * len(by_hosp) + 90)
        st.plotly_chart(
            clean_chart(fig_hosp, height, left_margin=8),
            use_container_width=True,
            config={"displayModeBar": False},
        )

        with st.expander("View data table"):
            table = snap[
                [
                    "hospital_name",
                    "oh_region",
                    "avg_wait_physician_hrs",
                    "avg_los_low_urgency_hrs",
                    "pct_within_target_low",
                    "volume_physician_assess",
                ]
            ].rename(
                columns={
                    "hospital_name": "Hospital",
                    "oh_region": "Region",
                    "avg_wait_physician_hrs": "Wait (hrs)",
                    "avg_los_low_urgency_hrs": "Low-urgency LOS (hrs)",
                    "pct_within_target_low": "% within target",
                    "volume_physician_assess": "Volume",
                }
            ).sort_values("Wait (hrs)", ascending=False)
            st.dataframe(table, use_container_width=True, hide_index=True)

        with st.expander("Data quality report"):
            if DQ_REPORT.exists():
                st.code(DQ_REPORT.read_text(encoding="utf-8"), language="text")
            else:
                st.write("No report yet.")

    with st.expander("Data refresh"):
        source = st.radio(
            "Source",
            options=["csv", "fixed-width"],
            format_func=lambda x: "CSV" if x == "csv" else "Fixed-width",
            horizontal=True,
        )
        if st.button("Run pipeline"):
            with st.spinner("Refreshing…"):
                code, output = run_pipeline(source)
            load_mart.clear()
            if code == 0:
                st.success("Refresh complete")
                st.rerun()
            else:
                st.error("Refresh failed")
                st.code(output)


if __name__ == "__main__":
    main()
