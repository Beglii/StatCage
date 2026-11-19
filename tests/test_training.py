"""Tests for the training table (statcage.features.training).

They use three made-up fighters with easy numbers:
    vet1    10 fights, 5.0 strikes/min over 150 minutes
    vet2     8 fights, 3.0 strikes/min over 50 minutes
    rookie   debut: 0 fights, no minutes, blank rates
"""

import pandas as pd
import pytest

from statcage.features.training import FEATURES, SHRINK, league_priors, matchups, shrink


# ---------------------------------------------------------------------------
# Tiny test data
# ---------------------------------------------------------------------------

def tiny_profiles() -> pd.DataFrame:
    """Pre-fight profiles for two fights: f1 (2020, training era) and f2 (2023, later)."""
    rows = [
        # fight_id, fighter_id, date,        fights_before, sig_landed_per_min, stat_minutes
        ("f1", "vet1", "2020-01-01", 10, 5.0, 150.0),
        ("f1", "vet2", "2020-01-01", 8, 3.0, 50.0),
        ("f2", "rookie", "2023-01-01", 0, None, 0.0),
        ("f2", "vet1", "2023-01-01", 11, 10.0, 160.0),
    ]
    profiles = pd.DataFrame(rows, columns=["fight_id", "fighter_id", "date", "fights_before",
                                           "sig_landed_per_min", "stat_minutes"])
    profiles["date"] = pd.to_datetime(profiles["date"])

    # Every other rate, evidence and feature column gets one plain filler value,
    # so the tests only have to think about the columns set above.
    for rate, (evidence, _) in SHRINK.items():
        if rate not in profiles:
            profiles[rate] = 0.5
        if evidence not in profiles:
            profiles[evidence] = 10.0
    for feature in FEATURES:
        if feature not in profiles and feature != "debut":  # debut is computed by matchups()
            profiles[feature] = 1.0
    return profiles


def tiny_fights() -> pd.DataFrame:
    """vet1 beats vet2 (f1), vet1 beats the rookie (f2), and a draw (f3) to be dropped."""
    return pd.DataFrame({
        "fight_id": ["f1", "f2", "f3"],
        "fighter_a_id": ["vet1", "rookie", "vet1"],
        "fighter_b_id": ["vet2", "vet1", "vet2"],
        "result": ["win", "win", "draw"],
        "winner_id": ["vet1", "vet1", None],
    })


# ---------------------------------------------------------------------------
# Shrinkage
# ---------------------------------------------------------------------------

def test_priors_use_the_training_era_only_and_weigh_by_evidence():
    priors = league_priors(tiny_profiles(), before=pd.Timestamp("2022-01-01"))
    # f2 (2023) is ignored. Weighted average: (5.0 * 150 + 3.0 * 50) / 200 = 4.5
    assert priors["sig_landed_per_min"] == pytest.approx(4.5)


def test_shrinking_trusts_big_samples_and_ignores_empty_ones():
    profiles = tiny_profiles()
    shrunk = shrink(profiles, league_priors(profiles, before=pd.Timestamp("2022-01-01")))
    rate = shrunk.set_index(["fight_id", "fighter_id"])["sig_landed_per_min"]

    # vet1 in f1: trust = 150 / (150 + 15), so it moves most of the way from 4.5 to 5.0.
    assert rate["f1", "vet1"] == pytest.approx(4.5 + 150 / 165 * 0.5)
    # The rookie has 0 minutes -> trust 0 -> exactly the league prior.
    assert rate["f2", "rookie"] == pytest.approx(4.5)


# ---------------------------------------------------------------------------
# Matchups
# ---------------------------------------------------------------------------

def test_draws_and_no_contests_are_dropped():
    table = matchups(tiny_profiles(), tiny_fights())
    assert sorted(table["fight_id"]) == ["f1", "f2"]


def test_label_and_differences_follow_the_corners_after_swapping():
    # Try several seeds, so both "swapped" and "not swapped" get checked.
    for seed in range(5):
        table = matchups(tiny_profiles(), tiny_fights(), seed=seed).set_index("fight_id")
        for fight_id in ["f1", "f2"]:
            row = table.loc[fight_id]
            # vet1 won both fights, so a_won must be 1 exactly when vet1 is in slot A.
            assert row["a_won"] == int(row["a_id"] == "vet1")
            # vet1 always has more fights, so diff > 0 exactly when vet1 is A.
            assert (row["diff_fights_before"] > 0) == (row["a_id"] == "vet1")


def test_debut_flag_difference():
    table = matchups(tiny_profiles(), tiny_fights()).set_index("fight_id")
    row = table.loc["f2"]
    # Rookie (debut = 1) vs vet1 (debut = 0): +1 if the rookie is A, -1 if B.
    assert row["diff_debut"] == (1 if row["a_id"] == "rookie" else -1)


def test_the_swap_is_random_but_repeatable():
    # 1,000 fights where the listed A ("x") always wins.
    fights = pd.DataFrame({
        "fight_id": [f"f{i}" for i in range(1000)],
        "fighter_a_id": "x", "fighter_b_id": "y", "result": "win", "winner_id": "x",
    })
    profiles = pd.concat([
        tiny_profiles().iloc[[0, 1]].assign(fight_id=f"f{i}", fighter_id=["x", "y"]) for i in range(1000)
    ])
    first = matchups(profiles, fights)

    # Random: after swapping, A wins about half the time instead of 100%.
    assert 0.45 < first["a_won"].mean() < 0.55
    # Repeatable: the same seed gives the exact same table.
    pd.testing.assert_frame_equal(first, matchups(profiles, fights))
