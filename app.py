import pandas as pd
import streamlit as st
import altair as alt

from src.load_monthly_fg import load_monthly_fg

st.set_page_config(page_title="Fantasy Monthly Trend Lab", layout="wide")

MONTH_NAMES = {4: "Apr", 5: "May", 6: "Jun", 7: "Jul", 8: "Aug", 9: "Sep"}
DEFAULT_MONTHS = [4, 5, 6, 7, 8, 9]

DESIRED_METRICS = [
    "FWOBA",
    "wOBA",
    "xwOBA",
    "wOBAcon",
    "xwOBAcon",
    "OPS",
    "fWAR",
]

LINE_INTERPOLATION = "monotone"

# Night-game modern palette for lines
BASEBALL_PALETTE = [
    "#E10600",  # MLB red
    "#3B82F6",  # electric blue
    "#10B981",  # subtle green
    "#F59E0B",  # amber stadium light
    "#8B5CF6",  # cool purple
    "#F97316",  # burnt orange
    "#22C55E",  # extra green
    "#60A5FA",  # soft blue
    "#FCA5A5",  # soft red tint
    "#A3A3A3",  # neutral gray
]


@st.cache_data
def get_data() -> pd.DataFrame:
    df = load_monthly_fg()
    df["Season"] = df["Season"].astype(int)
    df["Month"] = df["Month"].astype(int)
    df["PA"] = pd.to_numeric(df.get("PA", 0), errors="coerce").fillna(0).astype(int)

    if "MonthLabel" not in df.columns:
        df["MonthLabel"] = df["Month"].map(MONTH_NAMES)

    if "Team" not in df.columns and "Tm" in df.columns:
        df = df.rename(columns={"Tm": "Team"})

    return df


def get_metric_options(df: pd.DataFrame) -> list[str]:
    opts = [m for m in DESIRED_METRICS if m in df.columns]
    if "FWOBA" in df.columns and "FWOBA" not in opts:
        opts = ["FWOBA"] + opts
    return opts


def init_state(metric_options: list[str]) -> None:
    if "selected_pairs" not in st.session_state:
        st.session_state.selected_pairs = []
    if "metric" not in st.session_state:
        st.session_state.metric = metric_options[0] if metric_options else "FWOBA"


def add_pair(season: int, name: str, max_lines: int = 8) -> None:
    pair = {"season": int(season), "name": name}
    if pair not in st.session_state.selected_pairs:
        st.session_state.selected_pairs.append(pair)

    if len(st.session_state.selected_pairs) > max_lines:
        st.session_state.selected_pairs = st.session_state.selected_pairs[-max_lines:]


def remove_pair(idx: int) -> None:
    st.session_state.selected_pairs.pop(idx)


def month_axis() -> alt.Axis:
    return alt.Axis(
        title="",
        labelExpr=(
            "datum.value == 4 ? 'Apr' : "
            "datum.value == 5 ? 'May' : "
            "datum.value == 6 ? 'Jun' : "
            "datum.value == 7 ? 'Jul' : "
            "datum.value == 8 ? 'Aug' : 'Sep'"
        ),
    )


# -------------------------
# Compact layout tweaks (main pane + sidebar)
# -------------------------
st.markdown(
    """
<style>
/* tighten the main container padding */
.block-container {
  padding-top: 1.1rem;
  padding-bottom: 0.6rem;
  padding-left: 1.0rem;
  padding-right: 1.0rem;
  max-width: 1400px;
}

/* tighten header spacing */
h1, h2, h3 {
  margin-top: 0.3rem !important;
  margin-bottom: 0.4rem !important;
}

/* reduce vertical gaps between elements */
div[data-testid="stVerticalBlock"] > div {
  gap: 0.6rem;
}

/* slightly tighter sidebar padding */
section[data-testid="stSidebar"] .block-container {
  padding-top: 0.8rem;
}


h1 {
    font-size: 28px !important;
}

</style>
""",
    unsafe_allow_html=True,
)

# -------------------------
# App
# -------------------------
df = get_data()
metric_options = get_metric_options(df)
init_state(metric_options)

st.title("Fantasy Monthly Trend Lab")

st.sidebar.header("Controls")

# Only keep the metric dropdown
if metric_options:
    default_idx = (
        metric_options.index(st.session_state.metric)
        if st.session_state.metric in metric_options
        else 0
    )
    st.session_state.metric = st.sidebar.selectbox(
        "Metric",
        metric_options,
        index=default_idx,
    )
else:
    st.sidebar.error("No metrics available. Check your data + loader.")
    st.stop()

# Add lines (Season + Player)
st.sidebar.subheader("Add a line")

seasons = sorted(df["Season"].dropna().unique())
pick_season = st.sidebar.selectbox(
    "Season",
    seasons,
    index=len(seasons) - 1 if seasons else 0,
)

search = st.sidebar.text_input("Player search", value="").strip()

cand = df[df["Season"] == pick_season]
if search:
    cand = cand[cand["Name"].str.contains(search, case=False, na=False)]

names = sorted(cand["Name"].dropna().unique().tolist())
pick_name = st.sidebar.selectbox("Player", names) if names else None

if st.sidebar.button("Add line", disabled=pick_name is None):
    add_pair(pick_season, pick_name, max_lines=8)

if st.sidebar.button("Clear lines"):
    st.session_state.selected_pairs = []

st.sidebar.subheader("Selected")
if not st.session_state.selected_pairs:
    st.sidebar.caption("Add one or more player-season lines.")
else:
    for i, p in enumerate(st.session_state.selected_pairs):
        cols = st.sidebar.columns([5, 1])
        cols[0].write(f"{p['season']} — {p['name']}")
        if cols[1].button("✖", key=f"rm_{i}"):
            remove_pair(i)
            st.rerun()

# -------------------------
# Build plot dataframe (months fixed to Apr-Sep, no month filter UI)
# -------------------------
metric = st.session_state.metric
months = DEFAULT_MONTHS
min_pa = 0  # fixed (no slider)

plot_frames = []
for p in st.session_state.selected_pairs:
    sub = df[
        (df["Season"] == p["season"])
        & (df["Name"] == p["name"])
        & (df["Month"].isin(months))
        & (df["PA"] >= min_pa)
    ].copy()

    if sub.empty:
        continue

    sub["LineLabel"] = f"{p['season']} {p['name']}"
    plot_frames.append(sub)

plot_df = pd.concat(plot_frames, ignore_index=True) if plot_frames else pd.DataFrame()

if plot_df.empty:
    st.info("Add a player-season line from the sidebar to see charts.")
    st.stop()

month_sort = [m for m in months if m in plot_df["Month"].unique()]

# -------------------------
# Charts (shorter heights so both fit)
# -------------------------
metric_chart = (
    alt.Chart(plot_df)
    .mark_line(point=True, interpolate=LINE_INTERPOLATION)
    .encode(
        x=alt.X("Month:O", sort=month_sort, axis=month_axis()),
        y=alt.Y(f"{metric}:Q", title=metric),
        color=alt.Color(
            "LineLabel:N",
            scale=alt.Scale(range=BASEBALL_PALETTE),
            title="Line",
        ),
        tooltip=["LineLabel", "Team", "PA", "MonthLabel", metric],
    )
    .properties(height=360)
    .interactive()
)

pa_chart = (
    alt.Chart(plot_df)
    .mark_line(point=True, interpolate=LINE_INTERPOLATION)
    .encode(
        x=alt.X("Month:O", sort=month_sort, axis=month_axis()),
        y=alt.Y("PA:Q", title="Plate Appearances"),
        color=alt.Color(
            "LineLabel:N",
            scale=alt.Scale(range=BASEBALL_PALETTE),
            title="Line",
        ),
        tooltip=["LineLabel", "Team", "MonthLabel", "PA"],
    )
    .properties(height=240)
    .interactive()
)


# --- League average (PA-weighted, all players, all seasons) ---

if metric in df.columns and "PA" in df.columns:
    league_avg_metric = (
    df[df["PA"] > 0]
    .groupby("Month")
    .agg(
        weighted_metric=(metric, lambda x: (x * df.loc[x.index, "PA"]).sum()),
        total_pa=("PA", "sum")
    )
    .reset_index()
    )

    league_avg_metric[metric] = (
    league_avg_metric["weighted_metric"] /
    league_avg_metric["total_pa"]
    )
    league_avg_metric = league_avg_metric[["Month", metric]]

    avg_metric_line = (
        alt.Chart(league_avg_metric)
        .mark_line(
            strokeDash=[6, 6],
            color="#9CA3AF",
            strokeWidth=2
        )
        .encode(
            x=alt.X("Month:O", sort=month_sort),
            y=alt.Y(f"{metric}:Q")
        )
    )

    metric_chart = metric_chart + avg_metric_line

# --- League average PA (simple mean) ---

league_avg_pa = (
    df
    .groupby("Month", as_index=False)["PA"]
    .mean()
)

full_time_line = alt.Chart(
    pd.DataFrame({"Month": month_sort, "PA": [90]*len(month_sort)})
).mark_line(
    strokeDash=[6,6],
    color="#9CA3AF",
    strokeWidth=2
).encode(
    x="Month:O",
    y="PA:Q"
)

pa_chart = pa_chart + full_time_line


st.subheader(f"{metric} by Month")
st.altair_chart(metric_chart, width="stretch")


st.altair_chart(pa_chart, width="stretch")

# Optional: keep table but compact (comment out if you want it even tighter)
with st.expander("Data (filtered)", expanded=False):
    show_cols = ["Season", "MonthLabel", "Name", "Team", "PA", metric]
    show_cols = [c for c in show_cols if c in plot_df.columns]
    st.dataframe(
        plot_df[show_cols].sort_values(["Season", "Name", "MonthLabel"]),
        width="stretch",
        hide_index=True,
    )