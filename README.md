# 🎬 IMDb Movie Ratings Analyzer

**Minor Project – Virendra Mahajan**

A Python project that scrapes IMDb pages (Requests + BeautifulSoup), builds a tidy dataset (Pandas), and performs EDA (Matplotlib) to explore trends in ratings, genres, and directors.

## ✨ Highlights
- Web scraping pipeline with retries & polite rate-limiting
- Cleaned dataset + summary stats
- Plots: rating distribution, genre & decade boxplots, votes vs rating
- Tables: Top 10 by votes, Top directors by average rating

## ⚙️ Run
```bash
python src/scrape_imdb.py --ids data/raw/title_ids_sample.txt --out data/processed/imdb_movies.csv
python src/eda_plots.py --input data/processed/imdb_movies.csv
