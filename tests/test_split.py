"""Tests for the date split (statcage.features.split)."""

import pandas as pd

from statcage.features.split import features_and_label, split_by_date


def tiny_table() -> pd.DataFrame:
    """Five fights placed right on and around the two boundary dates."""
    dates = ["2021-12-31", "2022-01-01", "2023-12-31", "2024-01-01", "2026-11-01"]
    return pd.DataFrame({
        "fight_id": [f"f{i}" for i in range(5)],
        "date": pd.to_datetime(dates),
        "a_id": "x",
        "b_id": "y",
        "a_won": [1, 0, 1, 0, 1],
        "diff_age": [1.0, 2.0, 3.0, 4.0, 5.0],
        "diff_reach_in": [0.0, -1.0, 2.0, -3.0, 4.0],
    })


def test_boundary_dates_land_in_the_right_part():
    parts = split_by_date(tiny_table())
    assert parts["train"]["fight_id"].tolist() == ["f0"]              # 2021-12-31
    assert parts["validation"]["fight_id"].tolist() == ["f1", "f2"]   # 2022-01-01, 2023-12-31
    assert parts["test"]["fight_id"].tolist() == ["f3", "f4"]         # 2024-01-01 onward


def test_every_fight_is_in_exactly_one_part():
    parts = split_by_date(tiny_table())
    all_ids = pd.concat(part["fight_id"] for part in parts.values())
    assert sorted(all_ids) == sorted(tiny_table()["fight_id"])  # none lost, none doubled


def test_parts_are_in_time_order():
    # Every train fight is older than every validation fight, which is older than every test fight.
    parts = split_by_date(tiny_table())
    assert parts["train"]["date"].max() < parts["validation"]["date"].min()
    assert parts["validation"]["date"].max() < parts["test"]["date"].min()


def test_features_are_only_diff_columns_and_label_is_a_won():
    X, y = features_and_label(tiny_table())
    # No IDs, dates or the answer may sneak into the model inputs.
    assert X.columns.tolist() == ["diff_age", "diff_reach_in"]
    assert y.tolist() == [1, 0, 1, 0, 1]
