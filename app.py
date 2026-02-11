import pandas as pd
import streamlit as st
import altair as alt

from src.load_monthly_fg import load_monthly_fg


st.set_page_config(page_title="Fantasy Monthly Trend Lab", layout="wide")


MONTH_NAMES = {
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
}


@st.cache_data
def get_data() -> pd.DataFrame:
    df = load_monthly_fg()

    # Ensure types
    df["Season"] = df["Season"].astype(int)
    df["Month"] = df["Month"].astype(int)
    df["PA"] = pd.to_numeric(df["PA"], errors="coerce").fillna(0).astype(int)

    # Human month label + ordering
    df["MonthLabel"] = df["Month"].map(MONTH_NAMES)
    return df


st.title("Fantasy Monthly Trend Lab")
df = get_data()

# -------------------------
# Sidebar controls
# -------------------------
st.sidebar.header("Filters")

seasons = sorted(df["Season"].unique())
season = st.sidebar.selectbox("Season", seasons, index=len(seasons) - 1)

months_avail = sorted(df.loc[df["Season"] == season, "Month"].unique())
months_default = [m for m in [4, 5, 6, 7, 8, 9] if m in months_avail]

months = st.sidebar.multiselect(
    "Months",
    options=months_avail,
    default=months_default,
    format_func=lambda m: MONTH_NAMES.get(m, str(m)),
)

min_pa = st.sidebar.slider("Min PA (per month)", 0, 200, 0, step=10)

metric = st.sidebar.selectbox(
    "Metric",
    ["FWOBA", "R", "H", "2B", "HR", "RBI", "SB", "BB", "K", "AVG"],
)

max_lines = st.sidebar.slider("Max players (lines)", 1, 15, 8)

search = st.sidebar.text_input("Player search (contains)", value="")

# Filter base set
base = df[
    (df["Season"] == season)
    & (df["Month"].isin(months))
    & (df["PA"] >= min_pa)
].copy()

if search.strip():
    base = base[base["Name"].str.contains(search.strip(), case=False, na=False)]

# Candidate list for selection (unique names)
choices = sorted(base["Name"].dropna().unique().tolist())

selected = st.sidebar.multiselect(
    "Select players to plot",
    options=choices,
    default=choices[: min(max_lines, len(choices))],
)

selected = selected[:max_lines]

plot_df = base[base["Name"].isin(selected)].copy()

# Order months
plot_df["MonthOrder"] = plot_df["Month"]
plot_df = plot_df.sort_values(["Name", "MonthOrder"])

# -------------------------
# Chart
# -------------------------
st.subheader(f"{metric} by Month — {season}")

if plot_df.empty or not selected:
    st.info("No data for current filters.")
else:
    chart = (
        alt.Chart(plot_df)
        .mark_line(point=True)
        .encode(
            x=alt.X(
                "MonthOrder:O",
                sort=months_default,
                axis=alt.Axis(
                    title="Month",
                    labelExpr="datum.value == 4 ? 'Apr' : "
                              "datum.value == 5 ? 'May' : "
                              "datum.value == 6 ? 'Jun' : "
                              "datum.value == 7 ? 'Jul' : "
                              "datum.value == 8 ? 'Aug' : 'Sep'"
                ),
            ),
            y=alt.Y(f"{metric}:Q", title=metric),
            color=alt.Color("Name:N", title="Player"),
            tooltip=["Name", "Team", "PA", "MonthLabel", metric],
        )
        .properties(height=480)
        .interactive()
    )

    st.altair_chart(chart, use_container_width=True)

# -------------------------
# Table below
# -------------------------
st.subheader("Data (filtered)")
show_cols = ["Season", "MonthLabel", "Name", "Team", "PA", metric]

# Make sure selected metric exists
show_cols = [c for c in show_cols if c in plot_df.columns]

st.dataframe(
    plot_df[show_cols].sort_values(["Name", "Season", "MonthLabel"]),
    use_container_width=True,
    hide_index=True,
)
