"""Build fighter profiles as of any date, using only fights before that date.

Fights on the same night can't see each other, because we don't know their order.
"""

import pandas as pd

from statcage.ingest.build import PROCESSED_DIR

STANDARD_DIVISIONS = [
    "Strawweight",
    "Flyweight",
    "Bantamweight",
    "Featherweight",
    "Lightweight",
    "Welterweight",
    "Middleweight",
    "Light Heavyweight",
    "Heavyweight",
]

FINISHES = ["KO/TKO", "Submission"]

# Stats added up per fighter per fight. "opp_" versions are what the opponent did to them.
STAT_TOTALS = ["kd", "sig_landed", "sig_attempted", "td_landed", "td_attempted", "sub_att", "ctrl_s"]
OPPONENT_TOTALS = ["kd", "sig_landed", "sig_attempted", "td_landed", "td_attempted"]

CAREER_TOTALS = [
    "fights",
    "wins",
    "losses",
    "finish_wins",
    "finish_losses",
    "stat_s",
    "ctrl_known_s",
    *STAT_TOTALS,
    *[f"opp_{column}" for column in OPPONENT_TOTALS],
]

PROFILE_COLUMNS = [
    "fights_before",
    "wins_before",
    "losses_before",
    "win_rate",
    "finish_win_rate",
    "finish_loss_rate",
    "win_streak",
    "days_since_last",
    "age",
    "height_in",
    "reach_in",
    "sig_landed_per_min",
    "sig_absorbed_per_min",
    "sig_accuracy",
    "sig_defense",
    "td_per_15",
    "td_accuracy",
    "td_defense",
    "kd_per_15",
    "kd_absorbed_per_15",
    "sub_att_per_15",
    "ctrl_per_15",
    "division",
    "women",
]


def fighter_lines(fights: pd.DataFrame, events: pd.DataFrame, stats: pd.DataFrame) -> pd.DataFrame:
    """One row per fighter per fight: the result, their totals, and their opponent's totals."""
    dated = fights.merge(events[["event_id", "date"]], on="event_id")
    dated["date"] = pd.to_datetime(dated["date"])

    shared = ["fight_id", "date", "result", "winner_id", "method", "weight_class", "womens", "fight_time_s"]
    side_a = dated[shared].assign(fighter_id=dated["fighter_a_id"], opponent_id=dated["fighter_b_id"])
    side_b = dated[shared].assign(fighter_id=dated["fighter_b_id"], opponent_id=dated["fighter_a_id"])
    lines = pd.concat([side_a, side_b], ignore_index=True)

    won = lines["winner_id"] == lines["fighter_id"]
    lost = (lines["result"] == "win") & ~won
    finished = lines["method"].isin(FINISHES)
    lines["fights"] = 1
    lines["wins"] = won.astype(int)
    lines["losses"] = lost.astype(int)
    lines["finish_wins"] = (won & finished).astype(int)
    lines["finish_losses"] = (lost & finished).astype(int)

    totals = stats.groupby(["fight_id", "fighter_id"], as_index=False)[STAT_TOTALS].sum(min_count=1)
    lines = lines.merge(totals, on=["fight_id", "fighter_id"], how="left")

    # The opponent's row tells us what this fighter absorbed and defended.
    opponent = totals[["fight_id", "fighter_id", *OPPONENT_TOTALS]].rename(
        columns={"fighter_id": "opponent_id", **{c: f"opp_{c}" for c in OPPONENT_TOTALS}}
    )
    lines = lines.merge(opponent, on=["fight_id", "opponent_id"], how="left")

    # Only count time where the stat is known, so a missing stat doesn't look like a zero.
    lines["stat_s"] = lines["fight_time_s"].where(lines["sig_landed"].notna(), 0)
    lines["ctrl_known_s"] = lines["fight_time_s"].where(lines["ctrl_s"].notna(), 0)
    return lines


def build_career(lines: pd.DataFrame) -> pd.DataFrame:
    """Running totals per fighter, with one row for each night they fought."""
    lines = lines.assign(division=lines["weight_class"].where(lines["weight_class"].isin(STANDARD_DIVISIONS)))
    lines[CAREER_TOTALS] = lines[CAREER_TOTALS].astype("float64").fillna(0)

    nights = lines.groupby(["fighter_id", "date"], as_index=False)[CAREER_TOTALS].sum()
    divisions = lines.groupby(["fighter_id", "date"], as_index=False)["division"].last()
    career = nights.merge(divisions, on=["fighter_id", "date"]).sort_values(["fighter_id", "date"])

    # Any night without a win in every fight ends the streak, including draws and no contests.
    won_night = career["wins"] == career["fights"]
    streak_id = (~won_night).groupby(career["fighter_id"]).cumsum()
    career["win_streak"] = career["wins"].where(won_night, 0).groupby([career["fighter_id"], streak_id]).cumsum()

    by_fighter = career.groupby("fighter_id")
    career[CAREER_TOTALS] = by_fighter[CAREER_TOTALS].cumsum()
    career["division"] = by_fighter["division"].ffill()

    # Women's catch weight bouts aren't flagged, so any women's fight decides the category.
    women = lines.groupby("fighter_id")["womens"].max().rename("women")
    return career.merge(women, on="fighter_id").rename(columns={"date": "last_fight_date"})


def ratio(top: pd.Series, bottom: pd.Series) -> pd.Series:
    """top / bottom, left unknown when there is nothing to divide by."""
    return top / bottom.where(bottom > 0)


def profiles_as_of(requests: pd.DataFrame, career: pd.DataFrame, fighters: pd.DataFrame) -> pd.DataFrame:
    """Add a profile to each row of requests (fighter_id, date), from fights strictly before date."""
    requests = requests.assign(date=requests["date"].astype("datetime64[s]"))
    career = career.assign(last_fight_date=career["last_fight_date"].astype("datetime64[s]"))

    found = pd.merge_asof(
        requests.sort_values("date"),
        career.sort_values("last_fight_date"),
        left_on="date",
        right_on="last_fight_date",
        by="fighter_id",
        allow_exact_matches=False,
    ).merge(fighters[["fighter_id", "height_in", "reach_in", "dob"]], on="fighter_id", how="left")

    # A debut has zero fights (a known fact) but unknown rates.
    counts = ["fights", "wins", "losses", "win_streak"]
    found[counts] = found[counts].fillna(0)

    minutes = found["stat_s"] / 60
    per_15 = found["stat_s"] / 900

    profile = requests.columns.tolist()
    found = found.assign(
        fights_before=found["fights"],
        wins_before=found["wins"],
        losses_before=found["losses"],
        win_rate=ratio(found["wins"], found["wins"] + found["losses"]),
        finish_win_rate=ratio(found["finish_wins"], found["wins"]),
        finish_loss_rate=ratio(found["finish_losses"], found["losses"]),
        days_since_last=(found["date"] - found["last_fight_date"]).dt.days,
        age=(found["date"] - pd.to_datetime(found["dob"])).dt.days / 365.25,
        sig_landed_per_min=ratio(found["sig_landed"], minutes),
        sig_absorbed_per_min=ratio(found["opp_sig_landed"], minutes),
        sig_accuracy=ratio(found["sig_landed"], found["sig_attempted"]),
        sig_defense=1 - ratio(found["opp_sig_landed"], found["opp_sig_attempted"]),
        td_per_15=ratio(found["td_landed"], per_15),
        td_accuracy=ratio(found["td_landed"], found["td_attempted"]),
        td_defense=1 - ratio(found["opp_td_landed"], found["opp_td_attempted"]),
        kd_per_15=ratio(found["kd"], per_15),
        kd_absorbed_per_15=ratio(found["opp_kd"], per_15),
        sub_att_per_15=ratio(found["sub_att"], per_15),
        ctrl_per_15=ratio(found["ctrl_s"], found["ctrl_known_s"] / 900),
    )
    return found[profile + PROFILE_COLUMNS]


def build_profiles() -> None:
    tables = {
        name: pd.read_parquet(PROCESSED_DIR / f"{name}.parquet")
        for name in ("events", "fighters", "fights", "fight_stats")
    }
    lines = fighter_lines(tables["fights"], tables["events"], tables["fight_stats"])
    career = build_career(lines)
    requests = lines[["fight_id", "fighter_id", "opponent_id", "date"]]
    profiles = profiles_as_of(requests, career, tables["fighters"])

    for name, table in {"career": career, "pre_fight_profiles": profiles}.items():
        path = PROCESSED_DIR / f"{name}.parquet"
        table.to_parquet(path, index=False)
        print(f"{name}: {len(table):,} rows -> {path}")


if __name__ == "__main__":
    build_profiles()
