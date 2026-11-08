"""Unit tests for Economy Dashboard indicators and summary card rendering."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from techradar.world.economy import EconomyDashboard, EconomyIndicators


def test_default_indicators() -> None:
    indicators = EconomyIndicators()
    assert indicators.repo_rate_pct == 6.5
    assert indicators.reverse_repo_rate_pct == 3.35
    assert indicators.cpi_inflation_pct == 5.1
    assert indicators.gdp_growth_pct == 7.2
    assert indicators.usd_inr_rate == 84.0
    assert isinstance(indicators.last_updated, datetime)
    assert (datetime.now(UTC) - indicators.last_updated).total_seconds() < 10


def test_dashboard_get_indicators_defaults() -> None:
    dashboard = EconomyDashboard()
    ind = dashboard.get_indicators()
    assert ind.repo_rate_pct == 6.5
    assert ind.reverse_repo_rate_pct == 3.35
    assert ind.cpi_inflation_pct == 5.1
    assert ind.gdp_growth_pct == 7.2
    assert ind.usd_inr_rate == 84.0


def test_dashboard_custom_initial_indicators() -> None:
    custom = EconomyIndicators(
        repo_rate_pct=7.0,
        reverse_repo_rate_pct=4.0,
        cpi_inflation_pct=4.5,
        gdp_growth_pct=8.0,
        usd_inr_rate=83.25,
    )
    dashboard = EconomyDashboard(custom)
    ind = dashboard.get_indicators()
    assert ind.repo_rate_pct == 7.0
    assert ind.reverse_repo_rate_pct == 4.0
    assert ind.cpi_inflation_pct == 4.5
    assert ind.gdp_growth_pct == 8.0
    assert ind.usd_inr_rate == 83.25


def test_update_indicator_exact_and_alias_names() -> None:
    dashboard = EconomyDashboard()

    # Exact field name
    updated = dashboard.update_indicator("repo_rate_pct", 6.25)
    assert updated.repo_rate_pct == 6.25
    assert dashboard.get_indicators().repo_rate_pct == 6.25

    # Known aliases
    dashboard.update_indicator("repo_rate", 6.0)
    assert dashboard.get_indicators().repo_rate_pct == 6.0

    dashboard.update_indicator("cpi", 4.8)
    assert dashboard.get_indicators().cpi_inflation_pct == 4.8

    dashboard.update_indicator("inflation", 4.9)
    assert dashboard.get_indicators().cpi_inflation_pct == 4.9

    dashboard.update_indicator("reverse_repo_rate", 3.5)
    assert dashboard.get_indicators().reverse_repo_rate_pct == 3.5

    dashboard.update_indicator("gdp", 7.5)
    assert dashboard.get_indicators().gdp_growth_pct == 7.5

    dashboard.update_indicator("usd_inr", 83.95)
    assert dashboard.get_indicators().usd_inr_rate == 83.95


def test_update_indicator_non_negative_validation() -> None:
    dashboard = EconomyDashboard()
    with pytest.raises(ValueError, match="must be non-negative"):
        dashboard.update_indicator("repo_rate_pct", -0.25)

    with pytest.raises(ValueError, match="must be non-negative"):
        dashboard.update_indicator("cpi_inflation_pct", -5.0)

    # Direct model validation also catches negative values
    with pytest.raises(ValidationError):
        EconomyIndicators(repo_rate_pct=-1.0)


def test_update_indicator_unknown_metric() -> None:
    dashboard = EconomyDashboard()
    with pytest.raises(ValueError, match="Unknown metric name 'unsupported_metric'"):
        dashboard.update_indicator("unsupported_metric", 10.0)


def test_render_summary_card() -> None:
    dashboard = EconomyDashboard()
    card = dashboard.render_summary_card()

    assert "### 📊 Economy Dashboard" in card
    assert "- **Repo Rate:** 6.50%" in card
    assert "- **Reverse Repo Rate:** 3.35%" in card
    assert "- **CPI Inflation:** 5.10%" in card
    assert "- **GDP Growth:** 7.20%" in card
    assert "- **USD/INR Rate:** ₹84.00" in card
    assert "- **Last Updated:**" in card

    # After update, card reflects updated metrics
    dashboard.update_indicator("repo_rate", 6.75)
    updated_card = dashboard.render_summary_card()
    assert "- **Repo Rate:** 6.75%" in updated_card
