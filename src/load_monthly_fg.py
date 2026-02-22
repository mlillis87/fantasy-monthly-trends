from __future__ import annotations

from pathlib import Path
import re

import numpy as np
import pandas as pd

DATA_DIR = Path("data/monthly")

# Filenames are MM_YYYY.csv (e.g., 04_2021.csv)
FILENAME_RE = re.compile(r"(?P<month>\d{2})_(?P<year>\d{4})\.csv")


def _to_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


def load_monthly_fg(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """
    Load FanGraphs monthly split CSVs from data_dir and return one master DataFrame.

    Expected filename pattern: MM_YYYY.csv (e.g., 04_2021.csv)

    Adds:
      - Season (int)
      - Month (int)
      - MonthLabel (str, Apr-Sep)

    Normalizes:
      - Tm -> Team
      - SO -> K

    Computes:
      - OPS (from OBP+SLG if not present)
      - wOBA (approx, using fixed weights; season-specific weights require more inputs)
      - FWOBA (your fantasy-cat wOBA-style rate), rescaled ~0.200-0.400
      - fWAR only if WAR exists (renamed)
      - xwOBA / wOBAcon / xwOBAcon only if columns exist in your data
    """
    files = sorted(data_dir.glob("*.csv"))
    if not files:
        raise RuntimeError(f"No CSV files found in {data_dir.resolve()}")

    dfs: list[pd.DataFrame] = []

    for path in files:
        m = FILENAME_RE.fullmatch(path.name)
        if not m:
            print(f"Skipping unrecognized filename: {path.name}")
            continue

        month = int(m.group("month"))
        year = int(m.group("year"))

        df = pd.read_csv(path)

        # Overwrite/define from filename (more reliable than inside-file columns)
        df["Season"] = year
        df["Month"] = month
        dfs.append(df)

    if not dfs:
        raise RuntimeError(
            "No usable CSVs found. Check filenames match MM_YYYY.csv "
            f"and that {data_dir.resolve()} contains the monthly files."
        )

    all_df = pd.concat(dfs, ignore_index=True)

    # ---------------------------
    # Standardize column names
    # ---------------------------
    all_df = all_df.rename(columns={"Tm": "Team", "SO": "K"})

    # ---------------------------
    # Coerce numeric columns (keep Name/Team as strings)
    # ---------------------------
    for col in all_df.columns:
        if col in {"Name", "Team"}:
            continue
        all_df[col] = pd.to_numeric(all_df[col], errors="coerce").fillna(0)

    # Keep seasons 2021+
    all_df["Season"] = pd.to_numeric(all_df["Season"], errors="coerce").astype("Int64")
    all_df["Month"] = pd.to_numeric(all_df["Month"], errors="coerce").astype("Int64")
    all_df = all_df[all_df["Season"] >= 2021].copy()

    # Month label (Apr-Sep)
    month_names = {4: "Apr", 5: "May", 6: "Jun", 7: "Jul", 8: "Aug", 9: "Sep"}
    all_df["MonthLabel"] = all_df["Month"].map(month_names)

    # ---------------------------
    # Ensure common batting columns exist (as numeric, default 0)
    # ---------------------------
    needed = [
        "PA", "AB", "H", "1B", "2B", "3B", "HR",
        "BB", "IBB", "HBP", "SF",
        "R", "RBI", "SB", "K",
    ]
    for c in needed:
        if c not in all_df.columns:
            all_df[c] = 0

    for c in needed:
        all_df[c] = _to_num(all_df[c])

    # ---------------------------
    # OPS (compute if not present)
    # ---------------------------
    if "OPS" not in all_df.columns:
        # TB from hit types
        tb = all_df["1B"] + 2 * all_df["2B"] + 3 * all_df["3B"] + 4 * all_df["HR"]
        slg = np.where(all_df["AB"] > 0, tb / all_df["AB"], np.nan)

        obp_denom = all_df["AB"] + all_df["BB"] + all_df["HBP"] + all_df["SF"]
        obp = np.where(
            obp_denom > 0,
            (all_df["H"] + all_df["BB"] + all_df["HBP"]) / obp_denom,
            np.nan,
        )

        all_df["OPS"] = obp + slg

    # ---------------------------
    # wOBA (approx)
    #   Using stable weights (not season-specific).
    #   Exact season weights + scale require league constants by year.
    # ---------------------------
    if "wOBA" not in all_df.columns:
        # Common modern-ish weights (approx)
        w = {
            "BB": 0.69,   # unintentional BB
            "HBP": 0.72,
            "1B": 0.88,
            "2B": 1.25,
            "3B": 1.58,
            "HR": 2.01,
        }

        ubb = (all_df["BB"] - all_df["IBB"]).clip(lower=0)
        denom = all_df["AB"] + ubb + all_df["SF"] + all_df["HBP"]
        num = (
            w["BB"] * ubb
            + w["HBP"] * all_df["HBP"]
            + w["1B"] * all_df["1B"]
            + w["2B"] * all_df["2B"]
            + w["3B"] * all_df["3B"]
            + w["HR"] * all_df["HR"]
        )
        all_df["wOBA"] = np.where(denom > 0, num / denom, np.nan)

    # ---------------------------
    # fWAR (only if present)
    # ---------------------------
    if "WAR" in all_df.columns and "fWAR" not in all_df.columns:
        all_df["fWAR"] = pd.to_numeric(all_df["WAR"], errors="coerce")

    # ---------------------------
    # FWOBA (your fantasy categories) -> rescaled to ~0.200-0.400
    #
    # Cats: H, R, 2B, HR, SB, BB, RBI, K (K counts against)
    # We compute a raw rate per PA, then rescale via percentiles
    # so it "looks like" wOBA for easier intuition.
    # ---------------------------
    fw_weights = {
        "H": 0.55,
        "R": 0.55,
        "2B": 0.25,
        "HR": 1.10,
        "SB": 0.35,
        "BB": 0.45,
        "RBI": 0.55,
        "K": -0.35,
    }

    pa = all_df["PA"].where(all_df["PA"] > 0, np.nan)
    fw_raw = 0.0
    for stat, wt in fw_weights.items():
        fw_raw = fw_raw + wt * all_df[stat]

    all_df["FWOBA_raw"] = np.where(pa.notna(), fw_raw / pa, np.nan)

    # ---------------------------
    # FWOBA — match real MLB wOBA distribution
    # ---------------------------

    dist_mask = (all_df["PA"] >= 20) & all_df["FWOBA_raw"].notna()

    raw_mean = all_df.loc[dist_mask, "FWOBA_raw"].mean()
    raw_std = all_df.loc[dist_mask, "FWOBA_raw"].std()

    if raw_std and raw_std > 0:
        z = (all_df["FWOBA_raw"] - raw_mean) / raw_std
        all_df["FWOBA"] = 0.320 + (z * 0.045)
    else:
        all_df["FWOBA"] = 0.320

    # ---------------------------
    # Sorting
    # ---------------------------
    sort_cols = [c for c in ["Season", "Month", "Name"] if c in all_df.columns]
    all_df = all_df.sort_values(sort_cols).reset_index(drop=True)

    return all_df


if __name__ == "__main__":
    df = load_monthly_fg()
    print(df.head())
    print("\nRows:", len(df))
    print("\nSeasons:", sorted(df["Season"].dropna().unique().tolist()))
    print("\nMonths:", sorted(df["Month"].dropna().unique().tolist()))