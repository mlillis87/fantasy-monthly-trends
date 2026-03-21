import pandas as pd
import streamlit as st
import altair as alt

from src.load_monthly_fg import load_monthly_fg

st.set_page_config(page_title="Fantasy Monthly Trend Lab", layout="wide")

MONTH_NAMES = {4: "Apr", 5: "May", 6: "Jun", 7: "Jul", 8: "Aug", 9: "Sep"}
DEFAULT_MONTHS = [4, 5, 6, 7, 8, 9]

DESIRED_METRICS = [
    "wOBA",
    "HR",
    "OPS",
    "BB%",
    "K%",
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
    return [m for m in DESIRED_METRICS if m in df.columns]


def init_state(metric_options: list[str]) -> None:
    if "selected_pairs" not in st.session_state:
        st.session_state.selected_pairs = []
    if "metric" not in st.session_state:
        st.session_state.metric = metric_options[0] if metric_options else "WOBA"


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
df["K%"] = (df["K"] / df["PA"]).replace([float("inf")], 0).fillna(0)
df["BB%"] = (df["BB"] / df["PA"]).replace([float("inf")], 0).fillna(0)
proj = pd.read_csv("data/2026_depth_charts_projections.csv")
hitters_2026 = proj["Name"].dropna().unique()
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

cand = df[(df["Season"] == pick_season) & (df["Name"].isin(hitters_2026))]
if search:
    cand = cand[cand["Name"].str.contains(search, case=False, na=False)]

names = sorted(cand["Name"].dropna().unique().tolist())
if "player" not in st.session_state:
    st.session_state.player = None

if st.session_state.player not in names:
    st.session_state.player = names[0] if names else None

pick_name = st.sidebar.selectbox(
    "Player",
    names,
    index=names.index(st.session_state.player) if st.session_state.player in names else 0,
    key="player",
)

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
    base = pd.DataFrame({"Month": DEFAULT_MONTHS})

    sub = df[
        (df["Season"] == p["season"])
        & (df["Name"] == p["name"])
        & (df["Month"].isin(DEFAULT_MONTHS))
    ].copy()

    sub = base.merge(sub, on="Month", how="left")

    sub["Season"] = sub["Season"].fillna(p["season"]).astype(int)
    sub["Name"] = sub["Name"].fillna(p["name"])
    sub["PA"] = pd.to_numeric(sub["PA"], errors="coerce").fillna(0).astype(int)

    if "Team" in sub.columns:
        sub["Team"] = sub["Team"].fillna("")

    if "MonthLabel" not in sub.columns:
        sub["MonthLabel"] = sub["Month"].map(MONTH_NAMES)
    else:
        sub["MonthLabel"] = sub["MonthLabel"].fillna(sub["Month"].map(MONTH_NAMES))

    if metric in sub.columns:
        sub[metric] = pd.to_numeric(sub[metric], errors="coerce").fillna(0)
    else:
        sub[metric] = 0

    sub["LineLabel"] = f"{p['season']} {p['name']}"
    plot_frames.append(sub)

plot_df = pd.concat(plot_frames, ignore_index=True) if plot_frames else pd.DataFrame()
month_sort = DEFAULT_MONTHS

# -------------------------
# Charts (shorter heights so both fit)
# -------------------------
metric_chart = (
    alt.Chart(plot_df)
    .mark_line(point=True, interpolate=LINE_INTERPOLATION)
    .encode(
        x=alt.X("Month:O", sort=month_sort, axis=month_axis()),
        y=alt.Y(
            f"{metric}:Q",
            title=metric,
            axis=alt.Axis(format="%" if metric in ["BB%", "K%"] else ".3f"),
        ),
        color=alt.Color(
            "LineLabel:N",
            scale=alt.Scale(range=BASEBALL_PALETTE),
            title="Line",
        ),
        tooltip=[
            alt.Tooltip("LineLabel:N", title="Line"),
            alt.Tooltip("Team:N", title="Team"),
            alt.Tooltip("PA:Q", title="PA"),
            alt.Tooltip("MonthLabel:N", title="Month"),
            alt.Tooltip(
                f"{metric}:Q",
                title=metric,
                format=".1%" if metric in ["BB%", "K%"] else ".3f",
            ),
        ],
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
        tooltip=[
    alt.Tooltip("LineLabel:N", title="Line"),
    alt.Tooltip("Team:N", title="Team"),
    alt.Tooltip("MonthLabel:N", title="Month"),
    alt.Tooltip("PA:Q", title="PA"),
]
    )
    .properties(height=240)
    .interactive()
)


# --- League average (PA-weighted, all players, all seasons) ---

if metric in df.columns and "PA" in df.columns:
    league_avg_metric = (
    df[df["Month"].isin(month_sort)]
    .copy()
)

# rank hitters by PA within each month
league_avg_metric["PA_rank"] = league_avg_metric.groupby("Month")["PA"].rank(
    method="first", ascending=False
)

# keep top 200 hitters per month
league_avg_metric = league_avg_metric[league_avg_metric["PA_rank"] <= 270]

# PA-weighted average metric by month
league_avg_metric = (
    league_avg_metric
    .groupby("Month")
    .agg(
        weighted_metric=(metric, lambda x: (x * league_avg_metric.loc[x.index, "PA"]).sum()),
        total_pa=("PA", "sum"),
    )
    .reset_index()
)

league_avg_metric[metric] = (
    league_avg_metric["weighted_metric"] / league_avg_metric["total_pa"]
)

league_avg_metric = league_avg_metric[["Month", metric]]
league_avg_metric["Label"] = f"Avg {metric} (Top 270 hitters)"

avg_metric_line = (
    alt.Chart(league_avg_metric)
    .mark_line(
        strokeDash=[6, 6],
        color="#9CA3AF",
        strokeWidth=2
    )
    .encode(
        x=alt.X("Month:O", sort=month_sort),
        y=alt.Y(f"{metric}:Q"),
        tooltip=[
            alt.Tooltip("Label:N", title=""),
            alt.Tooltip("Month:O", title="Month"),
            alt.Tooltip(
                f"{metric}:Q",
                title=f"Avg {metric}",
                format=".1%" if metric in ["BB%", "K%"] else ".3f",
            ),
        ]
    )
)

metric_chart = metric_chart + avg_metric_line

# --- League average PA (simple mean) ---

league_avg_pa = (
    df[df["Month"].isin(month_sort)]
    .copy()
)

# rank players by PA within each month
league_avg_pa["PA_rank"] = league_avg_pa.groupby("Month")["PA"].rank(
    method="first", ascending=False
)

# keep top 150 hitters per month
league_avg_pa = league_avg_pa[league_avg_pa["PA_rank"] <= 270]

# compute average PA
league_avg_pa = (
    league_avg_pa
    .groupby("Month", as_index=False)["PA"]
    .mean()
)

league_avg_pa["Label"] = "Avg PA (Top 270 hitters)"

avg_pa_line = (
    alt.Chart(league_avg_pa)
    .mark_line(
        strokeDash=[6, 6],
        color="#9CA3AF",
        strokeWidth=2
    )
    .encode(
        x=alt.X("Month:O", sort=month_sort),
        y=alt.Y("PA:Q"),
        tooltip=[
            alt.Tooltip("Label:N", title=""),
            alt.Tooltip("Month:O", title="Month"),
            alt.Tooltip("PA:Q", title="Avg PA"),
        ]
    )
)

pa_chart = pa_chart + avg_pa_line


st.subheader(f"{metric} by Month")
st.altair_chart(metric_chart, width="stretch")


st.altair_chart(pa_chart, width="stretch")

# Optional: keep table but compact (comment out if you want it even tighter)
with st.expander("Data (filtered)", expanded=False):
    show_cols = ["Season", "MonthLabel", "Name", "Team", "PA", metric]
    show_cols = [c for c in show_cols if c in plot_df.columns]
    sort_cols = [c for c in ["Season", "Name", "Month"] if c in plot_df.columns]

    table_df = plot_df.sort_values(sort_cols) if sort_cols else plot_df

    st.dataframe(
        table_df[show_cols],
        width="stretch",
        hide_index=True,
    )