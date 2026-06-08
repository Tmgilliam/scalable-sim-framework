"""Scalable Simulation Framework — core Monte Carlo engine.

Public surface:
    ScenarioConfig    — Pydantic-validated scenario parameters
    MonteCarloEngine  — daily Monte Carlo loop with cross-run aggregation
    ScenarioResult    — config + metrics + narrative
    SCENARIO_LIBRARY  — pre-built scenarios (baseline, demand_shock, ...)
    run_scenario      — convenience entry point used by the CLI and dashboard
"""

from simulation.config import ScenarioConfig, DemandShock, LeadTimeShock
from simulation.engine import (
    MonteCarloEngine,
    MetricsSummary,
    RunMetrics,
    DailyTrace,
)


def __getattr__(name):
    # Lazy re-export of scenarios.* so `python -m simulation.scenarios` does
    # not trigger the "module found in sys.modules before execution" warning
    # caused by eager re-export at package import time.
    if name in {
        "ScenarioResult",
        "SCENARIO_LIBRARY",
        "run_scenario",
        "list_scenarios",
    }:
        from simulation import scenarios as _scenarios

        return getattr(_scenarios, name)
    raise AttributeError(name)


__all__ = [
    "ScenarioConfig",
    "DemandShock",
    "LeadTimeShock",
    "MonteCarloEngine",
    "MetricsSummary",
    "RunMetrics",
    "DailyTrace",
    "ScenarioResult",
    "SCENARIO_LIBRARY",
    "run_scenario",
    "list_scenarios",
]
