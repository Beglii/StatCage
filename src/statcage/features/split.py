"""Split the training table by date into train / validation / test.

    train       1994 - 2021   the model learns from these fights
    validation  2022 - 2023   we compare settings (like C) on these fights
    test        2024 - now    touched once at the very end, for the honest final score

Why by date and not at random? StatCage always predicts fights that haven't happened
yet. A random split would let the model learn from 2025 and get tested on 2019, like
studying next week's answer key. Splitting by date copies real life: learn from the
past, get graded on the future.

All fights on one night land in the same part, because the split is on the date.
"""

import pandas as pd

from statcage.ingest.build import PROCESSED_DIR


# ---------------------------------------------------------------------------
# Boundaries
# ---------------------------------------------------------------------------

# Each part starts on this date (inclusive). Training is everything before VALIDATION_START.
VALIDATION_START = pd.Timestamp("2022-01-01")
TEST_START = pd.Timestamp("2024-01-01")

# Columns that describe the fight but are NOT model inputs.
ID_COLUMNS = ["fight_id", "date", "a_id", "b_id"]
LABEL = "a_won"


# ---------------------------------------------------------------------------
# Splitting
# ---------------------------------------------------------------------------

def split_by_date(table: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Return {"train": ..., "validation": ..., "test": ...}, cut by fight date.

    Example: a fight on 2021-12-31 is train, 2022-01-01 is validation,
    2023-12-31 is validation, 2024-01-01 is test.
    """
    date = table["date"]
    parts = {
        "train": table[date < VALIDATION_START],
        "validation": table[(date >= VALIDATION_START) & (date < TEST_START)],
        "test": table[date >= TEST_START],
    }

    # Safety check: every fight lands in exactly one part (none lost, none doubled).
    if sum(len(part) for part in parts.values()) != len(table):
        raise ValueError("split lost or duplicated fights")

    return {name: part.reset_index(drop=True) for name, part in parts.items()}


def features_and_label(part: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Separate the model inputs (X: every diff_ column) from the answer (y: a_won).

    Like a practice exam: X is the questions, y is the answer key. The model only
    ever sees X when predicting; y is used to train it and to grade it.
    """
    X = part[[column for column in part.columns if column.startswith("diff_")]]
    y = part[LABEL]
    return X, y


def load_split() -> dict[str, pd.DataFrame]:
    """Read training_table.parquet and split it. Used by step 2d (training)."""
    return split_by_date(pd.read_parquet(PROCESSED_DIR / "training_table.parquet"))


# ---------------------------------------------------------------------------
# Script entry point:  uv run python -m statcage.features.split
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Print a summary of each part. Nothing is saved: the split is cheap to redo.
    for name, part in load_split().items():
        print(
            f"{name:<10} {len(part):>5,} fights   "
            f"{part['date'].min().date()} to {part['date'].max().date()}   "
            f"a_won rate {part[LABEL].mean():.3f}"
        )
