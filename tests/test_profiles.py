from datetime import date

import pandas as pd

from statcage.features.profiles import build_career, fighter_lines, profiles_as_of


def tiny_tables() -> dict[str, pd.DataFrame]:
    """Ana beats Bo by KO, beats Cy by decision, then loses to Bo by submission."""
    events = pd.DataFrame({
        "event_id": ["e1", "e2", "e3"],
        "date": [date(2020, 1, 1), date(2020, 6, 1), date(2021, 1, 1)],
    })
    fighters = pd.DataFrame({
        "fighter_id": ["ana", "bo", "cy"],
        "height_in": pd.array([66, 67, 68], dtype="Int64"),
        "reach_in": pd.array([68, None, 70], dtype="Int64"),
        "dob": [date(1990, 1, 1), None, date(1995, 1, 1)],
    })
    fights = pd.DataFrame({
        "fight_id": ["f1", "f2", "f3"],
        "event_id": ["e1", "e2", "e3"],
        "fighter_a_id": ["ana", "ana", "bo"],
        "fighter_b_id": ["bo", "cy", "ana"],
        "result": ["win", "win", "win"],
        "winner_id": ["ana", "ana", "bo"],
        "method": ["KO/TKO", "Decision", "Submission"],
        "weight_class": ["Flyweight", "Catch Weight", "Bantamweight"],
        "womens": [True, False, True],
        "fight_time_s": [300, 900, 600],
    })
    columns = ["fight_id", "fighter_id", "kd", "sig_landed", "sig_attempted",
               "td_landed", "td_attempted", "sub_att", "ctrl_s"]
    stats = pd.DataFrame([
        ("f1", "ana", 1, 10, 20, 1, 2, 0, None),
        ("f1", "bo", 0, 5, 20, 0, 4, 0, None),
        ("f2", "ana", 0, 30, 60, 3, 6, 1, 120),
        ("f2", "cy", 0, 15, 45, 0, 2, 0, 30),
        ("f3", "bo", 0, 8, 16, 2, 2, 1, 200),
        ("f3", "ana", 0, 4, 12, 0, 1, 0, 10),
    ], columns=columns)
    stats["ctrl_s"] = stats["ctrl_s"].astype("Int64")
    return {"events": events, "fighters": fighters, "fights": fights, "stats": stats}


def profile(tables: dict, fighter_id: str, day: str) -> pd.Series:
    lines = fighter_lines(tables["fights"], tables["events"], tables["stats"])
    career = build_career(lines)
    request = pd.DataFrame({"fighter_id": [fighter_id], "date": [pd.Timestamp(day)]})
    return profiles_as_of(request, career, tables["fighters"]).iloc[0]


def test_debut_has_zero_fights_and_unknown_rates():
    first = profile(tiny_tables(), "ana", "2020-01-01")
    assert first["fights_before"] == 0
    assert first["win_streak"] == 0
    assert pd.isna(first["sig_landed_per_min"])
    assert pd.isna(first["win_rate"])


def test_fight_on_the_same_date_is_not_included():
    before_second = profile(tiny_tables(), "ana", "2020-06-01")
    assert before_second["fights_before"] == 1
    assert before_second["sig_landed_per_min"] == 2.0


def test_any_later_date_includes_the_last_fight():
    today = profile(tiny_tables(), "ana", "2026-11-06")
    assert today["fights_before"] == 3
    assert today["wins_before"] == 2
    assert today["losses_before"] == 1
    assert today["win_streak"] == 0


def test_rates_use_career_totals():
    before_third = profile(tiny_tables(), "ana", "2021-01-01")
    assert before_third["sig_landed_per_min"] == 40 / 20
    assert before_third["sig_absorbed_per_min"] == 20 / 20
    assert before_third["td_per_15"] == 4 / (1200 / 900)
    assert before_third["win_streak"] == 2
    assert before_third["finish_win_rate"] == 0.5


def test_defense_comes_from_the_opponents_row():
    before_third = profile(tiny_tables(), "ana", "2021-01-01")
    assert before_third["sig_defense"] == 1 - 20 / 65
    assert before_third["td_defense"] == 1 - 0 / 6


def test_unknown_control_time_is_left_out_not_counted_as_zero():
    before_second = profile(tiny_tables(), "ana", "2020-06-01")
    assert pd.isna(before_second["ctrl_per_15"])
    before_third = profile(tiny_tables(), "ana", "2021-01-01")
    assert before_third["ctrl_per_15"] == 120 / (900 / 900)


def test_days_since_last_fight_and_age():
    before_second = profile(tiny_tables(), "ana", "2020-06-01")
    assert before_second["days_since_last"] == 152
    assert round(before_second["age"], 1) == 30.4
    assert pd.isna(profile(tiny_tables(), "bo", "2020-06-01")["age"])


def test_changing_a_future_fight_does_not_change_an_earlier_profile():
    tables = tiny_tables()
    honest = profile(tables, "ana", "2021-01-01")
    tables["stats"].loc[tables["stats"]["fight_id"] == "f3", "sig_landed"] = 999
    tables["fights"].loc[tables["fights"]["fight_id"] == "f3", "winner_id"] = "ana"
    pd.testing.assert_series_equal(honest, profile(tables, "ana", "2021-01-01"))


def test_fights_on_the_same_night_cannot_see_each_other():
    tables = tiny_tables()
    tables["events"].loc[1, "date"] = date(2020, 1, 1)
    second_fight = profile(tables, "ana", "2020-01-01")
    assert second_fight["fights_before"] == 0
    assert profile(tables, "ana", "2020-01-02")["fights_before"] == 2


def test_two_wins_on_one_night_both_count_in_the_streak():
    tables = tiny_tables()
    tables["events"].loc[1, "date"] = date(2020, 1, 1)
    assert profile(tables, "ana", "2020-01-02")["win_streak"] == 2


def test_a_loss_on_one_night_ends_the_streak():
    tables = tiny_tables()
    tables["events"].loc[2, "date"] = date(2020, 6, 1)
    assert profile(tables, "ana", "2020-06-02")["win_streak"] == 0


def test_division_skips_catch_weight():
    assert profile(tiny_tables(), "ana", "2021-01-01")["division"] == "Flyweight"
    assert pd.isna(profile(tiny_tables(), "cy", "2021-01-01")["division"])


def test_any_womens_fight_decides_the_category():
    assert bool(profile(tiny_tables(), "ana", "2020-01-02")["women"]) is True
    assert bool(profile(tiny_tables(), "cy", "2021-01-01")["women"]) is False
