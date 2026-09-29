import pytest

from app.settings_menu import (
    VOTE_TIME_MAX,
    VOTE_TIME_MIN,
    _format_vote_time,
    _parse_time_seconds,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("30", 30),
        ("600", 600),
        ("604800", 604800),
        ("10m30s", 630),
        ("2h", 7200),
        ("1d", 86400),
        ("1d12h", 129600),
        ("1h30m", 5400),
        ("90s", 90),
        ("  5m  ", 300),
    ],
)
def test_parse_time_seconds(value, expected):
    assert _parse_time_seconds(value) == expected


@pytest.mark.parametrize("value", ["", "abc", "10x", "m10", "1.5h", "-5m", "h"])
def test_parse_time_seconds_invalid(value):
    assert _parse_time_seconds(value) is None


def test_vote_time_bounds():
    assert VOTE_TIME_MIN == 30
    assert VOTE_TIME_MAX == 7 * 86400


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (30, "30 sec"),
        (60, "1 min"),
        (600, "10 min"),
        (5400, "1 h 30 min"),
        (86400, "1 d"),
        (129600, "1 d 12 h"),
    ],
)
def test_format_vote_time_en(seconds, expected):
    assert _format_vote_time("en_US", seconds) == expected
