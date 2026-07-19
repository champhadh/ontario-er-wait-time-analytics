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
import streamlit as st

ROOT = Path(__file__).resolve().parent
MART_CSV = ROOT / "data" / "processed" / "mart_hospital_month.csv"
DQ_REPORT = ROOT / "reports" / "data_quality_report.txt"
PIPELINE = ROOT / "etl" / "run_pipeline.py"

# Visual direction: clinical slate / forest (not purple/cream defaults)
COLORS = {
    "bg": "#f4f7f6",
    "ink": "#14242b",
    "muted": "#5a6f76",
    "accent": "#0b6e4f",
    "accent2": "#1f4e5f",
    "warn": "#c45c26",
    "card": "#e8eef0",
}

st.set_page_config(
    page_title="Ontario ER Wait-Time Analytics",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    f"""
    <style>
      .stApp {{ background: linear-gradient(165deg, #f4f7f6 0%, #e3ece8 45%, #d7e4e8 100%); }}
      h1, h2, h3 {{ color: {COLORS["ink"]} !important; letter-spacing: -0.02em; }}
      [data-testid="stMetric"] {{
        background: {COLORS["card"]};
        padding: 1rem 1.1rem;
        border-radius: 4px;
        border-left: 3px solid {COLORS["accent"]};
      }}
      [data-testid="stMetric"] label {{ color: {COLORS["muted"]} !important; }}
      .block-container {{ padding-top: 1.4rem; }}
      section[data-testid="stSidebar"] {{ background: #edf3f1; }}
      .footnote {{ color: {COLORS["muted"]}; font-size: 0.85rem; }}
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
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output


def main() -> None:
    st.title("Ontario ER Wait-Time Analytics")
    st.caption(
        "Hospital ED wait times · Python/SQL pipeline · data quality checks · Power BI–ready export"
    )

    with st.sidebar:
        st.header("Controls")
        source = st.radio(
            "Refresh source",
            options=["csv", "fixed-width"],
            format_func=lambda x: "CSV export" if x == "csv" else "Fixed-width (SAS path)",
            index=0,
        )
        if st.button("Refresh pipeline", type="primary", use_container_width=True):
            with st.spinner("Running ETL + quality checks…"):
                code, output = run_pipeline(source)
            load_mart.clear()
            st.code(output, language="text")
            if code == 0:
                st.success("Pipeline finished — DQ PASS")
            else:
                st.error("Pipeline finished with errors / DQ FAIL")

        if not MART_CSV.exists():
            st.warning("No processed data yet. Click Refresh pipeline.")
            return

        df_all = load_mart(MART_CSV.stat().st_mtime)
        regions = sorted(df_all["oh_region"].dropna().unique())
        peers = sorted(df_all["peer_group"].dropna().unique())
        hospitals = sorted(df_all["hospital_name"].dropna().unique())

        selected_regions = st.multiselect("OH region", regions, default=regions)
        selected_peers = st.multiselect("Peer group", peers, default=peers)
        selected_hospitals = st.multiselect(
            "Hospitals",
            hospitals,
            default=hospitals,
        )
        min_d, max_d = df_all["period_date"].min().date(), df_all["period_date"].max().date()
        date_range = st.date_input(
            "Period range",
            value=(min_d, max_d),
            min_value=min_d,
            max_value=max_d,
        )

    df_all = load_mart(MART_CSV.stat().st_mtime)
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
    else:
        start, end = min_d, max_d

    df = df_all[
        df_all["oh_region"].isin(selected_regions)
        & df_all["peer_group"].isin(selected_peers)
        & df_all["hospital_name"].isin(selected_hospitals)
        & (df_all["period_date"].dt.date >= start)
        & (df_all["period_date"].dt.date <= end)
    ].copy()

    if df.empty:
        st.warning("No rows match the current filters.")
        return

    latest = df["period_date"].max()
    snap = df[df["period_date"] == latest]

    avg_wait = weighted_avg(df, "avg_wait_physician_hrs", "volume_physician_assess")
    pct_within = snap["pct_within_target_low"].mean()
    over_target = (snap["avg_los_low_urgency_hrs"] > 4).mean()
    admitted_vs = (snap["avg_los_admitted_hrs"] - 8).mean()

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Avg wait to physician", f"{avg_wait:.1f} hrs" if avg_wait is not None else "—")
    k2.metric("% within target (low urg.)", f"{pct_within:.0f}%" if pd.notna(pct_within) else "—")
    k3.metric("% sites over 4h target", f"{over_target:.0%}" if pd.notna(over_target) else "—")
    k4.metric("Admitted LOS vs 8h", f"{admitted_vs:+.1f} hrs" if pd.notna(admitted_vs) else "—")

    st.markdown(
        f'<p class="footnote">KPIs mirror the DAX measures in <code>powerbi/measures.dax</code> · '
        f"latest filtered month: <b>{latest.strftime('%b %Y')}</b></p>",
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns((1.15, 1))

    with c1:
        trend = (
            df.assign(w=df["avg_wait_physician_hrs"] * df["volume_physician_assess"])
            .groupby("period_date", as_index=False)
            .agg(w=("w", "sum"), v=("volume_physician_assess", "sum"))
        )
        trend["avg_wait"] = trend["w"] / trend["v"]
        fig_trend = px.line(
            trend,
            x="period_date",
            y="avg_wait",
            markers=True,
            labels={"period_date": "Month", "avg_wait": "Hours"},
            title="Provincial / filtered avg wait to physician",
        )
        fig_trend.add_hline(y=2.0, line_dash="dash", line_color=COLORS["warn"], annotation_text="2h ref")
        fig_trend.update_traces(line_color=COLORS["accent"], line_width=2.5)
        fig_trend.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(244,247,246,0.6)",
            font_color=COLORS["ink"],
            margin=dict(l=10, r=10, t=48, b=10),
            height=360,
        )
        st.plotly_chart(fig_trend, use_container_width=True)

    with c2:
        by_region = (
            snap.groupby("oh_region", as_index=False)
            .agg(pct_within=("pct_within_target_low", "mean"))
            .sort_values("pct_within")
        )
        fig_region = px.bar(
            by_region,
            x="oh_region",
            y="pct_within",
            labels={"oh_region": "Region", "pct_within": "% within target"},
            title="% within low-urgency target by region (latest)",
        )
        fig_region.update_traces(marker_color=COLORS["accent2"])
        fig_region.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(244,247,246,0.6)",
            font_color=COLORS["ink"],
            margin=dict(l=10, r=10, t=48, b=10),
            height=360,
            yaxis_range=[0, 100],
        )
        st.plotly_chart(fig_region, use_container_width=True)

    by_hosp = (
        snap.dropna(subset=["avg_wait_physician_hrs"])
        .sort_values("avg_wait_physician_hrs", ascending=True)
        .tail(15)
    )
    fig_hosp = px.bar(
        by_hosp,
        x="avg_wait_physician_hrs",
        y="hospital_name",
        orientation="h",
        color="oh_region",
        labels={
            "avg_wait_physician_hrs": "Hours",
            "hospital_name": "Hospital",
            "oh_region": "Region",
        },
        title="Wait to physician by hospital (latest month)",
        color_discrete_sequence=[COLORS["accent"], COLORS["accent2"], COLORS["warn"], "#3d7c6e", "#6b8f71"],
    )
    fig_hosp.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(244,247,246,0.6)",
        font_color=COLORS["ink"],
        margin=dict(l=10, r=10, t=48, b=10),
        height=480,
        legend_title_text="Region",
    )
    st.plotly_chart(fig_hosp, use_container_width=True)

    tab_data, tab_dq = st.tabs(["Filtered data", "Data quality report"])
    with tab_data:
        show_cols = [
            "period_date",
            "hospital_name",
            "oh_region",
            "peer_group",
            "avg_wait_physician_hrs",
            "avg_los_low_urgency_hrs",
            "avg_los_high_urgency_hrs",
            "avg_los_admitted_hrs",
            "pct_within_target_low",
            "volume_physician_assess",
        ]
        st.dataframe(
            df[show_cols].sort_values(["period_date", "hospital_name"], ascending=[False, True]),
            use_container_width=True,
            hide_index=True,
        )
    with tab_dq:
        if DQ_REPORT.exists():
            st.code(DQ_REPORT.read_text(encoding="utf-8"), language="text")
        else:
            st.info("No DQ report yet — run the pipeline.")

    st.markdown(
        '<p class="footnote">Demo data calibrated to Ontario Health / CIHI-style ED reporting. '
        "Not for clinical use. Power BI build guide: <code>powerbi/DASHBOARD_BUILD.md</code></p>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
