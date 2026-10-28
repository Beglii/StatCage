"""Turn the text values in the ufcstats CSVs into numbers and dates.

Every function returns None for missing values ("", "--" or "---")
instead of guessing, so a missing reach stays missing.
"""

from datetime import date, datetime

MISSING = {"", "--", "---"}


def is_missing(value: str) -> bool:
    return value.strip() in MISSING


def parse_count(value: str) -> int | None:
    """Knockdowns, submission attempts, reversals: '1.0' -> 1."""
    if is_missing(value):
        return None
    return int(float(value))


def parse_landed_attempted(value: str) -> tuple[int | None, int | None]:
    """Strikes and takedowns: '9 of 37' -> (9, 37)."""
    if is_missing(value):
        return None, None
    landed, attempted = value.split(" of ")
    return int(landed), int(attempted)


def parse_clock(value: str) -> int | None:
    """Fight time and control time: '2:32' -> 152 seconds."""
    if is_missing(value):
        return None
    minutes, seconds = value.split(":")
    return int(minutes) * 60 + int(seconds)


def parse_height(value: str) -> int | None:
    """Height like 5' 11" -> 71 inches."""
    if is_missing(value):
        return None
    feet, inches = value.replace('"', "").split("' ")
    return int(feet) * 12 + int(inches)


def parse_reach(value: str) -> int | None:
    """Reach like 72" -> 72 inches."""
    if is_missing(value):
        return None
    return int(value.replace('"', ""))


def parse_weight(value: str) -> int | None:
    """Weight like '155 lbs.' -> 155."""
    if is_missing(value):
        return None
    return int(value.replace(" lbs.", ""))


def parse_date(value: str) -> date | None:
    """'October 17, 2026' or 'Jul 13, 1978' -> a date."""
    if is_missing(value):
        return None
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Unrecognized date: {value!r}")
