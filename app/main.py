"""
NZ Electricity Network Reliability Intelligence
Main Streamlit App — Entry Point

Reads gold layer data from ADLS and displays
industry-wide reliability overview.
"""

import os
import streamlit as st
import pandas as pd
import plotly.express as px
from io import BytesIO
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="NZ Grid Reliability Intelligence",
    page_icon="⚡",
    layout="wide",
)

# ── Custom CSS — Terminal/Cyberpunk Theme ──────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'JetBrains Mono', monospace;
    }

    .stApp {
        background-color: #0A0E1A;
        background-image:
            linear-gradient(rgba(0, 217, 255, 0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0, 217, 255, 0.03) 1px, transparent 1px);
        background-size: 40px 40px;
    }

    h1 {
        font-weight: 800 !important;
        text-transform: uppercase;
        letter-spacing: 2px;
        color: #00D9FF !important;
    }

    h2, h3 {
        font-family: 'JetBrains Mono', monospace !important;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #00D9FF !important;
    }

    [data-testid="stMetric"] {
        background-color: #111827;
        border: 1px solid #00D9FF44;
        border-radius: 8px;
        padding: 12px;
    }

    [data-testid="stMetricLabel"] {
        text-transform: uppercase;
        font-size: 11px !important;
        letter-spacing: 1px;
        color: #6B7A99 !important;
    }

    [data-testid="stMetricValue"] {
        font-family: 'JetBrains Mono', monospace !important;
        font-weight: 800 !important;
        color: #00D9FF !important;
    }

    .stCaption {
        font-family: 'JetBrains Mono', monospace !important;
        color: #6B7A99 !important;
    }
</style>
""", unsafe_allow_html=True)


# ── Data loading ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_gold_table(blob_path: str) -> pd.DataFrame:
    """Load a parquet table from ADLS gold container."""
    client = BlobServiceClient(
        account_url=f"https://{os.getenv('AZURE_STORAGE_ACCOUNT_NAME')}.blob.core.windows.net",
        credential=os.getenv("AZURE_STORAGE_ACCOUNT_KEY"),
    )
    blob = client.get_blob_client(container="gold", blob=blob_path)
    data = blob.download_blob().readall()
    return pd.read_parquet(BytesIO(data))


company_perf = load_gold_table("comcom/company_performance.parquet")
cause_breakdown = load_gold_table("comcom/cause_breakdown.parquet")
monthly_trend = load_gold_table("comcom/monthly_trend.parquet")


# ── Header ─────────────────────────────────────────────────────────────────────
st.title("⚡ NZ Electricity Network Reliability Intelligence")
st.caption("Data source: Commerce Commission EDB Information Disclosure 2025")

# ── KPI row ────────────────────────────────────────────────────────────────────
industry_avg = company_perf["industry_avg_saidi"].iloc[0]
best = company_perf.iloc[-1]
worst = company_perf.iloc[0]

col1, col2, col3, col4 = st.columns(4)
col1.metric("Companies Analysed", len(company_perf))
col2.metric("Industry Avg SAIDI", f"{industry_avg:.1f} min")

with col3:
    st.markdown(f"""
    <div style="background-color:#111827; border:1px solid #2A2F3E; border-radius:8px;
                padding:12px; border-top:4px solid #2ECC71;">
        <div style="color:#6B7A99; font-size:11px; letter-spacing:1px; text-transform:uppercase;">✅ Best Performer</div>
        <div style="color:#FAFAFA; font-size:22px; font-weight:800; margin:4px 0;">{best['edb']}</div>
        <div style="color:#2ECC71; font-size:20px; font-weight:800;">↓ {abs(best['saidi_vs_avg']):.0f} min <span style="color:#6B7A99; font-size:12px; font-weight:400;">better than average</span></div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown(f"""
    <div style="background-color:#111827; border:1px solid #2A2F3E; border-radius:8px;
                padding:12px; border-top:4px solid #E74C3C;">
        <div style="color:#6B7A99; font-size:11px; letter-spacing:1px; text-transform:uppercase;">⚠️ Worst Performer</div>
        <div style="color:#FAFAFA; font-size:22px; font-weight:800; margin:4px 0;">{worst['edb']}</div>
        <div style="color:#E74C3C; font-size:20px; font-weight:800;">↑ {worst['saidi_vs_avg']:.0f} min <span style="color:#6B7A99; font-size:12px; font-weight:400;">worse than average</span></div>
    </div>
    """, unsafe_allow_html=True)

st.divider()

# ── SAIDI ranking chart ───────────────────────────────────────────────────────
st.subheader("SAIDI Ranking — All Companies")
st.caption("Total minutes of unplanned + planned outage per customer in 2025")

# Binary color: above average = red, below average = green
company_perf["performance"] = company_perf["saidi_vs_avg"].apply(
    lambda x: "Worse than average" if x > 0 else "Better than average"
)

fig = px.bar(
    company_perf.sort_values("total_saidi", ascending=True),
    x="total_saidi",
    y="edb",
    orientation="h",
    color="performance",
    color_discrete_map={
        "Better than average": "#2ECC71",
        "Worse than average": "#E74C3C",
    },
    labels={"total_saidi": "SAIDI (minutes)", "edb": "Company", "performance": ""},
    height=800,
)
fig.add_vline(x=industry_avg, line_dash="dash", line_color="#888888",
               annotation_text=f"Industry Avg: {industry_avg:.1f}",
               annotation_font_color="#FAFAFA")
fig.update_traces(
    hovertemplate="<b>%{y}</b><br>SAIDI: %{x:.1f} min<extra></extra>"
)
fig.update_layout(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font_color="#FAFAFA",
    font_family="JetBrains Mono",
    xaxis=dict(gridcolor="#1E2538"),
    yaxis=dict(gridcolor="#1E2538", categoryorder="total descending"),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, title=None),
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Cause breakdown — worst performer drill-down ──────────────────────────────
st.subheader(f"Why is {worst['edb']} underperforming?")
st.caption("Breakdown of unplanned outage causes — share of total unplanned events")

worst_causes = cause_breakdown[cause_breakdown["edb"] == worst["edb"]].sort_values("cause_share", ascending=False)

fig2 = px.bar(
    worst_causes,
    x="cause_share",
    y="cause_normalised",
    orientation="h",
    text=worst_causes["cause_share"].apply(lambda x: f"{x:.0%}"),
    labels={"cause_share": "Share of Unplanned Events", "cause_normalised": "Cause"},
    color_discrete_sequence=["#00D9FF"],
)
fig2.update_traces(
    textposition="outside",
    hovertemplate="<b>%{y}</b><br>%{x:.0%} of unplanned events<extra></extra>"
)
fig2.update_layout(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font_color="#FAFAFA",
    font_family="JetBrains Mono",
    xaxis=dict(gridcolor="#1E2538", tickformat=".0%"),
    yaxis=dict(gridcolor="#1E2538", categoryorder="total ascending"),
    showlegend=False,
)
st.plotly_chart(fig2, use_container_width=True)

insight_cause = worst_causes.iloc[0]
st.info(
    f"**{insight_cause['cause_normalised']}** accounts for "
    f"**{insight_cause['cause_share']:.0%}** of unplanned outages at {worst['edb']}, "
    f"contributing **{insight_cause['total_saidi']:.1f} minutes** of SAIDI."
)
unknown_row = worst_causes[worst_causes["cause_normalised"] == "Unknown"]
if not unknown_row.empty and unknown_row.iloc[0]["cause_share"] > 0.10:
    st.warning(
        f"⚠️ **{unknown_row.iloc[0]['cause_share']:.0%}** of outages have an **unknown cause** — "
        f"this may indicate a data quality gap in fault reporting."
    )