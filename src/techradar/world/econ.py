"""Economy dashboard data (Phase 7 Task 7).

Series values come from three places, none of them a model: verified facts from an official
domain (repo rate, CPI inflation, GDP growth), values the owner types with `/econ`, and World
Bank rows. Everything lives in `econ_series`. This module is plain logic over already-parsed
numbers; the World Bank fetch and the API route wait for the internet stage.

WIRING(claude): the weekly World Bank fetch (`api.worldbank.org` in the squid allowlist), the
`json` parser kind (`parser/json_api.py`) that turns its answer into rows for `parse_worldbank`,
and `GET /v1/world/econ` are not built. `store_points` is where fetched rows go.

SEC: SEC-05, SEC-06, SEC-20.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import EconSeries, Fact, FactSource

# Used when infra/sources/official_domains.txt cannot be read.
OFFICIAL_DOMAINS: frozenset[str] = frozenset(
    {"rbi.org.in", "mospi.gov.in", "pib.gov.in", "finmin.nic.in"}
)
USAGE = "Use: /econ <series> <YYYY-MM> <value>"
MAX_POINTS = 24


class SeriesSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    unit: str
    kind: Literal["official_fact", "manual", "worldbank"]
    pattern: str | None = None
    wb_indicator: str | None = None
    wb_country: str | None = None


SERIES: dict[str, SeriesSpec] = {
    "repo_rate": SeriesSpec(
        label="Repo rate", unit="%", kind="official_fact", pattern=r"(?i)\brepo\s*rate\b"
    ),
    "cpi_inflation": SeriesSpec(
        label="CPI inflation",
        unit="%",
        kind="official_fact",
        pattern=r"(?i)\b(cpi|retail\s*inflation)\b",
    ),
    "gdp_growth": SeriesSpec(
        label="GDP growth", unit="%", kind="official_fact", pattern=r"(?i)\bgdp\s*growth\b"
    ),
    "usd_inr": SeriesSpec(label="USD/INR", unit="", kind="manual"),
    "gold_10g": SeriesSpec(label="Gold (10 g)", unit="₹", kind="manual"),
    "petrol_delhi": SeriesSpec(label="Petrol (Delhi)", unit="₹/litre", kind="manual"),
    "wb_gdp_growth_world": SeriesSpec(
        label="Global GDP growth",
        unit="%",
        kind="worldbank",
        wb_indicator="NY.GDP.MKTP.KD.ZG",
        wb_country="WLD",
    ),
    "wb_inflation_world": SeriesSpec(
        label="Global inflation",
        unit="%",
        kind="worldbank",
        wb_indicator="FP.CPI.TOTL.ZG",
        wb_country="WLD",
    ),
}

_VALUE = re.compile(r"^\s*([-+−]?\d+(?:\.\d+)?)\s*%?\s*$")
_PERCENT = re.compile(r"(?<![\w.])([-+−]?\d+(?:\.\d+)?)\s*%")


def load_official_domains(path: Path) -> frozenset[str]:
    """The official domains, one per line (`#` comments); the built-in set if unreadable."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return OFFICIAL_DOMAINS
    found = frozenset(
        line.strip().lstrip(".").lower() for line in lines if line.strip() and line[0] != "#"
    )
    return found or OFFICIAL_DOMAINS


class FactRow(BaseModel):
    """A fact as the dashboard sees it: the text, its status, and where it was supported."""

    model_config = ConfigDict(frozen=True)

    statement: str
    subject: str
    value: str | None = None
    status: str
    domains: frozenset[str] = frozenset()
    as_of: date | None = None


def extract_series_value(
    fact: FactRow, official_domains: Iterable[str]
) -> tuple[str, float] | None:
    """(series, value) from a verified fact supported by an official domain, else None.

    The fact's subject must match the series pattern; the number is read from its value, or
    from the statement when it has none (`5.5%`, `5.5`).
    """
    if fact.status != "verified" or not set(fact.domains) & set(official_domains):
        return None
    for key, spec in SERIES.items():
        if spec.kind != "official_fact" or not spec.pattern:
            continue
        if not re.search(spec.pattern, fact.subject):
            continue
        # the value field is the number itself; a statement must say it as a percentage
        for text, pattern in ((fact.value, _VALUE), (fact.statement, _PERCENT)):
            m = pattern.search(text) if text else None
            if m is not None:
                value = float(m.group(1).replace("−", "-"))
                if math.isfinite(value):
                    return key, value
    return None


class _WbRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: Annotated[str, Field(pattern=r"^[0-9]{4}$")]
    value: float | None = None


def parse_worldbank(data: bytes) -> list[tuple[date, float]]:
    """Rows of a World Bank indicator answer as (1 January of the year, value), newest first.

    Strict: the answer must be `[meta, [row, ...]]`; a row with no value is skipped; anything
    malformed gives an empty list.
    """
    try:
        parsed: Any = json.loads(data.decode("utf-8"))
        if not isinstance(parsed, list) or len(parsed) != 2 or not isinstance(parsed[1], list):
            return []
        rows = [_WbRow.model_validate(r) for r in parsed[1]]
    except ValueError, ValidationError, UnicodeDecodeError:
        return []
    out = [
        (date(int(r.date), 1, 1), r.value)
        for r in rows
        if r.value is not None and math.isfinite(r.value) and int(r.date) >= 1
    ]
    return sorted(out, key=lambda p: p[0], reverse=True)


def parse_econ_command(arg: str) -> tuple[str, date, float] | str:
    """`<series> <YYYY-MM> <value>` for a manual series, or the error text to send back."""
    parts = arg.split()
    if len(parts) != 3:
        return USAGE
    key, period_text, value_text = parts
    spec = SERIES.get(key)
    if spec is None or spec.kind != "manual":
        manual = ", ".join(k for k, s in SERIES.items() if s.kind == "manual")
        return f"Unknown series. You can enter: {manual}."
    if not re.fullmatch(r"\d{4}-\d{2}", period_text):
        return "Use the month as YYYY-MM."
    try:
        year, month = int(period_text[:4]), int(period_text[5:])
        period = date(year, month, 1)
        value = float(value_text.replace(",", ""))
    except ValueError:
        return USAGE
    if not math.isfinite(value) or value < 0:
        return "Give a number that is zero or more."
    return key, period, value


def _number(v: float) -> str:
    if float(v).is_integer():
        return f"{int(v):,}"
    return f"{round(v, 2):,.2f}".rstrip("0").rstrip(".")


def _with_unit(v: float, unit: str) -> str:
    if unit == "%":
        return f"{_number(v)}%"
    if unit.startswith("₹"):
        return f"₹{_number(v)}{unit[1:]}"
    return f"{_number(v)}{unit}"


def change_sentence(label: str, unit: str, prev: float | None, cur: float) -> str:
    """One plain sentence about the latest value against the one before it."""
    if prev is None:
        return f"{label} is {_with_unit(cur, unit)}."
    if prev == cur:
        return f"{label} stayed at {_with_unit(cur, unit)}."
    rose = cur > prev
    diff = _number(abs(cur - prev))
    sign = "+" if rose else "−"
    points = " points" if unit == "%" else ""
    verb = "rose" if rose else "fell"
    return (
        f"{label} {verb} from {_with_unit(prev, unit)} to {_with_unit(cur, unit)} "
        f"({sign}{diff}{points})."
    )


async def store_points(
    session: AsyncSession,
    series: str,
    points: Iterable[tuple[date, float]],
    *,
    source_kind: str,
    source_url: str | None = None,
) -> int:
    """Insert or update (series, period, source_kind) rows; the caller commits."""
    spec = SERIES[series]
    rows = [
        {
            "series": series,
            "period": period,
            "value": value,
            "unit": spec.unit,
            "source_kind": source_kind,
            "source_url": source_url,
        }
        for period, value in points
    ]
    if not rows:
        return 0
    stmt = insert(EconSeries).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_econ_series_period_source",
        set_={"value": stmt.excluded.value, "unit": stmt.excluded.unit},
    )
    await session.execute(stmt)
    return len(rows)


async def read_series(
    session: AsyncSession, series: str, limit: int = MAX_POINTS
) -> list[tuple[date, float]]:
    """Newest-first (period, value), one per period (a manual entry beats an official fact)."""
    stmt = (
        select(EconSeries.period, EconSeries.value, EconSeries.source_kind)
        .where(EconSeries.series == series)
        .order_by(EconSeries.period.desc(), EconSeries.source_kind)
    )
    seen: dict[date, float] = {}
    for period, value, kind in (await session.execute(stmt)).all():
        if period not in seen or kind == "manual":
            seen[period] = float(value)
    return sorted(seen.items(), reverse=True)[:limit]


async def collect_official(session: AsyncSession, official_domains: Iterable[str]) -> int:
    """Store every verified, current official fact that matches a series; returns rows stored."""
    official = frozenset(official_domains)
    facts = (
        await session.execute(
            select(Fact).where(
                Fact.status == "verified", Fact.superseded_by.is_(None), Fact.as_of.is_not(None)
            )
        )
    ).scalars()
    stored = 0
    for fact in list(facts):
        domains = frozenset(
            (
                await session.execute(
                    select(FactSource.domain).where(
                        FactSource.fact_id == fact.id, FactSource.supported.is_(True)
                    )
                )
            )
            .scalars()
            .all()
        )
        row = FactRow(
            statement=fact.statement,
            subject=fact.subject,
            value=fact.value,
            status=fact.status,
            domains=domains,
            as_of=fact.as_of,
        )
        hit = extract_series_value(row, official)
        if hit is None or fact.as_of is None:
            continue
        series, value = hit
        stored += await store_points(
            session,
            series,
            [(date(fact.as_of.year, fact.as_of.month, 1), value)],
            source_kind="official_fact",
        )
    return stored


async def record_manual(session: AsyncSession, series: str, period: date, value: float) -> None:
    """Store one value the owner typed with /econ; the caller commits."""
    await store_points(session, series, [(period, value)], source_kind="manual")


async def render_econ(session: AsyncSession) -> str:
    """The `/econ` reply: one sentence per series that has data, in series order."""
    lines: list[str] = []
    for key, spec in SERIES.items():
        points = await read_series(session, key, 2)
        if not points:
            continue
        cur = points[0][1]
        prev = points[1][1] if len(points) > 1 else None
        lines.append(change_sentence(spec.label, spec.unit, prev, cur))
    if not lines:
        return "No economy numbers yet. Add one: /econ usd_inr 2026-11 84.2"
    return "\n".join(lines)
