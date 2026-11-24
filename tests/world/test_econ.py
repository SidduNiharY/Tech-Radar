from __future__ import annotations

import json
from datetime import date

import pytest

from techradar.world.econ import (
    OFFICIAL_DOMAINS,
    FactRow,
    change_sentence,
    extract_series_value,
    load_official_domains,
    parse_econ_command,
    parse_worldbank,
)

OFFICIAL = set(OFFICIAL_DOMAINS)


def fact(
    statement: str, subject: str, value: str | None, domains: set[str], status: str = "verified"
) -> FactRow:
    return FactRow(
        statement=statement,
        subject=subject,
        value=value,
        status=status,
        domains=frozenset(domains),
        as_of=date(2026, 10, 1),
    )


def test_extract_repo_rate_from_official_fact() -> None:
    f = fact("Repo rate kept at 5.5%", "repo rate", "5.5%", {"rbi.org.in"})
    assert extract_series_value(f, OFFICIAL) == ("repo_rate", 5.5)


def test_ignores_non_official_fact() -> None:
    f = fact("Repo rate cut to 1%", "repo rate", "1%", {"fake-news.example"})
    assert extract_series_value(f, OFFICIAL) is None


def test_ignores_unverified_fact_even_from_an_official_domain() -> None:
    f = fact("Repo rate cut to 1%", "repo rate", "1%", {"rbi.org.in"}, status="unverified")
    assert extract_series_value(f, OFFICIAL) is None


def test_subject_must_match_and_the_number_comes_from_value_or_a_percentage() -> None:
    assert (
        extract_series_value(fact("Rice is 5.5%", "rice price", "5.5%", {"rbi.org.in"}), OFFICIAL)
        is None
    )
    from_statement = fact(
        "CPI inflation eased to 4.8% in October 2026", "CPI", None, {"mospi.gov.in"}
    )
    assert extract_series_value(from_statement, OFFICIAL) == ("cpi_inflation", 4.8)
    no_number = fact("GDP growth is strong", "GDP growth", None, {"pib.gov.in"})
    assert extract_series_value(no_number, OFFICIAL) is None
    negative = fact("GDP growth fell", "GDP growth", "-0.5%", {"pib.gov.in"})
    assert extract_series_value(negative, OFFICIAL) == ("gdp_growth", -0.5)


@pytest.mark.parametrize(
    "label,unit,prev,cur,expected",
    [
        ("Repo rate", "%", 5.5, 5.5, "Repo rate stayed at 5.5%."),
        ("CPI inflation", "%", 4.1, 4.6, "CPI inflation rose from 4.1% to 4.6% (+0.5 points)."),
        ("USD/INR", "", 84.2, 83.9, "USD/INR fell from 84.2 to 83.9 (−0.3)."),
        ("Gold (10 g)", "₹", None, 78450.0, "Gold (10 g) is ₹78,450."),
        ("Gold (10 g)", "₹", 78450.0, 79000.0, "Gold (10 g) rose from ₹78,450 to ₹79,000 (+550)."),
        ("Petrol (Delhi)", "₹/litre", None, 94.77, "Petrol (Delhi) is ₹94.77/litre."),
        ("Repo rate", "%", None, 5.5, "Repo rate is 5.5%."),
    ],
)
def test_change_sentence(
    label: str, unit: str, prev: float | None, cur: float, expected: str
) -> None:
    assert change_sentence(label, unit, prev, cur) == expected


def test_parse_worldbank_fixture() -> None:
    payload = [
        {"page": 1, "pages": 1, "per_page": 50, "total": 3},
        [
            {"indicator": {"id": "NY.GDP"}, "date": "2023", "value": 3.1},
            {"indicator": {"id": "NY.GDP"}, "date": "2022", "value": 3.0},
            {"indicator": {"id": "NY.GDP"}, "date": "2024", "value": None},
        ],
    ]
    assert parse_worldbank(json.dumps(payload).encode()) == [
        (date(2023, 1, 1), 3.1),
        (date(2022, 1, 1), 3.0),
    ]


@pytest.mark.parametrize(
    "raw",
    [
        b"not json",
        b"[]",
        b'{"a": 1}',
        b'[{"page": 1}, "oops"]',
        b'[{"page": 1}, [{"date": "twenty", "value": 1}]]',
        b'[{"page": 1}, [{"date": "2023", "value": "high"}]]',
        b'[{"page": 1}, [], 3]',
        b"\xff\xfe",
    ],
)
def test_parse_worldbank_malformed_gives_nothing(raw: bytes) -> None:
    assert parse_worldbank(raw) == []


def test_parse_econ_command() -> None:
    assert parse_econ_command("usd_inr 2026-11 84.5") == ("usd_inr", date(2026, 11, 1), 84.5)
    assert parse_econ_command("gold_10g 2026-11 78,450") == ("gold_10g", date(2026, 11, 1), 78450.0)


@pytest.mark.parametrize(
    "arg,starts",
    [
        ("", "Use: /econ"),
        ("usd_inr 2026-11", "Use: /econ"),
        ("repo_rate 2026-11 5.5", "Unknown series"),  # official series are not typed by hand
        ("wb_inflation_world 2026-11 3", "Unknown series"),
        ("usd_inr 2026-13 84", "Use: /econ"),
        ("usd_inr 202611 84", "Use the month"),
        ("usd_inr 2026-11 nan", "Give a number"),
        ("usd_inr 2026-11 -3", "Give a number"),
        ("usd_inr 2026-11 abc", "Use: /econ"),
    ],
)
def test_parse_econ_command_errors(arg: str, starts: str) -> None:
    assert parse_econ_command(arg).startswith(starts)  # type: ignore[union-attr]


def test_official_domains_file(tmp_path) -> None:
    f = tmp_path / "d.txt"
    f.write_text("# comment\nRBI.org.in\n.pib.gov.in\n\n")
    assert load_official_domains(f) == {"rbi.org.in", "pib.gov.in"}
    assert load_official_domains(tmp_path / "missing.txt") == OFFICIAL_DOMAINS
