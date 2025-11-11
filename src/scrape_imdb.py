import argparse
import json
import re
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional

import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

# -----------------------------
# Config
# -----------------------------
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
BASE_URL = "https://www.imdb.com/title/{tid}/"
DEFAULT_TIMEOUT = 15  # seconds

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s"
)

# -----------------------------
# Helpers
# -----------------------------
def build_session(total_retries: int = 3, backoff_factor: float = 0.5) -> requests.Session:
    """
    Create a requests Session with retry + backoff for transient errors.
    """
    retry = Retry(
        total=total_retries,
        read=total_retries,
        connect=total_retries,
        status=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s = requests.Session()
    s.headers.update(HEADERS)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s

def read_ids(path: Path) -> List[str]:
    """
    Read IMDb title IDs (one per line). Keeps only lines starting with 'tt'.
    """
    ids = []
    for line in path.read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if t and t.startswith("tt"):
            ids.append(t)
    return ids

def _sel_text(soup: BeautifulSoup, selector: str) -> Optional[str]:
    el = soup.select_one(selector)
    return el.get_text(strip=True) if el else None

def _parse_json_ld(soup: BeautifulSoup) -> dict:
    """
    Safely parse JSON-LD block if present.
    """
    data_ld = {}
    json_ld = soup.find("script", type="application/ld+json")
    if json_ld and json_ld.string:
        try:
            data_ld = json.loads(json_ld.string)
        except Exception:
            data_ld = {}
    return data_ld

def _parse_year(soup: BeautifulSoup, data_ld: dict) -> Optional[int]:
    """
    Prefer the visible metadata year; fallback to datePublished in JSON-LD.
    """
    year = None
    # Visible “Release” link within the hero metadata inline list
    y_el = soup.select_one("ul[data-testid='hero-title-block__metadata'] li a[href*='releaseinfo']")
    if y_el:
        m = re.search(r"(\d{4})", y_el.get_text(strip=True))
        if m:
            try:
                year = int(m.group(1))
            except Exception:
                year = None
    if year is None:
        # Fallback: JSON-LD datePublished
        dp = data_ld.get("datePublished")
        if isinstance(dp, str):
            m = re.match(r"(\d{4})", dp)
            if m:
                try:
                    year = int(m.group(1))
                except Exception:
                    year = None
    return year

def _parse_genres(soup: BeautifulSoup, data_ld: dict) -> Optional[List[str]]:
    genres = data_ld.get("genre")
    if isinstance(genres, str):
        genres = [genres]
    if genres:
        return [g for g in genres if isinstance(g, str) and g.strip()]
    # Fallback: anchor links with genres param
    found = [g.get_text(strip=True) for g in soup.select("a[href*='genres=']")]
    return found or None

def _parse_runtime_minutes(data_ld: dict) -> Optional[int]:
    """
    JSON-LD duration is ISO8601 like 'PT142M'.
    """
    dur = data_ld.get("duration")
    if isinstance(dur, str) and dur.startswith("PT"):
        m = re.search(r"PT(\d+)M", dur)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return None
    return None

def _parse_certificate(soup: BeautifulSoup) -> Optional[str]:
    # IMDb certificate areas can vary; try storyline certificate or parental guide link
    cert_el = soup.select_one("[data-testid='storyline-certificate'] a, a[href*='parentalguide']")
    return cert_el.get_text(strip=True) if cert_el else None

def _parse_directors(soup: BeautifulSoup, data_ld: dict) -> Optional[List[str]]:
    """
    Robustly parse directors:
    1) JSON-LD 'director'
    2) JSON-LD 'creator' (sometimes director(s) under 'creator')
    3) Page principal credits list (no deprecated :contains)
    """
    # 1) JSON-LD director
    names: List[str] = []
    if "director" in data_ld:
        d = data_ld["director"]
        if isinstance(d, list):
            names = [x.get("name") for x in d if isinstance(x, dict) and x.get("name")]
        elif isinstance(d, dict) and d.get("name"):
            names = [d["name"]]

    # 2) JSON-LD creator fallback (not perfect, but often includes directors)
    if not names and "creator" in data_ld:
        creators = data_ld["creator"]
        if isinstance(creators, list):
            for c in creators:
                if isinstance(c, dict) and c.get("@type") == "Person" and c.get("name"):
                    names.append(c["name"])

    # 3) Page principal credits fallback
    if not names:
        for li in soup.select("li[data-testid='title-pc-principal-credit']"):
            label_el = li.find(["span", "h3"])
            label_txt = label_el.get_text(strip=True) if label_el else ""
            if "Director" in label_txt:  # matches 'Director' or 'Directors'
                anchors = li.select("a[href*='/name/']")
                extracted = [a.get_text(strip=True) for a in anchors if a.get_text(strip=True)]
                if extracted:
                    names = extracted
                    break

    names = [n.strip() for n in names if n and str(n).strip().lower() != "nan"]
    return names or None

def parse_title_page(html: str) -> Dict:
    """
    Parse a single title page HTML into a row dict.
    """
    soup = BeautifulSoup(html, "html.parser")
    data_ld = _parse_json_ld(soup)

    # Title
    title = data_ld.get("name") or _sel_text(soup, "h1[data-testid='hero-title-block__title']")

    # Rating & votes (from JSON-LD aggregateRating)
    rating, votes = None, None
    try:
        agg = data_ld.get("aggregateRating") or {}
        rv = agg.get("ratingValue")
        rc = agg.get("ratingCount")
        rating = float(rv) if rv is not None else None
        votes = int(rc) if rc is not None else None
    except Exception:
        pass

    # Year
    year = _parse_year(soup, data_ld)

    # Genres
    genres = _parse_genres(soup, data_ld)

    # Runtime minutes
    runtime_min = _parse_runtime_minutes(data_ld)

    # Certificate
    certificate = _parse_certificate(soup)

    # Directors
    directors_list = _parse_directors(soup, data_ld)

    return {
        "title": title,
        "year": year,
        "rating": rating,
        "votes": votes,
        "genres": ", ".join(genres) if genres else None,
        "runtime_min": runtime_min,
        "certificate": certificate,
        "directors": ", ".join(directors_list) if directors_list else None,
    }

def scrape_ids(ids: List[str], sleep_s: float = 1.5, timeout: int = DEFAULT_TIMEOUT) -> pd.DataFrame:
    """
    Scrape multiple title IDs into a DataFrame.
    - sleep_s: polite delay between requests
    - timeout: request timeout (seconds)
    """
    session = build_session()
    rows = []
    for i, tid in enumerate(ids, start=1):
        url = BASE_URL.format(tid=tid)
        try:
            resp = session.get(url, timeout=timeout)
            if resp.status_code != 200:
                logging.warning(f"{i}/{len(ids)} [warn] {tid} -> HTTP {resp.status_code}")
                time.sleep(sleep_s)
                continue
            row = parse_title_page(resp.text)
            row["imdb_id"] = tid
            row["url"] = url
            rows.append(row)
            logging.info(f"{i}/{len(ids)} [ok] {tid} -> {row.get('title')}")
            time.sleep(sleep_s)
        except Exception as e:
            logging.error(f"{i}/{len(ids)} [error] {tid}: {e}")
            time.sleep(sleep_s)
    return pd.DataFrame(rows)

# -----------------------------
# Main
# -----------------------------
def main():
    ap = argparse.ArgumentParser(description="Scrape IMDb title pages -> tidy CSV + summary.json")
    ap.add_argument("--ids", type=str, required=True, help="Path to text file with IMDb title IDs (one per line).")
    ap.add_argument("--out", type=str, required=True, help="Output CSV path.")
    ap.add_argument("--sleep", type=float, default=1.5, help="Seconds to sleep between requests (politeness).")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Per-request timeout in seconds.")
    args = ap.parse_args()

    ids = read_ids(Path(args.ids))
    if not ids:
        logging.error("No valid IMDb IDs found. Ensure your file contains lines like 'tt0111161'.")
        raise SystemExit(2)

    df = scrape_ids(ids, sleep_s=args.sleep, timeout=args.timeout)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)

    # Summary for quick reporting
    summary = {
        "n_titles": int(len(df)),
        "rating_mean": float(pd.to_numeric(df.get("rating"), errors="coerce").mean()) if len(df) else None,
        "rating_median": float(pd.to_numeric(df.get("rating"), errors="coerce").median()) if len(df) else None,
        "top_genres": (
            df["genres"].dropna().str.split(", ").explode().value_counts().head(10).to_dict()
            if "genres" in df.columns and len(df)
            else {}
        ),
        "n_with_directors": int(df["directors"].notna().sum()) if "directors" in df.columns else 0,
    }
    reports_dir = Path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    logging.info(f"Saved CSV -> {out_path}")
    logging.info(f"Saved summary -> {reports_dir/'summary.json'}")

if __name__ == "__main__":
    main()
