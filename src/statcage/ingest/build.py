"""Run the whole data pipeline: download, clean, validate, then save Parquet tables.

Nothing is saved unless every table passes validation.
"""

from pathlib import Path

from statcage.ingest.clean import clean_events, clean_fight_stats, clean_fighters, clean_fights
from statcage.ingest.download import download_all
from statcage.ingest.validate import validate_all

PROCESSED_DIR = Path(__file__).resolve().parents[3] / "data" / "processed"


def build(refresh: bool = False) -> None:
    download_all(refresh=refresh)

    events = clean_events()
    fighters = clean_fighters()
    fights = clean_fights(events, fighters)
    stats = clean_fight_stats(events, fights)

    validate_all(events, fighters, fights, stats)
    print("Validation passed")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    tables = {"events": events, "fighters": fighters, "fights": fights, "fight_stats": stats}
    for name, table in tables.items():
        path = PROCESSED_DIR / f"{name}.parquet"
        table.to_parquet(path, index=False)
        print(f"{name}: {len(table):,} rows -> {path}")


if __name__ == "__main__":
    build()
