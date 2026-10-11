# ChannelLens Campaign Dashboard

A Streamlit dashboard for comparing campaign spend, clicks, conversions, revenue, ROAS, and net ROI.

## Run

```bash
streamlit run app.py --server.port 5000
```

The included synthetic CSV loads by default. Upload another campaign CSV in the sidebar to analyze it. The dashboard requires numeric spend, clicks, conversions, and revenue fields; common header variations are accepted. Date, campaign, platform, goal, and audience fields power filters and breakdowns when provided.

## Metric definitions

- ROAS = revenue ÷ spend
- Net ROI = (revenue − spend) ÷ spend
- Cost per click = spend ÷ clicks
- Cost per conversion = spend ÷ conversions

All ratios are recalculated from the selected rows' totals.
