import pandas as pd
import streamlit as st
import altair as alt
from pathlib import Path

st.set_page_config(page_title="Fantasy Monthly Trend Lab", layout="wide")

MONTH_MAP = {4:"Apr",5:"May",6:"Jun",7:"Jul",8:"Aug",9:"Sep"}
MONTH_ORDER = list(MONTH_MAP.values())
DEFAULT_MONTHS = [4,5,6,7,8,9]

def safe_read_csv(path):
    try:
        return pd.read_csv(path)
    except:
        return pd.read_csv(path, encoding="latin1")

# -------------------------
# VIEW SWITCH (HARD RESET FIX)
# -------------------------
view = st.sidebar.radio("View", ["Batters","Pitchers (SP)"])

if "last_view" not in st.session_state:
    st.session_state.last_view = view

if st.session_state.last_view != view:
    st.session_state.clear()
    st.session_state.last_view = view
    st.rerun()

# -------------------------
# LOADERS
# -------------------------
@st.cache_data
def load_batters():
    dfs = []
    for f in Path("data/monthly/batters").glob("*.csv"):
        df = safe_read_csv(f)
        m,y = f.stem.split("_")
        df["Month"] = int(m)
        df["Season"] = int(y)

        for col in ["PA","AB","H","2B","3B","HR","BB","HBP","SF","SO"]:
            df[col] = pd.to_numeric(df.get(col,0), errors="coerce").fillna(0)

        df["1B"] = df["H"] - df["2B"] - df["3B"] - df["HR"]

        df["OBP"] = (df["H"]+df["BB"]+df["HBP"]) / (df["AB"]+df["BB"]+df["HBP"]+df["SF"])
        df["SLG"] = (df["1B"]+2*df["2B"]+3*df["3B"]+4*df["HR"]) / df["AB"]
        df["OPS"] = df["OBP"] + df["SLG"]

        df["wOBA"] = (
            0.69*df["BB"] + 0.72*df["HBP"] + 0.89*df["1B"] +
            1.27*df["2B"] + 1.62*df["3B"] + 2.10*df["HR"]
        ) / (df["AB"]+df["BB"]+df["HBP"]+df["SF"])

        df["K%"] = df["SO"]/df["PA"]
        df["BB%"] = df["BB"]/df["PA"]

        dfs.append(df)

    return pd.concat(dfs, ignore_index=True)

@st.cache_data
def load_pitchers():
    base = Path("data/monthly/sp")
    dfs = []

    for f in (base/"standard").glob("*.csv"):
        adv = base/"advanced"/f.name
        if not adv.exists(): continue

        df = pd.merge(
            safe_read_csv(f),
            safe_read_csv(adv),
            on=["Season","Month","Name"]
        )

        m,y = f.stem.split("_")
        df["Month"] = int(m)
        df["Season"] = int(y)
        df["IP"] = pd.to_numeric(df.get("IP",0), errors="coerce").fillna(0)

        dfs.append(df)

    return pd.concat(dfs, ignore_index=True)

@st.cache_data
def load_names(path):
    return sorted(safe_read_csv(path)["Name"].dropna().unique())

# -------------------------
# CONFIG
# -------------------------
if view == "Batters":
    df = load_batters()
    METRICS = ["wOBA","OPS","HR","BB%","K%"]
    VOL = "PA"
    VOL_LABEL = "Plate Appearances"
    eligible = load_names("data/2026_depth_charts_batters.csv")
else:
    df = load_pitchers()
    METRICS = ["ERA","WHIP","K%","BB%","xFIP"]
    VOL = "IP"
    VOL_LABEL = "Innings Pitched"
    eligible = load_names("data/2026_depth_charts_sp.csv")

df["MonthLabel"] = df["Month"].map(MONTH_MAP)

st.title("Fantasy Monthly Trend Lab")

# -------------------------
# SIDEBAR
# -------------------------
metric = st.sidebar.selectbox("Metric", METRICS)
season = st.sidebar.selectbox("Season", sorted(df["Season"].unique()))

eligible = [n for n in eligible if n in df["Name"].unique()]
names = sorted(df[(df["Season"]==season)&(df["Name"].isin(eligible))]["Name"].unique())
player = st.sidebar.selectbox("Player", names)

if "pairs" not in st.session_state:
    st.session_state.pairs = []

if st.sidebar.button("Add line"):
    st.session_state.pairs.append({"season":season,"name":player})

if st.sidebar.button("Clear"):
    st.session_state.pairs = []

# -------------------------
# BUILD DF (CRITICAL FIX)
# -------------------------
frames = []

for p in st.session_state.pairs:
    base = pd.DataFrame({"Month":DEFAULT_MONTHS})
    sub = df[(df["Season"]==p["season"])&(df["Name"]==p["name"])]
    sub = base.merge(sub, on="Month", how="left")

    sub["MonthLabel"] = sub["Month"].map(MONTH_MAP)

    # 🔥 FORCE METRIC EXIST + NUMERIC
    sub[metric] = pd.to_numeric(sub.get(metric,0), errors="coerce").fillna(0)
    sub[VOL] = pd.to_numeric(sub.get(VOL,0), errors="coerce").fillna(0)

    sub["LineLabel"] = f"{p['season']} {p['name']}"

    frames.append(sub)

plot_df = pd.concat(frames) if frames else pd.DataFrame()

# -------------------------
# BASELINE
# -------------------------
b = df.copy()
b["rank"] = b.groupby("Month")[VOL].rank(ascending=False)
b = b[b["rank"]<=250]

metric_base = b.groupby("Month")[metric].mean().reset_index()
metric_base["MonthLabel"] = metric_base["Month"].map(MONTH_MAP)

vol_base = b.groupby("Month")[VOL].mean().reset_index()
vol_base["MonthLabel"] = vol_base["Month"].map(MONTH_MAP)

# -------------------------
# CHARTS (FINAL FIX)
# -------------------------
if not plot_df.empty:

    color_enc = alt.Color("LineLabel:N", legend=alt.Legend(title=None))

    metric_chart = alt.Chart(plot_df).mark_line(
        point=True, interpolate="monotone"
    ).encode(
        x=alt.X("MonthLabel:N", sort=MONTH_ORDER, axis=alt.Axis(title=None)),
        y=alt.Y(f"{metric}:Q"),
        color=color_enc
    )

    metric_base_chart = alt.Chart(metric_base).mark_line(
        strokeDash=[5,5], color="gray"
    ).encode(
        x="MonthLabel:N",
        y=alt.Y(f"{metric}:Q")
    )

    volume_chart = alt.Chart(plot_df).mark_line(
        point=True, interpolate="monotone"
    ).encode(
        x=alt.X("MonthLabel:N", sort=MONTH_ORDER, axis=alt.Axis(title=None)),
        y=alt.Y(f"{VOL}:Q", axis=alt.Axis(title=VOL_LABEL)),
        color=color_enc
    )

    volume_base_chart = alt.Chart(vol_base).mark_line(
        strokeDash=[5,5], color="gray"
    ).encode(
        x="MonthLabel:N",
        y=alt.Y(f"{VOL}:Q")
    )

    st.subheader(metric)
    st.altair_chart(metric_chart + metric_base_chart, use_container_width=True)
    st.altair_chart(volume_chart + volume_base_chart, use_container_width=True)