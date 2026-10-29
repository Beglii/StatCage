from datetime import date

import pytest

from statcage.ingest.parse import (
    id_from_url,
    parse_clock,
    parse_count,
    parse_date,
    parse_height,
    parse_landed_attempted,
    parse_reach,
    parse_weight,
    text_or_none,
)


def test_id_from_url():
    assert id_from_url("http://ufcstats.com/event-details/55e94a9b525dcf45") == "55e94a9b525dcf45"


def test_text_or_none():
    assert text_or_none(" Orthodox ") == "Orthodox"
    assert text_or_none("") is None


def test_landed_attempted():
    assert parse_landed_attempted("9 of 37") == (9, 37)
    assert parse_landed_attempted("0 of 0") == (0, 0)
    assert parse_landed_attempted("") == (None, None)


def test_count():
    assert parse_count("1.0") == 1
    assert parse_count("0") == 0
    assert parse_count("") is None


def test_clock():
    assert parse_clock("2:32") == 152
    assert parse_clock("0:08") == 8
    assert parse_clock("--") is None


def test_height():
    assert parse_height("5' 11\"") == 71
    assert parse_height("6' 0\"") == 72
    assert parse_height("--") is None


def test_reach_and_weight():
    assert parse_reach("72\"") == 72
    assert parse_reach("--") is None
    assert parse_weight("155 lbs.") == 155
    assert parse_weight("--") is None


def test_date_both_formats():
    assert parse_date("October 17, 2026") == date(2026, 10, 17)
    assert parse_date("Jul 13, 1978") == date(1978, 7, 13)
    assert parse_date("--") is None


def test_date_unknown_format_fails_loudly():
    with pytest.raises(ValueError):
        parse_date("2026-10-17")
