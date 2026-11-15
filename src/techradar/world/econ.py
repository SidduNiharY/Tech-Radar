from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

OFFICIAL_DOMAINS: set[str] = {
    "rbi.org.in",
    "mospi.gov.in",
    "pib.gov.in",
    "finmin.nic.in",
}


class SeriesSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    unit: str
    kind: Literal["official_fact", "manual", "worldbank"]
    pattern: str | None = None
    wb_indicator: str | None = None


SERIES: dict[str, SeriesSpec] = {
    "repo_rate": SeriesSpec(
        label="Repo rate",
        unit="%",
        kind="official_fact",
        pattern=r"(?i)\brepo\s*rate\b",
    ),
    "cpi_inflation": SeriesSpec(
        label="CPI inflation",
        unit="%",
        kind="official_fact",
        pattern=r"(?i)\b(cpi|retail\s*inflation)\b",
    ),
    "gdp_growth": SeriesSpec(
        label="GDP growth",
        unit="%",
        kind="official_fact",
        pattern=r"(?i)\bgdp\s*growth\b",
    ),
    "usd_inr": SeriesSpec(
        label="USD/INR",
        unit="",
        kind="manual",
    ),
    "gold_10g": SeriesSpec(
        label="Gold (10 g)",
        unit="₹",
        kind="manual",
    ),
    "petrol_delhi": SeriesSpec(
        label="Petrol (Delhi)",
        unit="₹/litre",
        kind="manual",
    ),
    "wb_gdp_growth_world": SeriesSpec(
        label="Global GDP growth",
        unit="%",
        kind="worldbank",
        wb_indicator="NY.GDP.MKTP.KD.ZG",
    ),
    "wb_inflation_world": SeriesSpec(
        label="Global inflation",
        unit="%",
        kind="worldbank",
        wb_indicator="FP.CPI.TOTL.ZG",
    ),
}

_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)")


def extract_series_value(fact: Any, official_domains: set[str]) -> tuple[str, float] | None:
    """Extract official macroeconomic series metric and numeric value from a verified fact."""
    domains = getattr(fact, "domains", set())
    if not any(d in official_domains for d in domains):
        return None

    subject = getattr(fact, "subject", "")
    statement = getattr(fact, "statement", "")
    raw_val = getattr(fact, "value", None) or statement

    for series_key, spec in SERIES.items():
        if spec.kind != "official_fact" or not spec.pattern:
            continue
        if re.search(spec.pattern, subject) or re.search(spec.pattern, statement):
            m = _NUM_RE.search(raw_val)
            if m:
                try:
                    return series_key, float(m.group(1))
                except ValueError:
                    continue
    return None


def parse_worldbank(data: bytes) -> list[tuple[date, float]]:
    """Parse JSON timeseries observations from World Bank API response."""
    try:
        parsed = json.loads(data.decode("utf-8"))
        if not isinstance(parsed, list) or len(parsed) < 2:
            return []
        records = parsed[1]
        if not isinstance(records, list):
            return []

        out: list[tuple[date, float]] = []
        for r in records:
            if not isinstance(r, dict):
                continue
            val = r.get("value")
            d_str = r.get("date")
            if val is None or d_str is None:
                continue
            # Usually year string '2023'
            year = int(d_str)
            period = date(year, 1, 1)
            out.append((period, float(val)))
        return out
    except Exception:
        return []


def parse_econ_command(arg: str) -> tuple[str, date, float] | str:
    """Parse '/econ <series> <YYYY-MM> <value>' for manual series update."""
    parts = arg.strip().split()
    if len(parts) != 3:
        return "Use: /econ <series> <YYYY-MM> <value>"

    series_key, period_str, val_str = parts[0], parts[1], parts[2]
    spec = SERIES.get(series_key)
    if spec is None or spec.kind != "manual":
        return f"Unknown or non-manual series '{series_key}'."

    try:
        dt = datetime.strptime(period_str, "%Y-%m")
        period = date(dt.year, dt.month, 1)
    except ValueError:
        return "Invalid period format. Use YYYY-MM."

    try:
        val = float(val_str)
    except ValueError:
        return "Invalid numeric value."

    return series_key, period, val


def change_sentence(label: str, unit: str, prev: float | None, cur: float) -> str:
    """Render human-readable change description for macroeconomic observation."""
    if prev is None:
        if unit == "₹":
            formatted = f"{int(cur):,}" if cur.is_integer() else f"{cur:,.2f}"
            return f"{label} is ₹{formatted}."
        if unit:
            return f"{label} is {cur}{unit}."
        return f"{label} is {cur}."

    if prev == cur:
        return f"{label} stayed at {cur}{unit}."

    if cur > prev:
        diff = cur - prev
        diff_str = f"+{diff:.1f} points" if unit == "%" else f"+{diff:.1f}"
        return f"{label} rose from {prev}{unit} to {cur}{unit} ({diff_str})."

    # cur < prev
    diff = prev - cur
    diff_str = f"−{diff:.1f} points" if unit == "%" else f"−{diff:.1f}"
    return f"{label} fell from {prev}{unit} to {cur}{unit} ({diff_str})."
