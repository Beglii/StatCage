"""Turn pre-fight profiles into the training table: one row per decided fight.

Pipeline:
    profiles  ->  shrink()    pull small-sample fluke rates toward the league average
              ->  matchups()  pair fighter A with fighter B, subtract (A - B), add the label a_won

Output (data/processed/training_table.parquet), one row per fight:
    fight_id, date, a_id, b_id, a_won, diff_debut, diff_fights_before, ..., diff_td_defense

Example row: if A has a 76" reach and B has 72", diff_reach_in = +4. If A won, a_won = 1.
"""

import numpy as np
import pandas as pd

from statcage.ingest.build import PROCESSED_DIR


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

# Fights before this date are the training era. Anything we "learn" from the data
# (like league averages) must come from this era only, or test fights leak in.
# The actual train / validation / test split happens in step 2c.
VALIDATION_START = pd.Timestamp("2022-01-01")

# Fixed random seed, so the corner swap is identical on every rebuild
# (same shuffle every time -> results can be repeated).
SEED = 7

# How to shrink each rate:   rate -> (evidence column, k)
#   evidence = how much data the rate is based on (the bottom of its fraction)
#   k        = how much evidence makes us trust the fighter's own number halfway
# Each k is about one typical fight's worth. A median UFC fight is ~13 minutes,
# ~65-80 significant strike attempts and only ~1-3 takedown attempts.
SHRINK = {
    # Record rates: evidence is counted in fights.
    "win_rate": ("decided_before", 3),
    "finish_win_rate": ("wins_before", 3),
    "finish_loss_rate": ("losses_before", 3),
    # Volume rates: evidence is minutes of fighting with stats recorded.
    "sig_landed_per_min": ("stat_minutes", 15),
    "sig_absorbed_per_min": ("stat_minutes", 15),
    "td_per_15": ("stat_minutes", 15),
    "kd_per_15": ("stat_minutes", 15),
    "kd_absorbed_per_15": ("stat_minutes", 15),
    "sub_att_per_15": ("stat_minutes", 15),
    "ctrl_per_15": ("ctrl_minutes", 15),
    # Accuracy and defense: evidence is attempts (theirs, or their opponents').
    "sig_accuracy": ("sig_attempted", 75),
    "sig_defense": ("opp_sig_attempted", 75),
    "td_accuracy": ("td_attempted", 5),
    "td_defense": ("opp_td_attempted", 5),
}

# Every feature that becomes an A - B column in the training table.
FEATURES = [
    "debut",            # 1 if this is their first UFC fight (the missing-value indicator)
    "fights_before",
    "win_streak",
    "days_since_last",  # blank for debuts; filled in step 2d
    "age",
    "height_in",
    "reach_in",
    *SHRINK,            # all the shrunk rates above
]


# ---------------------------------------------------------------------------
# Shrinkage
# ---------------------------------------------------------------------------

def league_priors(profiles: pd.DataFrame, before: pd.Timestamp = VALIDATION_START) -> dict[str, float]:
    """Return the typical ("prior") value of each rate, from training-era fights only.

    It's a weighted average: a fighter with 150 minutes counts 150x more than one with
    1 minute, like a GPA where 4-credit classes count more than 1-credit classes.

    Example: rates 5.0 (150 min) and 3.0 (50 min) -> (5.0*150 + 3.0*50) / 200 = 4.5
    """
    # Only fights before the validation date, so later fights can't shape the averages.
    training_era = profiles[profiles["date"] < before]

    priors = {}
    for rate, (evidence, _) in SHRINK.items():
        # Skip rows with no evidence (debuts): their rate is blank, not a real value.
        known = training_era[training_era[evidence] > 0]
        weighted_sum = (known[rate] * known[evidence]).sum()
        priors[rate] = float(weighted_sum / known[evidence].sum())
    return priors


def shrink(profiles: pd.DataFrame, priors: dict[str, float]) -> pd.DataFrame:
    """Pull each rate toward its prior. The less evidence, the stronger the pull.

        trust  = evidence / (evidence + k)            a dial from 0 (none) to 1 (full)
        shrunk = prior + trust * (rate - prior)       start at the prior, move toward the rate

    Examples for strikes per minute (prior 3.3, k = 15 minutes):
        56/min over 0.25 min -> trust 0.02 -> ~4.2  (a 15-second fluke, mostly ignored)
        5/min over 150 min   -> trust 0.91 -> ~4.85 (a proven veteran, mostly trusted)
        debut, 0 min         -> trust 0    -> 3.3   (blank becomes the prior)
    """
    shrunk = profiles.copy()
    for rate, (evidence, k) in SHRINK.items():
        trust = profiles[evidence] / (profiles[evidence] + k)

        # Debuts have a blank rate. Their trust is 0, so any filler works; using the
        # prior just keeps pandas from doing math on a blank.
        raw = profiles[rate].fillna(priors[rate])

        shrunk[rate] = priors[rate] + trust * (raw - priors[rate])
    return shrunk


# ---------------------------------------------------------------------------
# Training table
# ---------------------------------------------------------------------------

def matchups(profiles: pd.DataFrame, fights: pd.DataFrame, seed: int = SEED) -> pd.DataFrame:
    """Build one row per decided fight: A minus B for every feature, plus a_won.

    The listed A corner wins ~64% of the time (favorites get listed first), so A and B
    are swapped at random. Otherwise the model would just learn "always pick A".
    """
    # --- 1. Keep fights with a winner --------------------------------------
    # Draws and no contests have no yes/no answer to "did A win?", so they're dropped.
    # Sorting first gives a fixed order, so the seed always flips the same coin per fight.
    decided = fights[fights["result"] == "win"].sort_values("fight_id").reset_index(drop=True)

    # --- 2. Random corner swap -----------------------------------------------
    # One coin flip per fight: True = swap A and B.
    swap = np.random.default_rng(seed).random(len(decided)) < 0.5

    # np.where(swap, x, y) is Java's  swap ? x : y,  applied to every row at once.
    table = pd.DataFrame({
        "fight_id": decided["fight_id"],
        "a_id": np.where(swap, decided["fighter_b_id"], decided["fighter_a_id"]),
        "b_id": np.where(swap, decided["fighter_a_id"], decided["fighter_b_id"]),
    })

    # --- 3. Label ----------------------------------------------------------------
    # 1 if whoever ended up in the A slot won, else 0.
    table["a_won"] = (decided["winner_id"] == table["a_id"]).astype(int)

    # --- 4. Attach both fighters' profiles ---------------------------------------
    # Add the debut indicator, so the model can learn how first-timers tend to do.
    profiles = profiles.assign(debut=(profiles["fights_before"] == 0).astype(int))

    # Two renamed copies of the profiles (a_age, a_reach_in, ... and b_age, ...), each
    # joined on (fight, fighter). Like joining the same SQL table twice under two aliases.
    columns = ["fight_id", "fighter_id", "date", *FEATURES]
    a = profiles[columns].rename(columns={"fighter_id": "a_id", **{f: f"a_{f}" for f in FEATURES}})
    b = profiles[columns].drop(columns="date").rename(  # date is already on A's side
        columns={"fighter_id": "b_id", **{f: f"b_{f}" for f in FEATURES}}
    )
    table = table.merge(a, on=["fight_id", "a_id"]).merge(b, on=["fight_id", "b_id"])

    # --- 5. Differences: A minus B -----------------------------------------------
    # Positive = A has more of it. If the corners were swapped, every sign flips
    # and so does a_won, so both versions teach the same lesson.
    for feature in FEATURES:
        table[f"diff_{feature}"] = table[f"a_{feature}"] - table[f"b_{feature}"]

    # --- 6. Keep only what the model needs, oldest fights first ------------------
    diffs = [f"diff_{feature}" for feature in FEATURES]
    return table[["fight_id", "date", "a_id", "b_id", "a_won", *diffs]].sort_values(
        ["date", "fight_id"], ignore_index=True
    )


# ---------------------------------------------------------------------------
# Script entry point:  uv run python -m statcage.features.training
# ---------------------------------------------------------------------------

def build_training_table() -> None:
    """Load the profiles, shrink, build matchups, and save training_table.parquet."""
    profiles = pd.read_parquet(PROCESSED_DIR / "pre_fight_profiles.parquet")
    fights = pd.read_parquet(PROCESSED_DIR / "fights.parquet")

    priors = league_priors(profiles)
    table = matchups(shrink(profiles, priors), fights)

    path = PROCESSED_DIR / "training_table.parquet"
    table.to_parquet(path, index=False)

    # Quick sanity checks: about 8,792 rows, and a_won near 0.5 after the swap.
    print(f"training_table: {len(table):,} rows -> {path}")
    print(f"a_won rate: {table['a_won'].mean():.3f}")
    print("priors:", {name: round(value, 3) for name, value in priors.items()})


if __name__ == "__main__":
    build_training_table()
