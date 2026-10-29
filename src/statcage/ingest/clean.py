"""Build clean tables from the raw ufcstats CSVs."""

import pandas as pd

from statcage.ingest.download import BASE_URL
from statcage.ingest.parse import (
    id_from_url,
    parse_date,
    parse_height,
    parse_reach,
    parse_weight,
    text_or_none,
)
from statcage.scrape.fetch import cache_path


def read_raw(name: str) -> pd.DataFrame:
    """Load one downloaded CSV with every value as text, spaces trimmed."""
    path = cache_path(f"{BASE_URL}/{name}")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return df.apply(lambda column: column.str.strip())


def clean_events() -> pd.DataFrame:
    raw = read_raw("ufc_event_details.csv")
    events = pd.DataFrame({
        "event_id": raw["URL"].map(id_from_url),
        "name": raw["EVENT"],
        "date": raw["DATE"].map(parse_date),
        "location": raw["LOCATION"],
        "country": raw["LOCATION"].str.split(",").str[-1].str.strip(),
    })
    return events.sort_values("date").reset_index(drop=True)


def clean_fighters() -> pd.DataFrame:
    tott = read_raw("ufc_fighter_tott.csv")
    details = read_raw("ufc_fighter_details.csv")
    raw = tott.merge(details, on="URL", how="left").fillna("")

    name = (raw["FIRST"] + " " + raw["LAST"]).str.strip()
    name = name.where(name != "", raw["FIGHTER"])

    return pd.DataFrame({
        "fighter_id": raw["URL"].map(id_from_url),
        "name": name,
        "alt_name": raw["FIGHTER"].where(raw["FIGHTER"] != name, None),
        "nickname": raw["NICKNAME"].map(text_or_none),
        "height_in": raw["HEIGHT"].map(parse_height).astype("Int64"),
        "weight_lbs": raw["WEIGHT"].map(parse_weight).astype("Int64"),
        "reach_in": raw["REACH"].map(parse_reach).astype("Int64"),
        "stance": raw["STANCE"].map(text_or_none),
        "dob": raw["DOB"].map(parse_date),
    })


if __name__ == "__main__":
    events = clean_events()
    fighters = clean_fighters()
    print(events.tail(), "\n")
    print(fighters.head(), "\n")
    print(fighters.isna().sum())
