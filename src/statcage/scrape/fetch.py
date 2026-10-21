"""Polite, cached downloads from ufcstats.com."""

import time
from pathlib import Path
from urllib.parse import urlparse

import requests

# Project root is 3 folders up from this file: scrape -> statcage -> src -> root
RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw"

USER_AGENT = "StatCage/0.1 (student project; github.com/Beglii/StatCage)"
DELAY_SECONDS = 1.0
MAX_RETRIES = 3

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT


def cache_path(url: str) -> Path:
    """Turn a URL into a file path under data/raw.

    http://ufcstats.com/event-details/abc123 -> data/raw/event-details/abc123.html
    """
    parsed = urlparse(url)
    name = parsed.path.strip("/") or "index"
    if parsed.query:
        name += "_" + parsed.query.replace("=", "-").replace("&", "_")
    return RAW_DIR / f"{name}.html"


def fetch(url: str, refresh: bool = False) -> str:
    """Return the HTML for url, from the cache if we already have it."""
    path = cache_path(url)
    if path.exists() and not refresh:
        return path.read_text(encoding="utf-8")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = _session.get(url, timeout=30)
            response.raise_for_status()
            break
        except requests.RequestException:
            if attempt == MAX_RETRIES:
                raise
            time.sleep(DELAY_SECONDS * 2 ** attempt)
    time.sleep(DELAY_SECONDS)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(response.text, encoding="utf-8")
    return response.text
