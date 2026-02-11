from pathlib import Path
import re

import pandas as pd


DATA_DIR = Path("data/monthly")


# ---------------------------
# Parse YYYY_MM.csv filename
# ---------------------------
FILENAME_RE = re.compile(r"(?P<month>\d{2})_(?P<year>\d{4})\.csv")


def load_monthly_fg(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    files = list(data_dir.glob("*.csv"))

    if not files:
        raise RuntimeError(f"No CSV files found in {data_dir.resolve()}")

    dfs = []

    for path in files:
        m = FILENAME_RE.match(path.name)
        if not m:
            print(f"Skipping unrecognized filename: {path.name}")
            continue

        year = int(m.group("year"))
        month = int(m.group("month"))

        df = pd.read_csv(path)

        # Add season + month
        df["Season"] = year
        df["Month"] = month

        dfs.append(df)

    all_df = pd.concat(dfs, ignore_index=True)

    # ---------------------------
    # Standardize column names
    # ---------------------------
    rename_map = {
        "Tm": "Team",
        "SO": "K",
    }

    all_df = all_df.rename(columns=rename_map)

    # ---------------------------
    # Keep seasons 2021+
    # ---------------------------
    all_df = all_df[all_df["Season"] >= 2021]

    # ---------------------------
    # Compute custom FWOBA
    # (weights placeholder)
    # ---------------------------
    weights = {
        "R": 1.0,
        "H": 1.0,
        "2B": 1.2,
        "HR": 2.0,
        "RBI": 1.0,
        "SB": 1.5,
        "BB": 0.8,
    }

    def compute_fwoba(row):
        total = 0.0
        for stat, w in weights.items():
            total += row.get(stat, 0) * w
        return total / row["PA"] if row["PA"] > 0 else 0.0

    all_df["FWOBA"] = all_df.apply(compute_fwoba, axis=1)

    return all_df


if __name__ == "__main__":
    df = load_monthly_fg()
    print(df.head())
    print("\nRows:", len(df))
    print("\nSeasons:", sorted(df["Season"].unique()))
    print("\nMonths:", sorted(df["Month"].unique()))
