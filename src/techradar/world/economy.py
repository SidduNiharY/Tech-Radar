"""Economy Dashboard Indicators module.

Provides real-time economic indicators baseline, updates, and markdown summary cards.
"""

from datetime import UTC, datetime
from typing import Final

from pydantic import BaseModel, Field


class EconomyIndicators(BaseModel):
    """Core macroeconomic indicators snapshot."""

    repo_rate_pct: float = Field(default=6.5, ge=0.0, description="RBI Repo rate percentage")
    reverse_repo_rate_pct: float = Field(
        default=3.35, ge=0.0, description="RBI Reverse Repo rate percentage"
    )
    cpi_inflation_pct: float = Field(
        default=5.1, ge=0.0, description="Consumer Price Index inflation percentage"
    )
    gdp_growth_pct: float = Field(
        default=7.2, ge=0.0, description="Annual GDP growth rate percentage"
    )
    usd_inr_rate: float = Field(default=84.0, ge=0.0, description="USD to INR exchange rate")
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when indicators were last updated",
    )


METRIC_ALIASES: Final[dict[str, str]] = {
    "repo_rate": "repo_rate_pct",
    "repo_rate_pct": "repo_rate_pct",
    "reverse_repo_rate": "reverse_repo_rate_pct",
    "reverse_repo_rate_pct": "reverse_repo_rate_pct",
    "cpi_inflation": "cpi_inflation_pct",
    "cpi_inflation_pct": "cpi_inflation_pct",
    "cpi": "cpi_inflation_pct",
    "inflation": "cpi_inflation_pct",
    "gdp_growth": "gdp_growth_pct",
    "gdp_growth_pct": "gdp_growth_pct",
    "gdp": "gdp_growth_pct",
    "usd_inr": "usd_inr_rate",
    "usd_inr_rate": "usd_inr_rate",
}


class EconomyDashboard:
    """Manages economic indicators and summary generation."""

    def __init__(self, indicators: EconomyIndicators | None = None) -> None:
        self._indicators = indicators if indicators is not None else EconomyIndicators()

    def get_indicators(self) -> EconomyIndicators:
        """Return the current economic indicators snapshot."""
        return self._indicators

    def update_indicator(self, metric_name: str, value: float) -> EconomyIndicators:
        """Update a specific economic indicator with validation.

        Args:
            metric_name: Name of the indicator field (or recognized alias).
            value: New indicator value (must be >= 0).

        Returns:
            Updated EconomyIndicators instance.

        Raises:
            ValueError: If metric_name is unknown or value is negative.
        """
        canonical_name = METRIC_ALIASES.get(metric_name.strip().lower())
        if canonical_name is None:
            valid_names = ", ".join(sorted(METRIC_ALIASES.keys()))
            raise ValueError(f"Unknown metric name '{metric_name}'. Valid metrics: {valid_names}")

        if value < 0.0:
            raise ValueError(
                f"Indicator metric '{metric_name}' must be non-negative (>= 0), got {value}"
            )

        updated_values = {
            canonical_name: float(value),
            "last_updated": datetime.now(UTC),
        }
        self._indicators = self._indicators.model_copy(update=updated_values)
        return self._indicators

    def render_summary_card(self) -> str:
        """Format a clean markdown text summary card displaying economic metrics."""
        ind = self._indicators
        timestamp_str = ind.last_updated.strftime("%Y-%m-%d %H:%M:%S UTC")
        return (
            "### 📊 Economy Dashboard\n\n"
            f"- **Repo Rate:** {ind.repo_rate_pct:.2f}%\n"
            f"- **Reverse Repo Rate:** {ind.reverse_repo_rate_pct:.2f}%\n"
            f"- **CPI Inflation:** {ind.cpi_inflation_pct:.2f}%\n"
            f"- **GDP Growth:** {ind.gdp_growth_pct:.2f}%\n"
            f"- **USD/INR Rate:** ₹{ind.usd_inr_rate:.2f}\n"
            f"- **Last Updated:** {timestamp_str}\n"
        )
