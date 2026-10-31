from datetime import date

import pytest

from statcage.ingest.parse import (
    fight_seconds,
    id_from_url,
    parse_clock,
    parse_count,
    parse_date,
    parse_height,
    parse_landed_attempted,
    parse_method,
    parse_outcome,
    parse_reach,
    parse_round_lengths,
    parse_scheduled_rounds,
    parse_weight,
    parse_weight_class,
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


def test_outcome():
    assert parse_outcome("W/L") == ("win", "a")
    assert parse_outcome("L/W") == ("win", "b")
    assert parse_outcome("NC/NC") == ("no_contest", None)


def test_outcome_unknown_fails_loudly():
    with pytest.raises(KeyError):
        parse_outcome("W/W")


def test_method():
    assert parse_method("Decision - Split", "Judge A 28 - 29.") == ("Decision", "Split")
    assert parse_method("TKO - Doctor's Stoppage", "Facial Cut") == ("KO/TKO", "Doctor's Stoppage")
    assert parse_method("Submission", "Rear Naked Choke") == ("Submission", "Rear Naked Choke")
    assert parse_method("KO/TKO", "") == ("KO/TKO", None)


def test_weight_class_light_heavyweight_is_not_heavyweight():
    assert parse_weight_class("Light Heavyweight Bout")["weight_class"] == "Light Heavyweight"
    assert parse_weight_class("Heavyweight Bout")["weight_class"] == "Heavyweight"


def test_weight_class_flags():
    info = parse_weight_class("UFC Interim Women's Flyweight Title Bout")
    assert info == {
        "weight_class": "Flyweight",
        "womens": True,
        "title_fight": True,
        "interim": True,
        "tournament": False,
    }


def test_tournament_final_is_not_a_title_fight():
    info = parse_weight_class("Ultimate Fighter 27 Lightweight Tournament Title Bout")
    assert info["title_fight"] is False
    assert info["tournament"] is True


def test_early_tournament_has_no_weight_class():
    assert parse_weight_class("UFC 2 Tournament Title Bout")["weight_class"] is None


def test_scheduled_rounds_and_lengths():
    assert parse_scheduled_rounds("5 Rnd (5-5-5-5-5)") == 5
    assert parse_scheduled_rounds("No Time Limit") is None
    assert parse_round_lengths("1 Rnd + OT (12-3)") == [12, 3]
    assert parse_round_lengths("No Time Limit") is None


def test_fight_seconds():
    assert fight_seconds(2, 152, [5, 5, 5]) == 452
    assert fight_seconds(1, 30, [5, 5, 5]) == 30
    assert fight_seconds(2, 60, [12, 3]) == 780
    assert fight_seconds(1, 1080, None) == 1080
