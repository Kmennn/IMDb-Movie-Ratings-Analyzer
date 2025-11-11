import argparse
from pathlib import Path
import logging
import math

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# -----------------------------
# Config
# -----------------------------
FIG_DIR = Path("src/figures")
REPORTS_DIR = Path("reports")
FIG_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s"
)

# -----------------------------
# Utils
# -----------------------------
def save_current_fig(filename: str, dpi: int = 120):
    """Save the current matplotlib figure and close it."""
    out_path = FIG_DIR / filename
    plt.gcf().savefig(out_path, bbox_inches="tight", dpi=dpi)
    plt.close()
    logging.info(f"Saved figure -> {out_path}")

def coerce_numeric(series: pd.Series) -> pd.Series:
    """Safely coerce to numeric."""
    return pd.to_numeric(series, errors="coerce")

def normalize_genres(df: pd.DataFrame) -> pd.DataFrame:
    if "genres" not in df.columns:
        return df
    s = df["genres"].astype(str).replace({"nan": ""}).fillna("")
    main = (
        s.str.split(",")
         .str[0]
         .str.strip()
         .replace({"": np.nan})
    )
    df["main_genre"] = main
    return df

def add_decade(df: pd.DataFrame) -> pd.DataFrame:
    if "year" not in df.columns:
        return df
    y = coerce_numeric(df["year"])
    df["decade"] = (y // 10) * 10
    return df

def to_director_list(val):
    """Make sure each row becomes a list of director names or None."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    if isinstance(val, list):
        cleaned = [str(x).strip() for x in val if str(x).strip() not in {"", "nan"}]
        return cleaned or None
    s = str(val).strip()
    if s == "" or s.lower() == "nan":
        return None
    parts = [p.strip() for p in s.split(",") if p.strip() not in {"", "nan"}]
    return parts or None

# -----------------------------
# EDA Steps
# -----------------------------
def plot_rating_histogram(df: pd.DataFrame):
    if "rating" not in df.columns:
        logging.warning("rating column not found; skipping histogram.")
        return
    r = coerce_numeric(df["rating"]).dropna()
    if r.empty:
        logging.warning("No numeric ratings; skipping histogram.")
        return
    r.plot(kind="hist", bins=15, title="IMDb Rating Distribution")
    plt.xlabel("Rating")
    plt.ylabel("Count")
    save_current_fig("ratings_histogram.png")

def plot_rating_by_main_genre(df: pd.DataFrame):
    needed = {"rating", "main_genre"}
    if not needed.issubset(df.columns):
        logging.warning("Columns rating/main_genre missing; skipping genre boxplot.")
        return
    tmp = df.copy()
    tmp["rating"] = coerce_numeric(tmp["rating"])
    tmp = tmp.dropna(subset=["rating", "main_genre"])
    if tmp.empty:
        logging.warning("No data for rating-by-genre; skipping.")
        return
    tmp.boxplot(column="rating", by="main_genre", rot=45)
    plt.title("Rating by Main Genre")
    plt.suptitle("")
    plt.xlabel("Main Genre")
    plt.ylabel("Rating")
    save_current_fig("rating_by_genre_boxplot.png")

def plot_votes_vs_rating(df: pd.DataFrame):
    for col in ("rating", "votes"):
        if col not in df.columns:
            logging.warning(f"{col} not found; skipping votes vs rating scatter.")
            return
    tmp = df.copy()
    tmp["rating"] = coerce_numeric(tmp["rating"])
    tmp["votes"] = coerce_numeric(tmp["votes"])
    tmp = tmp.dropna(subset=["rating", "votes"])
    if tmp.empty:
        logging.warning("No numeric votes/ratings; skipping scatter.")
        return
    tmp.plot(kind="scatter", x="votes", y="rating", title="Votes vs Rating", alpha=0.7)
    plt.xlabel("Votes")
    plt.ylabel("Rating")
    save_current_fig("votes_vs_rating_scatter.png")

def plot_rating_by_decade(df: pd.DataFrame):
    if "decade" not in df.columns or "rating" not in df.columns:
        logging.warning("Columns rating/decade missing; skipping decade boxplot.")
        return
    tmp = df.copy()
    tmp["rating"] = coerce_numeric(tmp["rating"])
    tmp["decade"] = coerce_numeric(tmp["decade"])
    tmp = tmp.dropna(subset=["rating", "decade"])
    if tmp.empty:
        logging.warning("No data for rating-by-decade; skipping.")
        return
    tmp.boxplot(column="rating", by="decade", rot=45)
    plt.title("Rating by Decade")
    plt.suptitle("")
    plt.xlabel("Decade")
    plt.ylabel("Rating")
    save_current_fig("rating_by_decade_boxplot.png")

def table_top10_by_votes(df: pd.DataFrame):
    if "votes" not in df.columns:
        logging.warning("votes column not found; skipping top10 by votes.")
        return
    tmp = df.copy()
    tmp["votes"] = coerce_numeric(tmp["votes"])
    tmp = tmp.sort_values("votes", ascending=False).head(10)
    cols = [c for c in ["title", "year", "rating", "votes"] if c in tmp.columns]
    if not cols:
        logging.warning("No expected columns to print for top10 by votes.")
        return
    print("\nTop 10 Movies by Votes:\n", tmp[cols])
    outp = REPORTS_DIR / "top10_by_votes.csv"
    tmp.to_csv(outp, index=False)
    logging.info(f"Saved table -> {outp}")

def table_top_directors_avg_rating(df: pd.DataFrame, min_films: int = 2):
    if "directors" not in df.columns or "rating" not in df.columns:
        logging.warning("directors/rating missing; skipping director leaderboard.")
        return
    tmp = df.copy()
    tmp["rating"] = coerce_numeric(tmp["rating"])
    tmp["directors"] = tmp["directors"].apply(to_director_list)
    tmp = tmp.dropna(subset=["rating", "directors"]).explode("directors").dropna(subset=["directors"])
    if tmp.empty:
        logging.info("No usable director data; skipping.")
        return
    director_stats = (
        tmp.groupby("directors", dropna=True)
          .agg(n_films=("title", "count"), avg_rating=("rating", "mean"))
          .query("n_films >= @min_films")
          .sort_values("avg_rating", ascending=False)
    )
    if director_stats.empty:
        logging.info(f"No directors with at least {min_films} films; skipping.")
        return
    print(f"\nTop Directors by Avg Rating (min {min_films} films):\n", director_stats.head(10))
    outp = REPORTS_DIR / "top_directors_avg_rating.csv"
    director_stats.to_csv(outp)
    logging.info(f"Saved table -> {outp}")

# -----------------------------
# Main
# -----------------------------
def main():
    ap = argparse.ArgumentParser(description="IMDb Ratings EDA")
    ap.add_argument("--input", type=str, required=True, help="Path to tidy CSV from scraper.")
    ap.add_argument("--min_director_films", type=int, default=2, help="Min films per director to include.")
    args = ap.parse_args()

    df = pd.read_csv(args.input)
    # Derived columns
    df = add_decade(df)
    df = normalize_genres(df)

    # Plots
    plot_rating_histogram(df)
    plot_rating_by_main_genre(df)
    plot_votes_vs_rating(df)
    plot_rating_by_decade(df)

    # Tables
    table_top10_by_votes(df)
    table_top_directors_avg_rating(df, min_films=args.min_director_films)

    logging.info(f"Figures saved to {FIG_DIR}")

if __name__ == "__main__":
    main()
