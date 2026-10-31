"""Check the clean tables before they are saved.

Every rule here holds on the real data, so a failure means the source files
changed or a cleaning step broke. All problems are collected and reported together.
"""

from datetime import date

import pandas as pd

FIRST_UFC = date(1993, 11, 12)
OUTCOMES = {"win", "draw", "no_contest"}
STRIKE_PREFIXES = ["sig", "total", "td", "head", "body", "leg", "distance", "clinch", "ground"]


def flag(problems: list[str], bad: pd.Series, message: str) -> None:
    """Record a problem if any row is marked bad (unknown values count as fine)."""
    count = int(bad.fillna(False).sum())
    if count:
        problems.append(f"{message}: {count} rows")


def outside(values: pd.Series, low, high) -> pd.Series:
    """True where a known value is below low or above high (unknown values are skipped)."""
    known = values.dropna()
    bad = (known < low) | (known > high)
    return bad.reindex(values.index, fill_value=False)


def check_events(events: pd.DataFrame, today: date) -> list[str]:
    problems = []
    flag(problems, events["event_id"].isna(), "events: missing event_id")
    flag(problems, events["event_id"].duplicated(), "events: duplicate event_id")
    flag(problems, events["date"].isna(), "events: missing date")
    flag(problems, outside(events["date"], FIRST_UFC, today), "events: date before UFC 1 or in the future")
    return problems


def check_fighters(fighters: pd.DataFrame, today: date) -> list[str]:
    problems = []
    flag(problems, fighters["fighter_id"].isna(), "fighters: missing fighter_id")
    flag(problems, fighters["fighter_id"].duplicated(), "fighters: duplicate fighter_id")
    flag(problems, fighters["name"].isna() | (fighters["name"] == ""), "fighters: missing name")
    flag(problems, outside(fighters["height_in"], 48, 96), "fighters: height outside 4-8 ft")
    flag(problems, outside(fighters["reach_in"], 48, 96), "fighters: reach outside 48-96 in")
    flag(problems, outside(fighters["weight_lbs"], 100, 800), "fighters: weight outside 100-800 lbs")
    flag(problems, outside(fighters["dob"], date(1900, 1, 1), today), "fighters: impossible date of birth")
    return problems


def check_fights(fights: pd.DataFrame, events: pd.DataFrame, fighters: pd.DataFrame) -> list[str]:
    problems = []
    flag(problems, fights["fight_id"].duplicated(), "fights: duplicate fight_id")
    flag(problems, ~fights["event_id"].isin(events["event_id"]), "fights: event_id not in events")
    for side in ("fighter_a_id", "fighter_b_id"):
        flag(problems, ~fights[side].isin(fighters["fighter_id"]), f"fights: {side} not in fighters")
    flag(problems, fights["fighter_a_id"] == fights["fighter_b_id"], "fights: fighter fights himself")

    flag(problems, ~fights["result"].isin(OUTCOMES), "fights: unknown result")
    win = fights["result"] == "win"
    flag(problems, win & fights["winner_id"].isna(), "fights: win with no winner")
    flag(problems, ~win & fights["winner_id"].notna(), "fights: draw or no contest with a winner")
    in_bout = (fights["winner_id"] == fights["fighter_a_id"]) | (fights["winner_id"] == fights["fighter_b_id"])
    flag(problems, win & ~in_bout, "fights: winner did not fight in the bout")

    # scheduled_rounds counts regulation rounds only; early UFC fights could go to overtime.
    flag(problems, outside(fights["end_round"], 1, 5), "fights: end_round outside 1-5")
    flag(problems, fights["end_time_s"] <= 0, "fights: fight ended at 0:00 or earlier")
    flag(problems, fights["fight_time_s"] < fights["end_time_s"], "fights: total time shorter than last round")
    flag(problems, fights["fight_time_s"] > 40 * 60, "fights: longer than 40 minutes")
    return problems


def check_fight_stats(stats: pd.DataFrame, fights: pd.DataFrame) -> list[str]:
    problems = []
    flag(problems, stats.duplicated(["fight_id", "fighter_id", "round"]), "stats: duplicate fighter round")
    flag(problems, ~stats["fight_id"].isin(fights["fight_id"]), "stats: fight_id not in fights")

    # Bring in each fight's two fighters and last round to check every stat row against.
    joined = stats.merge(
        fights[["fight_id", "fighter_a_id", "fighter_b_id", "end_round"]], on="fight_id", how="left"
    )
    in_fight = (joined["fighter_id"] == joined["fighter_a_id"]) | (joined["fighter_id"] == joined["fighter_b_id"])
    flag(problems, ~in_fight, "stats: fighter did not fight in this fight")
    flag(problems, (joined["round"] < 1) | (joined["round"] > joined["end_round"]), "stats: round after the fight ended")

    for prefix in STRIKE_PREFIXES:
        landed, attempted = stats[f"{prefix}_landed"], stats[f"{prefix}_attempted"]
        flag(problems, landed < 0, f"stats: negative {prefix}_landed")
        flag(problems, landed > attempted, f"stats: {prefix} landed more than attempted")

    # Significant strikes are split two ways (by target, and by position); both must add up.
    for kind in ("landed", "attempted"):
        sig = stats[f"sig_{kind}"]
        by_target = stats[f"head_{kind}"] + stats[f"body_{kind}"] + stats[f"leg_{kind}"]
        by_position = stats[f"distance_{kind}"] + stats[f"clinch_{kind}"] + stats[f"ground_{kind}"]
        flag(problems, by_target != sig, f"stats: head + body + leg != sig_{kind}")
        flag(problems, by_position != sig, f"stats: distance + clinch + ground != sig_{kind}")
        flag(problems, sig > stats[f"total_{kind}"], f"stats: more significant than total strikes {kind}")

    for column in ("kd", "sub_att", "rev"):
        flag(problems, stats[column] < 0, f"stats: negative {column}")
    flag(problems, outside(stats["ctrl_s"], 0, 31 * 60), "stats: control time outside one round")
    return problems


def validate_all(
    events: pd.DataFrame,
    fighters: pd.DataFrame,
    fights: pd.DataFrame,
    stats: pd.DataFrame,
    today: date | None = None,
) -> None:
    """Raise one error listing every problem, or return quietly if the tables are clean."""
    today = today or date.today()
    problems = (
        check_events(events, today)
        + check_fighters(fighters, today)
        + check_fights(fights, events, fighters)
        + check_fight_stats(stats, fights)
    )
    if problems:
        raise ValueError("Validation failed:\n  " + "\n  ".join(problems))
