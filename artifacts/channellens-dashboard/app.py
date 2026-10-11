from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


APP_DIR = Path(__file__).resolve().parent
SAMPLE_CSV = APP_DIR / "campaign_data.csv"

st.set_page_config(
    page_title="ChannelLens | Campaign performance",
    layout="wide",
)


ALIASES = {
    "date": ("date", "day", "report_date"),
    "campaign_name": ("campaign_name", "campaign", "campaign_title", "name"),
    "platform": ("platform", "channel", "publisher", "network"),
    "campaign_goal": ("campaign_goal", "goal", "objective"),
    "audience": ("audience", "audience_segment", "segment"),
    "spend": ("spend_usd", "spend", "cost", "amount_spent", "media_spend"),
    "clicks": ("clicks", "link_clicks", "outbound_clicks"),
    "conversions": ("conversions", "purchases", "orders", "results"),
    "revenue": ("revenue_usd", "revenue", "sales", "conversion_value"),
}

METRIC_LABELS = {
    "Spend": "spend",
    "Clicks": "clicks",
    "Conversions": "conversions",
    "Revenue": "revenue",
    "ROAS": "roas",
    "Net ROI": "roi",
    "Cost per click": "cpc",
    "Cost per conversion": "cpa",
}


def normalize_columns(data: pd.DataFrame) -> pd.DataFrame:
    """Map common campaign CSV headers to the app's standard field names."""
    data = data.copy()
    data.columns = [str(column).strip().lower().replace(" ", "_") for column in data.columns]
    rename: dict[str, str] = {}
    for canonical, choices in ALIASES.items():
        match = next((choice for choice in choices if choice in data.columns), None)
        if match:
            rename[match] = canonical
    data = data.rename(columns=rename)

    required = ["spend", "clicks", "conversions", "revenue"]
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(
            "This CSV is missing required fields: "
            + ", ".join(missing)
            + ". Include spend, clicks, conversions, and revenue so ROI can be calculated."
        )

    if "campaign_name" not in data.columns:
        data["campaign_name"] = "All campaigns"
    if "platform" not in data.columns:
        data["platform"] = "Unspecified"
    for optional in ("campaign_goal", "audience"):
        if optional not in data.columns:
            data[optional] = "Unspecified"

    for column in ("spend", "clicks", "conversions", "revenue"):
        data[column] = pd.to_numeric(data[column], errors="coerce")

    all_metrics_missing = data[
        ["spend", "clicks", "conversions", "revenue"]
    ].isna().all(axis=1)
    data = data.loc[~all_metrics_missing].copy()
    if data.empty:
        raise ValueError("No rows contain any valid spend, clicks, conversions, or revenue values.")

    for column in ("campaign_name", "platform", "campaign_goal", "audience"):
        data[column] = data[column].fillna("Unspecified").astype(str).str.strip()
        data.loc[data[column].eq(""), column] = "Unspecified"

    if "date" in data.columns:
        data["date"] = pd.to_datetime(data["date"], errors="coerce")
        data = data.loc[data["date"].notna()].copy()
        if data.empty:
            raise ValueError("The date column was found, but it contains no valid dates.")

    data["roas"] = data["revenue"].div(data["spend"].where(data["spend"].ne(0)))
    data["roi"] = (data["revenue"] - data["spend"]).div(data["spend"].where(data["spend"].ne(0)))
    data["cpc"] = data["spend"].div(data["clicks"].where(data["clicks"].ne(0)))
    data["cpa"] = data["spend"].div(data["conversions"].where(data["conversions"].ne(0)))
    return data


def metric_value(data: pd.DataFrame, metric: str) -> float:
    spend = data["spend"].sum()
    clicks = data["clicks"].sum()
    conversions = data["conversions"].sum()
    revenue = data["revenue"].sum()
    totals = {
        "spend": spend,
        "clicks": clicks,
        "conversions": conversions,
        "revenue": revenue,
        "roas": revenue / spend if spend else float("nan"),
        "roi": (revenue - spend) / spend if spend else float("nan"),
        "cpc": spend / clicks if clicks else float("nan"),
        "cpa": spend / conversions if conversions else float("nan"),
    }
    return totals[metric]


def format_metric(value: float, metric: str) -> str:
    if pd.isna(value):
        return "—"
    if metric in ("spend", "revenue", "cpc", "cpa"):
        return f"${value:,.2f}" if metric in ("cpc", "cpa") else f"${value:,.0f}"
    if metric == "roas":
        return f"{value:.2f}x"
    if metric == "roi":
        return f"{value:.1%}"
    return f"{value:,.0f}"


def comparison_table(data: pd.DataFrame, group_by: str) -> pd.DataFrame:
    grouped = (
        data.groupby(group_by, dropna=False)
        .agg(
            Spend=("spend", "sum"),
            Clicks=("clicks", "sum"),
            Conversions=("conversions", "sum"),
            Revenue=("revenue", "sum"),
        )
        .reset_index()
    )
    grouped["ROAS"] = grouped["Revenue"].div(grouped["Spend"].where(grouped["Spend"].ne(0)))
    grouped["Net ROI"] = (
        (grouped["Revenue"] - grouped["Spend"])
        .div(grouped["Spend"].where(grouped["Spend"].ne(0)))
        .mul(100)
    )
    grouped["Cost per click"] = grouped["Spend"].div(grouped["Clicks"].where(grouped["Clicks"].ne(0)))
    grouped["Cost per conversion"] = grouped["Spend"].div(
        grouped["Conversions"].where(grouped["Conversions"].ne(0))
    )
    return grouped


st.title("ChannelLens")
st.caption("A clear view of campaign investment, response, and return.")

with st.sidebar:
    st.header("Data & filters")
    uploaded = st.file_uploader("Upload a campaign CSV", type=["csv"])

    if uploaded is None:
        source = pd.read_csv(SAMPLE_CSV)
        st.caption("Showing the included synthetic campaign sample.")
    else:
        try:
            source = pd.read_csv(uploaded)
        except Exception as exc:
            st.error(f"Could not read this CSV: {exc}")
            st.stop()

    try:
        data = normalize_columns(source)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    full_sample_start = data["date"].min().date() if "date" in data.columns else None
    full_sample_end = data["date"].max().date() if "date" in data.columns else None

    st.divider()
    if "date" in data.columns:
        min_date = data["date"].min().date()
        max_date = data["date"].max().date()
        chosen_dates = st.date_input(
            "Date range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )
        if isinstance(chosen_dates, tuple) and len(chosen_dates) == 2:
            start_date, end_date = chosen_dates
            data = data.loc[
                data["date"].dt.date.between(start_date, end_date)
            ].copy()
    else:
        st.caption("No date field detected; date filtering and trend charts are unavailable.")

    for field, label in (
        ("platform", "Platform"),
        ("campaign_goal", "Campaign goal"),
        ("audience", "Audience"),
    ):
        options = sorted(data[field].dropna().unique().tolist())
        selected = st.multiselect(label, options, default=options)
        if selected:
            data = data.loc[data[field].isin(selected)].copy()
        else:
            data = data.iloc[0:0].copy()

    campaigns = sorted(data["campaign_name"].dropna().unique().tolist())
    selected_campaigns = st.multiselect("Campaign", campaigns, default=campaigns)
    if selected_campaigns:
        data = data.loc[data["campaign_name"].isin(selected_campaigns)].copy()
    else:
        data = data.iloc[0:0].copy()

    st.divider()
    st.caption("ROI uses (revenue − spend) ÷ spend. ROAS uses revenue ÷ spend.")

if data.empty:
    st.info("No campaign rows match these filters. Adjust the date range or selections.")
    st.stop()

if "date" in data.columns:
    period_start = data["date"].min().strftime("%b %d, %Y")
    period_end = data["date"].max().strftime("%b %d, %Y")
    st.caption(
        f"Filtered period: {period_start} – {period_end} · "
        f"{len(data):,} daily campaign rows · "
        f"{data['campaign_name'].nunique():,} campaigns"
    )

total_spend = data["spend"].sum()
total_revenue = data["revenue"].sum()
total_clicks = data["clicks"].sum()
total_conversions = data["conversions"].sum()
net_roi = (total_revenue - total_spend) / total_spend if total_spend else float("nan")
roas = total_revenue / total_spend if total_spend else float("nan")

if uploaded is None and full_sample_start is not None and full_sample_end is not None:
    st.info(
        f"Data note: the included sample spans {full_sample_start:%B %-d, %Y}–"
        f"{full_sample_end:%B %-d, %Y}. That differs from the Fall Bathroom Refresh "
        "dates in the PRD, so this view reflects the CSV rather than the PRD flight."
    )

st.subheader("Performance at a glance")
missing_revenue = int(data["revenue"].isna().sum())
if missing_revenue:
    st.warning(
        f"{missing_revenue:,} selected rows have no revenue value. Totals use reported "
        "revenue only while retaining available spend, clicks, and conversions. ROAS "
        "and net ROI may therefore understate actual return."
    )

missing_spend = int(data["spend"].isna().sum())
if missing_spend:
    st.warning(
        f"{missing_spend:,} selected rows have no spend value; spend totals and "
        "spend-based ratios use reported spend only."
    )

cards = st.columns(5)
cards[0].metric("Spend", f"${total_spend:,.0f}", help="Sum of spend across the filtered campaign rows.")
cards[1].metric("Clicks", f"{total_clicks:,.0f}", help="Sum of clicks across the filtered campaign rows.")
cards[2].metric(
    "Conversions",
    f"{total_conversions:,.0f}",
    help="Sum of the conversions column; view-through conversions are not added separately.",
)
cards[3].metric("ROAS", f"{roas:.2f}x" if pd.notna(roas) else "—", help="Total revenue ÷ total spend.")
cards[4].metric(
    "Net ROI",
    f"{net_roi:.1%}" if pd.notna(net_roi) else "—",
    help="(Total revenue − total spend) ÷ total spend.",
)

st.divider()
left, right = st.columns([1.15, 1])

with left:
    st.subheader("Compare platforms")
    platform_data = comparison_table(data, "platform")
    platform_data = platform_data.sort_values("Spend", ascending=False)
    chart_metric_label = st.selectbox(
        "Compare platforms by",
        list(METRIC_LABELS.keys()),
        index=5,
        key="platform_metric",
    )
    chart_metric = METRIC_LABELS[chart_metric_label]
    chart_columns = {
        "spend": "Spend",
        "clicks": "Clicks",
        "conversions": "Conversions",
        "revenue": "Revenue",
        "roas": "ROAS",
        "roi": "Net ROI",
        "cpc": "Cost per click",
        "cpa": "Cost per conversion",
    }
    chart_column = chart_columns[chart_metric]
    bar_data = platform_data[["platform", chart_column]].replace(
        [float("inf"), -float("inf")], pd.NA
    )
    bar_data = bar_data.dropna(subset=[chart_column])
    if not bar_data.empty:
        fig = px.bar(
            bar_data.sort_values(chart_column, ascending=True),
            x=chart_column,
            y="platform",
            orientation="h",
            labels={"platform": "Platform", chart_column: chart_metric_label},
            color_discrete_sequence=["#0f766e"],
        )
        fig.update_layout(
            height=max(300, 54 * len(bar_data)),
            margin=dict(l=4, r=8, t=12, b=4),
            coloraxis_showscale=False,
        )
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("There are no non-zero values for this metric in the current selection.")

with right:
    st.subheader("Spend & revenue over time")
    if "date" in data.columns:
        cadence = st.radio("Time grouping", ["Week", "Month"], horizontal=True)
        period = "W-MON" if cadence == "Week" else "MS"
        trend = data.set_index("date").resample(period)[["spend", "revenue"]].sum().reset_index()
        trend = trend.melt(
            id_vars="date",
            value_vars=["spend", "revenue"],
            var_name="Measure",
            value_name="Amount ($)",
        )
        trend["Measure"] = trend["Measure"].map({"spend": "Spend", "revenue": "Revenue"})
        fig = px.line(
            trend,
            x="date",
            y="Amount ($)",
            color="Measure",
            markers=True,
            labels={"date": "Date"},
            color_discrete_map={"Spend": "#2563eb", "Revenue": "#0f766e"},
        )
        fig.update_layout(height=360, margin=dict(l=4, r=8, t=12, b=4), legend_title_text="")
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("Add a date column to view performance trends.")

st.divider()
st.subheader("Campaign comparison")
st.caption("Totals are summed; ROAS, net ROI, and unit costs are recalculated from those totals.")

campaigns_table = comparison_table(data, "campaign_name").rename(columns={"campaign_name": "Campaign"})
platform_by_campaign = (
    data.groupby("campaign_name")["platform"]
    .agg(lambda values: ", ".join(sorted(values.unique())))
    .rename("Platform")
)
goal_by_campaign = (
    data.groupby("campaign_name")["campaign_goal"]
    .agg(lambda values: ", ".join(sorted(values.unique())))
    .rename("Goal")
)
campaigns_table = (
    campaigns_table.set_index("Campaign")
    .join(platform_by_campaign)
    .join(goal_by_campaign)
    .reset_index()
)
campaigns_table = campaigns_table[
    [
        "Campaign",
        "Platform",
        "Goal",
        "Spend",
        "Clicks",
        "Conversions",
        "Revenue",
        "ROAS",
        "Net ROI",
        "Cost per click",
        "Cost per conversion",
    ]
]

worst_roas = campaigns_table["ROAS"].min()
if pd.notna(worst_roas) and len(campaigns_table) > 1:
    st.caption(f"Lowest ROAS in this selection: {campaigns_table.loc[campaigns_table['ROAS'].idxmin(), 'Campaign']}")

display_table = campaigns_table.copy()
for column in ("Spend", "Revenue", "Cost per click", "Cost per conversion"):
    display_table[column] = display_table[column].map(lambda value: f"${value:,.2f}" if pd.notna(value) else "—")
display_table["ROAS"] = display_table["ROAS"].map(lambda value: f"{value:.2f}x" if pd.notna(value) else "—")
display_table["Net ROI"] = display_table["Net ROI"].map(lambda value: f"{value:.1f}%" if pd.notna(value) else "—")
for column in ("Clicks", "Conversions"):
    display_table[column] = display_table[column].map(lambda value: f"{value:,.0f}")

st.dataframe(display_table, width="stretch", hide_index=True)
csv_bytes = campaigns_table.to_csv(index=False).encode("utf-8")
st.download_button(
    "Download filtered campaign comparison",
    data=csv_bytes,
    file_name="channellens_campaign_comparison.csv",
    mime="text/csv",
)

with st.expander("Metric definitions"):
    st.markdown(
        """
        - **Spend:** sum of campaign spend.
        - **Clicks:** sum of clicks.
        - **Conversions:** sum of the CSV's `conversions` field.
        - **Revenue:** sum of attributed revenue.
        - **ROAS:** revenue ÷ spend.
        - **Net ROI:** (revenue − spend) ÷ spend.
        - **Cost per click:** spend ÷ clicks.
        - **Cost per conversion:** spend ÷ conversions.

        These are aggregate ratios calculated from filtered totals, not averages of daily or campaign-level ratios.
        """
    )
