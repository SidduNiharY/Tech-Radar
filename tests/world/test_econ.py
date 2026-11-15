from __future__ import annotations

import json

import pytest

from techradar.world.econ import (
    OFFICIAL_DOMAINS,
    change_sentence,
    extract_series_value,
    parse_econ_command,
    parse_worldbank,
)


class FakeFact:
    def __init__(
        self,
        statement: str,
        subject: str,
        value: str | None = None,
        domains: set[str] | None = None,
    ) -> None:
        self.statement = statement
        self.subject = subject
        self.value = value
        self.domains = domains or set()


def test_extract_repo_rate_from_official_fact() -> None:
    f = FakeFact(
        "Repo rate kept at 5.5%",
        "repo rate",
        "5.5%",
        domains={"rbi.org.in"},
    )
    assert extract_series_value(f, OFFICIAL_DOMAINS) == ("repo_rate", 5.5)


def test_ignores_non_official_fact() -> None:
    f = FakeFact(
        "Repo rate cut to 1%",
        "repo rate",
        "1%",
        domains={"fake-news.example"},
    )
    assert extract_series_value(f, OFFICIAL_DOMAINS) is None


@pytest.mark.parametrize(
    "label,unit,prev,cur,expected",
    [
        ("Repo rate", "%", 5.5, 5.5, "Repo rate stayed at 5.5%."),
        (
            "CPI inflation",
            "%",
            4.1,
            4.6,
            "CPI inflation rose from 4.1% to 4.6% (+0.5 points).",
        ),
        ("USD/INR", "", 84.2, 83.9, "USD/INR fell from 84.2 to 83.9 (−0.3)."),
        ("Gold (10 g)", "₹", None, 78450.0, "Gold (10 g) is ₹78,450."),
    ],
)
def test_change_sentence(
    label: str, unit: str, prev: float | None, cur: float, expected: str
) -> None:
    assert change_sentence(label, unit, prev, cur) == expected


def test_parse_worldbank_fixture() -> None:
    payload = [
        {"page": 1, "pages": 1, "per_page": 50, "total": 2},
        [
            {"indicator": {"id": "NY.GDP"}, "date": "2023", "value": 3.1},
            {"indicator": {"id": "NY.GDP"}, "date": "2022", "value": 3.0},
        ],
    ]
    raw_bytes = json.dumps(payload).encode("utf-8")
    parsed = parse_worldbank(raw_bytes)
    assert len(parsed) == 2
    assert parsed[0][1] == 3.1
    assert parsed[1][1] == 3.0


def test_parse_econ_command() -> None:
    res = parse_econ_command("usd_inr 2026-11 84.5")
    assert isinstance(res, tuple)
    assert res[0] == "usd_inr"
    assert res[2] == 84.5
