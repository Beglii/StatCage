from datetime import date

import pandas as pd
import pytest

from statcage.ingest.validate import validate_all

TODAY = date(2026, 10, 31)


def tiny_tables() -> dict[str, pd.DataFrame]:
    """One event, two fighters, one fight that ended in round 1, and its two stat rows."""
    events = pd.DataFrame({"event_id": ["e1"], "date": [date(2026, 10, 17)]})
    fighters = pd.DataFrame({
        "fighter_id": ["f1", "f2"],
        "name": ["Joaquin Buckley", "Mike Malott"],
        "height_in": pd.array([70, None], dtype="Int64"),
        "weight_lbs": pd.array([170, 170], dtype="Int64"),
        "reach_in": pd.array([76, None], dtype="Int64"),
        "dob": [date(1994, 4, 27), None],
    })
    fights = pd.DataFrame({
        "fight_id": ["x1"],
        "event_id": ["e1"],
        "fighter_a_id": ["f1"],
        "fighter_b_id": ["f2"],
        "result": ["win"],
        "winner_id": ["f1"],
        "end_round": [1],
        "end_time_s": [152],
        "fight_time_s": [152],
    })
    stat = {
        "kd": 0, "sub_att": 0, "rev": 0,
        "sig_landed": 9, "sig_attempted": 37,
        "total_landed": 9, "total_attempted": 37,
        "td_landed": 0, "td_attempted": 0,
        "head_landed": 5, "head_attempted": 33,
        "body_landed": 1, "body_attempted": 1,
        "leg_landed": 3, "leg_attempted": 3,
        "distance_landed": 9, "distance_attempted": 37,
        "clinch_landed": 0, "clinch_attempted": 0,
        "ground_landed": 0, "ground_attempted": 0,
    }
    stats = pd.DataFrame([
        {"fight_id": "x1", "fighter_id": "f1", "round": 1, **stat},
        {"fight_id": "x1", "fighter_id": "f2", "round": 1, **stat},
    ])
    stats["ctrl_s"] = pd.array([0, None], dtype="Int64")
    return {"events": events, "fighters": fighters, "fights": fights, "stats": stats}


def validate(tables: dict[str, pd.DataFrame]) -> None:
    validate_all(**tables, today=TODAY)


def test_clean_tables_pass():
    validate(tiny_tables())


def test_winner_must_be_in_the_bout():
    tables = tiny_tables()
    tables["fights"].loc[0, "winner_id"] = "someone_else"
    with pytest.raises(ValueError, match="winner did not fight in the bout"):
        validate(tables)


def test_draw_cannot_have_a_winner():
    tables = tiny_tables()
    tables["fights"].loc[0, "result"] = "draw"
    with pytest.raises(ValueError, match="draw or no contest with a winner"):
        validate(tables)


def test_fight_must_point_to_a_real_event():
    tables = tiny_tables()
    tables["fights"].loc[0, "event_id"] = "missing"
    with pytest.raises(ValueError, match="event_id not in events"):
        validate(tables)


def test_landed_cannot_exceed_attempted():
    tables = tiny_tables()
    tables["stats"].loc[0, "td_landed"] = 3
    with pytest.raises(ValueError, match="td landed more than attempted"):
        validate(tables)


def test_strike_splits_must_add_up():
    tables = tiny_tables()
    tables["stats"].loc[0, "head_landed"] = 6
    with pytest.raises(ValueError, match=r"head \+ body \+ leg != sig_landed"):
        validate(tables)


def test_no_stats_after_the_fight_ended():
    tables = tiny_tables()
    tables["stats"].loc[1, "round"] = 2
    with pytest.raises(ValueError, match="round after the fight ended"):
        validate(tables)


def test_future_event_fails():
    tables = tiny_tables()
    tables["events"].loc[0, "date"] = date(2027, 1, 1)
    with pytest.raises(ValueError, match="in the future"):
        validate(tables)


def test_all_problems_reported_together():
    tables = tiny_tables()
    tables["fights"].loc[0, "winner_id"] = "someone_else"
    tables["stats"].loc[0, "td_landed"] = 3
    with pytest.raises(ValueError) as error:
        validate(tables)
    assert "winner did not fight" in str(error.value)
    assert "td landed more than attempted" in str(error.value)
