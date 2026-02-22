# Fantasy Monthly Trend Lab ⚾

A Streamlit-based analytics application for visualizing MLB hitter performance trends at the monthly level.

This tool was built to support fantasy baseball decision-making by combining:

- Custom fantasy-weighted rate metrics
- Real MLB performance stats
- League-relative context
- Playing time validation

The goal: separate signal from noise in monthly performance swings.

---

## Live Features

### 1. Monthly Performance Trends
Visualizes selected metrics across April–September for any player-season:

- **FWOBA** (custom fantasy-weighted wOBA analog)
- wOBA
- OPS
- Additional advanced metrics (if present in dataset)

Smooth interpolation highlights directional trend without overfitting.

---

### 2. League Baseline Overlay
Each chart includes a dotted league-average reference line calculated across:

- All players
- All years in dataset
- Plate-appearance-weighted (for rate stats)

This provides immediate context:
- Above league
- Below league
- Trending toward mean

---

### 3. Playing Time Context
A secondary chart plots monthly Plate Appearances:

- Identifies injury-driven volatility
- Highlights small-sample noise
- Differentiates performance slump vs availability issue

A reference threshold line indicates typical full-time usage.

---

## Custom Metric: FWOBA

FWOBA (Fantasy Weighted On-Base Average) is a rate stat designed to mimic real MLB wOBA behavior while reflecting custom fantasy scoring categories.

### Categories Included
- Hits
- Runs
- Doubles
- Home Runs
- Stolen Bases
- Walks
- RBIs
- Strikeouts (negative weight)

### Methodology
1. Weighted per-plate-appearance scoring
2. Standardization to z-score
3. Rescaled to match real MLB wOBA distribution:
   - League average ≈ .320
   - Realistic monthly volatility (~.045 std dev)
   - No artificial ceiling or floor

This makes FWOBA visually and statistically comparable to real wOBA.

---

## Technical Stack

- **Python 3.13**
- **Streamlit 1.54**
- **Pandas 2.3**
- **NumPy 2.4**
- **Altair 6**

The app uses vectorized operations and grouped aggregation for efficient monthly metric computation.

---

## Project Structure
