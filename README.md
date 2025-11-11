# Minor Project: IMDb Movie Ratings Analyzer

Scrape movie metadata and ratings from IMDb pages using `requests` + `BeautifulSoup`, build a tidy dataset, then perform EDA and plots.

## Quick Start
1. Create venv and install deps:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   pip install -r requirements.txt
   ```

2. Provide a list of IMDb title IDs in `data/raw/title_ids_sample.txt` (already included with some examples).
   - IDs look like `tt0111161` (The Shawshank Redemption).

3. Run the scraper to build the dataset:
   ```bash
   python src/scrape_imdb.py --ids data/raw/title_ids_sample.txt --out data/processed/imdb_movies.csv
   ```

4. Run EDA:
   ```bash
   python src/eda_plots.py --input data/processed/imdb_movies.csv
   ```

5. Check outputs:
   - Tidy CSV: `data/processed/imdb_movies.csv`
   - Figures: `src/figures/` (ratings histogram, boxplots by genre/decade, votes vs rating scatter)
   - Report metrics (small JSON): `reports/summary.json`

## Notes
- Use responsibly. IMDb's site, structure, and robots policy may change; keep your request rate low.
- If scraping is blocked, consider caching HTML first or using the OMDb API (requires an API key). This template focuses on requests + BeautifulSoup to satisfy assignment requirements.

## Deliverables
- PDF/DOCX report (use `reports/report_template.md`), with figures and observations.
- Source code in `src/`.
- Dataset CSV in `data/processed/`.
- Zip the whole folder for submission.