"""Pre-built scenario library + narrative interpretation.

Each scenario returns a `ScenarioResult` containing the exact config
that ran, the cross-run metrics summary, and a plain-English narrative
written for an operations director (not a data scientist).

The narrative is the most important part of this module: it converts
raw Monte Carlo output into the language operations leadership uses to
make decisions ("9 times out of 10 you would expect X stockout days").
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List

from simulation.config import ScenarioConfig, DemandShock, LeadTimeShock
from simulation.engine import MetricsSummary, MonteCarloEngine


# ---------------------------------------------------------------------------
# Result object
# ---------------------------------------------------------------------------


@dataclass
class ScenarioResult:
    """The full output of one scenario run."""

    scenario_name: str
    config: ScenarioConfig
    summary: MetricsSummary
    narrative: str = ""
    sweep_results: List["ScenarioResult"] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "scenario_name": self.scenario_name,
            "config": self.config.to_dict(),
            "summary": self.summary.to_dict(),
            "narrative": self.narrative,
            "sweep_results": [r.to_dict() for r in self.sweep_results],
        }


# ---------------------------------------------------------------------------
# Narrative generator
# ---------------------------------------------------------------------------


def _interpret(name: str, cfg: ScenarioConfig, summary: MetricsSummary) -> str:
    """Convert metrics into operations-director language."""
    m = summary.metrics
    stockout_p50 = m["stockout_days"]["p50"]
    stockout_p90 = m["stockout_days"]["p90"]
    fill_p50 = m["fill_rate"]["p50"]
    fill_p10 = m["fill_rate"]["p10"]
    avg_inv_p50 = m["avg_inventory"]["p50"]
    target = cfg.service_level_target
    service_p50 = m["service_level_achieved"]["p50"]

    target_status = (
        f"meets the {target:.0%} service-level target"
        if service_p50 >= target
        else f"falls short of the {target:.0%} service-level target (median {service_p50:.1%})"
    )

    return (
        f"Scenario '{name}' ({cfg.num_runs} Monte Carlo runs over {cfg.simulation_days} days):\n"
        f"  - Median fill rate is {fill_p50:.1%}; 10% of futures fall below {fill_p10:.1%}.\n"
        f"  - You would expect about {stockout_p50:.0f} stockout days half the time, "
        f"and as many as {stockout_p90:.0f} in the worst 10% of outcomes.\n"
        f"  - The policy holds a median average inventory of {avg_inv_p50:.0f} units.\n"
        f"  - Under these assumptions the policy {target_status}."
    )


# ---------------------------------------------------------------------------
# Base config and scenarios
# ---------------------------------------------------------------------------


def _baseline_config() -> ScenarioConfig:
    """Calibrated to steady-state normal operations.

    These numbers reflect a mid-volume SKU with ~100 units/day demand,
    a 7-day lead time, and a reorder policy roughly tuned to a 95%
    service level. They are intentionally realistic, not synthetic.
    """
    return ScenarioConfig(
        name="baseline",
        description="Steady-state normal operations. No shocks.",
        initial_inventory=1500,
        demand_mean=100.0,
        demand_std=20.0,
        lead_time_mean=7.0,
        lead_time_std=2.0,
        reorder_point=900,
        reorder_qty=1000,
        service_level_target=0.95,
        simulation_days=180,
        num_runs=200,
        seed=42,
    )


def scenario_baseline(num_runs: int = 200, simulation_days: int = 180) -> ScenarioResult:
    cfg = _baseline_config().with_overrides(num_runs=num_runs, simulation_days=simulation_days)
    summary = MonteCarloEngine(cfg).run()
    return ScenarioResult(
        scenario_name="baseline",
        config=cfg,
        summary=summary,
        narrative=_interpret("baseline", cfg, summary),
    )


def scenario_demand_shock(
    multiplier: float = 2.0,
    duration_days: int = 30,
    start_day: int = 60,
    num_runs: int = 200,
    simulation_days: int = 180,
) -> ScenarioResult:
    """2x demand spike for a configurable duration.

    Models a launch event, viral demand, or supply-chain panic buying.
    """
    cfg = _baseline_config().with_overrides(
        name="demand_shock",
        description=f"{multiplier:.1f}x demand spike for {duration_days} days starting on day {start_day}.",
        num_runs=num_runs,
        simulation_days=simulation_days,
        demand_shock=DemandShock(
            start_day=start_day,
            duration_days=duration_days,
            multiplier=multiplier,
        ).model_dump(),
    )
    summary = MonteCarloEngine(cfg).run()
    return ScenarioResult(
        scenario_name="demand_shock",
        config=cfg,
        summary=summary,
        narrative=_interpret("demand_shock", cfg, summary),
    )


def scenario_lead_time_crisis(
    multiplier: float = 2.0,
    duration_days: int = 45,
    start_day: int = 45,
    num_runs: int = 200,
    simulation_days: int = 180,
) -> ScenarioResult:
    """Lead time doubles for a configurable period.

    Models a port closure, a sole-source supplier disruption, or a
    geopolitical event upstream.
    """
    cfg = _baseline_config().with_overrides(
        name="lead_time_crisis",
        description=f"Lead time {multiplier:.1f}x for {duration_days} days starting on day {start_day}.",
        num_runs=num_runs,
        simulation_days=simulation_days,
        lead_time_shock=LeadTimeShock(
            start_day=start_day,
            duration_days=duration_days,
            multiplier=multiplier,
        ).model_dump(),
    )
    summary = MonteCarloEngine(cfg).run()
    return ScenarioResult(
        scenario_name="lead_time_crisis",
        config=cfg,
        summary=summary,
        narrative=_interpret("lead_time_crisis", cfg, summary),
    )


def scenario_combined_stress(
    demand_multiplier: float = 1.8,
    lead_time_multiplier: float = 1.8,
    duration_days: int = 30,
    start_day: int = 60,
    num_runs: int = 200,
    simulation_days: int = 180,
) -> ScenarioResult:
    """Demand shock + lead-time increase concurrently.

    The compound case operations leadership actually worries about.
    """
    cfg = _baseline_config().with_overrides(
        name="combined_stress",
        description=(
            f"Demand {demand_multiplier:.1f}x AND lead time {lead_time_multiplier:.1f}x "
            f"for {duration_days} days starting on day {start_day}."
        ),
        num_runs=num_runs,
        simulation_days=simulation_days,
        demand_shock=DemandShock(
            start_day=start_day,
            duration_days=duration_days,
            multiplier=demand_multiplier,
        ).model_dump(),
        lead_time_shock=LeadTimeShock(
            start_day=start_day,
            duration_days=duration_days,
            multiplier=lead_time_multiplier,
        ).model_dump(),
    )
    summary = MonteCarloEngine(cfg).run()
    return ScenarioResult(
        scenario_name="combined_stress",
        config=cfg,
        summary=summary,
        narrative=_interpret("combined_stress", cfg, summary),
    )


def scenario_service_level_sensitivity(
    targets: List[float] | None = None,
    num_runs: int = 100,
    simulation_days: int = 180,
) -> ScenarioResult:
    """Sweep service-level target from 0.85 → 0.99 and quantify the tradeoff.

    Each higher target requires more inventory to achieve. This is the
    cost/service tradeoff in numbers operations leadership can defend
    to finance.

    The returned `ScenarioResult.sweep_results` holds the individual
    sub-results so the dashboard and CLI can render the full curve.
    """
    if targets is None:
        targets = [0.85, 0.90, 0.95, 0.97, 0.99]

    base = _baseline_config()
    sub_results: List[ScenarioResult] = []
    for target in targets:
        scaled_reorder_point = int(round(base.reorder_point * (0.85 + (target - 0.85) * 1.5)))
        cfg = base.with_overrides(
            name=f"service_level_{int(target * 100):02d}",
            description=f"Service-level target {target:.0%}.",
            num_runs=num_runs,
            simulation_days=simulation_days,
            service_level_target=target,
            reorder_point=max(1, scaled_reorder_point),
        )
        summary = MonteCarloEngine(cfg).run()
        sub_results.append(
            ScenarioResult(
                scenario_name=cfg.name,
                config=cfg,
                summary=summary,
                narrative=_interpret(cfg.name, cfg, summary),
            )
        )

    narrative_lines = [
        "Scenario 'service_level_sensitivity' -- cost vs. service tradeoff:",
    ]
    for sub in sub_results:
        m = sub.summary.metrics
        narrative_lines.append(
            f"  - Target {sub.config.service_level_target:.0%}: "
            f"median fill rate {m['fill_rate']['p50']:.1%}, "
            f"median avg inventory {m['avg_inventory']['p50']:.0f} units."
        )

    parent_cfg = sub_results[0].config
    return ScenarioResult(
        scenario_name="service_level_sensitivity",
        config=parent_cfg,
        summary=sub_results[-1].summary,
        narrative="\n".join(narrative_lines),
        sweep_results=sub_results,
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


SCENARIO_LIBRARY: Dict[str, Callable[..., ScenarioResult]] = {
    "baseline": scenario_baseline,
    "demand_shock": scenario_demand_shock,
    "lead_time_crisis": scenario_lead_time_crisis,
    "combined_stress": scenario_combined_stress,
    "service_level_sensitivity": scenario_service_level_sensitivity,
}


def list_scenarios() -> List[str]:
    """Return the names of available pre-built scenarios."""
    return list(SCENARIO_LIBRARY.keys())


def run_scenario(name: str, **overrides) -> ScenarioResult:
    """Run a pre-built scenario by name. Extra kwargs are forwarded.

    Raises ValueError for unknown scenario names.
    """
    if name not in SCENARIO_LIBRARY:
        raise ValueError(
            f"Unknown scenario '{name}'. Available: {sorted(SCENARIO_LIBRARY.keys())}"
        )
    return SCENARIO_LIBRARY[name](**overrides)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Run a pre-built Monte Carlo scenario.")
    parser.add_argument(
        "--scenario",
        default="baseline",
        choices=list(SCENARIO_LIBRARY.keys()),
        help="Pre-built scenario to execute.",
    )
    parser.add_argument("--num-runs", type=int, default=200, help="Number of Monte Carlo replications.")
    parser.add_argument("--simulation-days", type=int, default=180, help="Length of each run, in days.")
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Optional path to write the JSON-serialized ScenarioResult.",
    )
    args = parser.parse_args()

    if args.scenario == "service_level_sensitivity":
        result = run_scenario(args.scenario, num_runs=args.num_runs, simulation_days=args.simulation_days)
    else:
        result = run_scenario(
            args.scenario,
            num_runs=args.num_runs,
            simulation_days=args.simulation_days,
        )

    print(result.narrative)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        print(f"\nWrote ScenarioResult to {out_path}")


if __name__ == "__main__":
    _cli()
