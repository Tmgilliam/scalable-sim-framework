"""Pydantic-validated scenario configuration for the Monte Carlo engine.

Why Pydantic instead of a plain dataclass:
    * Operations leadership runs these scenarios through a UI. We need
      input validation to fail loud and early, not three minutes into
      a 1,000-run Monte Carlo loop.
    * The config is the contract that the Vertex AI pipeline component
      consumes. A typed schema lets the pipeline reject malformed
      payloads at the orchestration layer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel, Field, model_validator


class DemandShock(BaseModel):
    """Demand-side stress injection.

    `multiplier` scales mean demand during the shock window. A value
    of 2.0 doubles demand; 0.5 halves it.
    """

    start_day: int = Field(..., ge=1, description="1-based start day (inclusive).")
    duration_days: int = Field(..., ge=1, description="Length of the shock window in days.")
    multiplier: float = Field(..., gt=0.0, description="Multiplier applied to demand_mean during the window.")


class LeadTimeShock(BaseModel):
    """Lead-time stress injection.

    `multiplier` scales mean lead time during the shock window. A
    value of 2.0 means supplier lead times double for the duration.
    """

    start_day: int = Field(..., ge=1)
    duration_days: int = Field(..., ge=1)
    multiplier: float = Field(..., gt=0.0)


class ScenarioConfig(BaseModel):
    """Scenario configuration for the Monte Carlo engine.

    All inventory / demand / lead-time parameters are in *daily* units.
    `num_runs` controls Monte Carlo replication width.
    """

    name: str = Field(default="custom", description="Human-readable scenario name.")
    description: str = Field(default="", description="Plain-English description of what this scenario tests.")

    initial_inventory: int = Field(..., ge=0, description="Starting on-hand inventory units.")
    demand_mean: float = Field(..., gt=0.0, description="Mean daily demand (units/day).")
    demand_std: float = Field(..., ge=0.0, description="Standard deviation of daily demand.")
    lead_time_mean: float = Field(..., gt=0.0, description="Mean supplier lead time in days.")
    lead_time_std: float = Field(..., ge=0.0, description="Standard deviation of lead time in days.")

    reorder_point: int = Field(..., gt=0, description="Inventory position threshold that triggers a reorder.")
    reorder_qty: int = Field(..., gt=0, description="Order quantity placed when threshold is crossed.")

    service_level_target: float = Field(
        ...,
        gt=0.0,
        lt=1.0,
        description="Target fill rate (fraction of demand met from stock).",
    )

    simulation_days: int = Field(..., ge=30, le=730, description="Length of each Monte Carlo run, in days.")
    num_runs: int = Field(..., ge=1, le=10_000, description="Number of Monte Carlo replications.")

    seed: int = Field(default=42, description="Master RNG seed. Per-run seeds derive from this.")

    demand_shock: Optional[DemandShock] = None
    lead_time_shock: Optional[LeadTimeShock] = None

    @model_validator(mode="after")
    def _validate_shock_windows(self) -> "ScenarioConfig":
        """Shock windows must fit inside the simulation horizon."""
        for label, shock in (("demand_shock", self.demand_shock), ("lead_time_shock", self.lead_time_shock)):
            if shock is None:
                continue
            end = shock.start_day + shock.duration_days - 1
            if end > self.simulation_days:
                raise ValueError(
                    f"{label} runs day {shock.start_day}..{end}, but simulation_days={self.simulation_days}."
                )
        return self

    @model_validator(mode="after")
    def _validate_reorder_logic(self) -> "ScenarioConfig":
        """A reorder that doesn't cover lead-time demand is a misconfigured policy."""
        expected_lt_demand = self.demand_mean * self.lead_time_mean
        if self.reorder_qty < expected_lt_demand * 0.25:
            raise ValueError(
                f"reorder_qty={self.reorder_qty} is implausibly small relative to expected "
                f"lead-time demand ({expected_lt_demand:.1f}). Operations would never run this."
            )
        return self

    # ---- Loaders ----------------------------------------------------------

    @classmethod
    def from_file(cls, path: str | Path) -> "ScenarioConfig":
        """Load a scenario config from JSON or YAML based on file extension."""
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        if p.suffix.lower() in {".yaml", ".yml"}:
            data = yaml.safe_load(text)
        elif p.suffix.lower() == ".json":
            data = json.loads(text)
        else:
            raise ValueError(f"Unsupported config extension: {p.suffix}. Use .json, .yaml, or .yml.")
        if not isinstance(data, dict):
            raise ValueError(f"Config file {p} must contain a mapping at the top level.")
        return cls(**data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScenarioConfig":
        return cls(**data)

    # ---- Inheritance ------------------------------------------------------

    def with_overrides(self, **overrides: Any) -> "ScenarioConfig":
        """Return a new config derived from this one with the given overrides applied.

        Supports nested shock blocks via dict-shaped overrides, e.g.:
            base.with_overrides(demand_shock={"start_day": 30, "duration_days": 14, "multiplier": 2.0})
        """
        base = self.model_dump()
        for key, value in overrides.items():
            base[key] = value
        return ScenarioConfig(**base)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")
