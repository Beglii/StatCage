"""Build clean tables from the raw ufcstats CSVs."""

from collections import Counter
from datetime import date

import pandas as pd

from statcage.ingest.download import BASE_URL
from statcage.ingest.parse import (
    fight_seconds,
    id_from_url,
    parse_clock,
    parse_count,
    parse_date,
    parse_height,
    parse_landed_attempted,
    parse_method,
    parse_outcome,
    parse_reach,
    parse_round_lengths,
    parse_scheduled_rounds,
    parse_weight,
    parse_weight_class,
    text_or_none,
)
from statcage.scrape.fetch import cache_path

# Spelling differences between the fight results and the fighter list.
NAME_FIXES = {
    "Nick Galanti": "Nicholas Galanti",
    "Rafael Cerquiera": "Rafael Cerqueira",
}

# Upper weight limit (lbs) of each division, used to tell same-named fighters apart.
DIVISION_LIMITS = {
    "Strawweight": 115,
    "Flyweight": 125,
    "Bantamweight": 135,
    "Featherweight": 145,
    "Lightweight": 155,
    "Welterweight": 170,
    "Middleweight": 185,
    "Light Heavyweight": 205,
    "Heavyweight": 265,
}

# Stat columns written as "landed of attempted", and the name prefix each one gets.
LANDED_ATTEMPTED = {
    "SIG.STR.": "sig",
    "TOTAL STR.": "total",
    "TD": "td",
    "HEAD": "head",
    "BODY": "body",
    "LEG": "leg",
    "DISTANCE": "distance",
    "CLINCH": "clinch",
    "GROUND": "ground",
}


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


def build_name_index(fighters: pd.DataFrame) -> dict[str, list[dict]]:
    """Map each name and alt_name to every fighter who has it."""
    index = {}
    for fighter in fighters.to_dict("records"):
        for name in (fighter["name"], fighter["alt_name"]):
            if pd.notna(name):
                index.setdefault(name, []).append(fighter)
    return index


def age_on(dob: date, day: date) -> float:
    return (day - dob).days / 365.25


def match_fighter(name: str, index: dict, weight_class: str | None, fight_date: date) -> dict:
    """Find the fighter behind a name in a bout, using age and weight when the name is shared."""
    name = NAME_FIXES.get(name, name)
    candidates = index.get(name, [])
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ValueError(f"No fighter named {name!r}")

    # Shared name: rule out anyone under 18 or over 45 on fight night...
    plausible = [
        fighter for fighter in candidates
        if pd.isna(fighter["dob"]) or 18 <= age_on(fighter["dob"], fight_date) <= 45
    ]

    # ...then pick the one whose listed weight is closest to the division limit.
    limit = DIVISION_LIMITS.get(weight_class)

    def weight_gap(fighter: dict) -> float:
        if limit is None or pd.isna(fighter["weight_lbs"]):
            return float("inf")
        return abs(fighter["weight_lbs"] - limit)

    plausible.sort(key=weight_gap)
    if not plausible or (len(plausible) > 1 and weight_gap(plausible[0]) == weight_gap(plausible[1])):
        raise ValueError(f"Can't tell which {name!r} fought on {fight_date} ({weight_class})")
    return plausible[0]


def clean_fights(events: pd.DataFrame, fighters: pd.DataFrame) -> pd.DataFrame:
    raw = read_raw("ufc_fight_results.csv")

    # Link each fight to its event. Rows whose event isn't in the events table are
    # old copies of renamed events (or Road to UFC), so they get dropped.
    event_ids = dict(zip(events["name"], events["event_id"]))
    event_dates = dict(zip(events["event_id"], events["date"]))
    raw["event_id"] = raw["EVENT"].map(event_ids)
    for event_name, count in raw.loc[raw["event_id"].isna(), "EVENT"].value_counts().items():
        print(f"Dropped {count} fights from unlisted event: {event_name}")
    raw = raw[raw["event_id"].notna()]

    index = build_name_index(fighters)
    shared_name_picks = Counter()
    rows = []
    for r in raw.to_dict("records"):
        fight_date = event_dates[r["event_id"]]
        division = parse_weight_class(r["WEIGHTCLASS"])
        name_a, name_b = r["BOUT"].split(" vs. ")
        fighter_a = match_fighter(name_a, index, division["weight_class"], fight_date)
        fighter_b = match_fighter(name_b, index, division["weight_class"], fight_date)
        for name, fighter in ((name_a, fighter_a), (name_b, fighter_b)):
            if len(index.get(name, [])) > 1:
                shared_name_picks[(name, fighter["nickname"], division["weight_class"])] += 1

        result, winner = parse_outcome(r["OUTCOME"])
        method, method_detail = parse_method(r["METHOD"], r["DETAILS"])
        end_round = int(r["ROUND"])
        end_time_s = parse_clock(r["TIME"])

        rows.append({
            "fight_id": id_from_url(r["URL"]),
            "event_id": r["event_id"],
            "fighter_a_id": fighter_a["fighter_id"],
            "fighter_b_id": fighter_b["fighter_id"],
            "result": result,
            "winner_id": {"a": fighter_a["fighter_id"], "b": fighter_b["fighter_id"]}.get(winner),
            "method": method,
            "method_detail": method_detail,
            "end_round": end_round,
            "end_time_s": end_time_s,
            "scheduled_rounds": parse_scheduled_rounds(r["TIME FORMAT"]),
            "fight_time_s": fight_seconds(end_round, end_time_s, parse_round_lengths(r["TIME FORMAT"])),
            **division,
            "referee": text_or_none(r["REFEREE"]),
        })

    print("Shared-name picks (name -> nickname chosen, division, fights):")
    for (name, nickname, weight_class), count in sorted(shared_name_picks.items()):
        print(f"  {name} -> {nickname}, {weight_class}, {count}")

    fights = pd.DataFrame(rows)
    fights["scheduled_rounds"] = fights["scheduled_rounds"].astype("Int64")
    if fights["fight_id"].duplicated().any():
        raise ValueError("Duplicate fight_id after dropping unlisted events")
    return fights


def clean_fight_stats(events: pd.DataFrame, fights: pd.DataFrame) -> pd.DataFrame:
    raw = read_raw("ufc_fight_stats.csv")

    # Empty rows are placeholders for old fights that have no stats.
    empty = raw["FIGHTER"] == ""
    print(f"Dropped {empty.sum()} empty stat rows")
    raw = raw[~empty]

    # The stats file has no fight URL, only event + bout, so look the fight up in the
    # results file. If two fights share an event + bout, we can't tell them apart.
    results = read_raw("ufc_fight_results.csv")
    results = results[results["EVENT"].isin(events["name"])]
    fight_ids = {}
    ambiguous = set()
    for r in results.to_dict("records"):
        key = (r["EVENT"], r["BOUT"])
        if key in fight_ids:
            ambiguous.add(key)
        fight_ids[key] = id_from_url(r["URL"])

    sides = fights.set_index("fight_id")[["fighter_a_id", "fighter_b_id"]].to_dict("index")

    dropped = Counter()
    rows = []
    for r in raw.to_dict("records"):
        key = (r["EVENT"], r["BOUT"])
        if key in ambiguous:
            dropped[f"two fights share {r['EVENT']}: {r['BOUT']}"] += 1
            continue
        if key not in fight_ids:
            dropped[f"unlisted event {r['EVENT']}"] += 1
            continue
        fight_id = fight_ids[key]

        # FIGHTER is always one side of the bout, so reuse the IDs clean_fights picked.
        name_a, name_b = r["BOUT"].split(" vs. ")
        if r["FIGHTER"] == name_a:
            fighter_id = sides[fight_id]["fighter_a_id"]
        elif r["FIGHTER"] == name_b:
            fighter_id = sides[fight_id]["fighter_b_id"]
        else:
            raise ValueError(f"{r['FIGHTER']!r} is not in bout {r['BOUT']!r}")

        row = {
            "fight_id": fight_id,
            "fighter_id": fighter_id,
            "round": int(r["ROUND"].removeprefix("Round ")),
            "kd": parse_count(r["KD"]),
        }
        for column, prefix in LANDED_ATTEMPTED.items():
            row[f"{prefix}_landed"], row[f"{prefix}_attempted"] = parse_landed_attempted(r[column])
        row["sub_att"] = parse_count(r["SUB.ATT"])
        row["rev"] = parse_count(r["REV."])
        row["ctrl_s"] = parse_clock(r["CTRL"])
        rows.append(row)

    for reason, count in sorted(dropped.items()):
        print(f"Dropped {count} stat rows: {reason}")

    stats = pd.DataFrame(rows)
    stats["ctrl_s"] = stats["ctrl_s"].astype("Int64")

    if stats.duplicated(["fight_id", "fighter_id", "round"]).any():
        raise ValueError("Same fighter has two stat rows for one round")
    per_round = stats.groupby(["fight_id", "round"])["fighter_id"].nunique()
    if (per_round != 2).any():
        raise ValueError(f"{(per_round != 2).sum()} rounds don't have exactly one row per fighter")

    missing = ~fights["fight_id"].isin(stats["fight_id"])
    print(f"{missing.sum()} fights have no stats")
    return stats


if __name__ == "__main__":
    events = clean_events()
    fighters = clean_fighters()
    fights = clean_fights(events, fighters)
    print()
    print(fights.head(3).T, "\n")
    print(f"{len(fights):,} fights")
    print(fights.isna().sum())
    print()
    stats = clean_fight_stats(events, fights)
    print()
    print(stats.head(2).T, "\n")
    print(f"{len(stats):,} stat rows")
    print(stats.isna().sum()[stats.isna().sum() > 0])
