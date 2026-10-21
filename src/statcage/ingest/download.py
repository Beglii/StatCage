"""Download the ufcstats CSVs published by github.com/Greco1899/scrape_ufc_stats.

That project scrapes ufcstats.com and refreshes these files every week.
"""

from statcage.scrape.fetch import cache_path, fetch

BASE_URL = "https://raw.githubusercontent.com/Greco1899/scrape_ufc_stats/main"

FILES = [
    "ufc_event_details.csv",
    "ufc_fight_details.csv",
    "ufc_fight_results.csv",
    "ufc_fight_stats.csv",
    "ufc_fighter_details.csv",
    "ufc_fighter_tott.csv",
]


def download_all(refresh: bool = False) -> None:
    """Download each CSV (or reuse the cached copy) and print where it was saved."""
    for name in FILES:
        url = f"{BASE_URL}/{name}"
        text = fetch(url, refresh=refresh)
        lines = text.count("\n")
        print(f"{name}: {lines:,} lines -> {cache_path(url)}")


if __name__ == "__main__":
    download_all(refresh=True)
