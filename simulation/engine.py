"""Monte Carlo inventory simulation engine.

Daily-resolution stochastic simulation:
    * Demand:   N(demand_mean, demand_std), floored at 0.
    * Lead time: N(lead_time_mean, lead_time_std), floored at 1 day.
    * Reorder:   when inventory_position <= reorder_point, place an
                 order for reorder_qty with a sampled lead time.
    * Shocks:    demand and lead-time multipliers active during their
                 configured windows.

Per run we record stockout_days, fill_rate, avg_inventory,
service_level_achieved, and total_orders_placed. Across runs we
aggregate mean, std, and the p10/p50/p90 percentiles.

The first run's full day-by-day trace is preserved for dashboard
visualization. Keeping a trace for every run is unnecessary and
expensive; one is enough to drive the operator-facing chart.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

import numpy as np

from simulation.config import ScenarioConfig


@dataclass
class DailyTrace:
    """Day-by-day state for a single Monte Carlo run.

    Used by the dashboard's stress-test visualization panel.
    """

    day: List[int] = field(default_factory=list)
    on_hand: List[float] = field(default_factory=list)
    on_order: List[float] = field(default_factory=list)
    demand: List[float] = field(default_factory=list)
    fulfilled: List[float] = field(default_factory=list)
    stockout_flag: List[int] = field(default_factory=list)
    reorder_events: List[int] = field(default_factory=list)


@dataclass
class RunMetrics:
    """Metrics captured from a single Monte Carlo run."""

    stockout_days: int
    fill_rate: float
    avg_inventory: float
    service_level_achieved: float
    total_orders_placed: int


@dataclass
class MetricsSummary:
    """Aggregated metrics across all Monte Carlo runs.

    For every metric we capture mean, std, and p10/p50/p90. p10 is the
    pessimistic-tail view ("10% of futures look at least this bad");
    p90 is the optimistic-tail view.
    """

    num_runs: int
    metrics: Dict[str, Dict[str, float]]
    sample_trace: Optional[DailyTrace] = None

    def to_dict(self) -> Dict:
        return {
            "num_runs": self.num_runs,
            "metrics": self.metrics,
            "sample_trace": asdict(self.sample_trace) if self.sample_trace else None,
        }


class MonteCarloEngine:
    """Daily Monte Carlo simulation of a single-product inventory policy.

    The engine is deliberately scoped to one product. Multi-SKU
    aggregation is handled by running independent engines in parallel
    (see vertex/pipeline.py).
    """

    METRIC_NAMES = (
        "stockout_days",
        "fill_rate",
        "avg_inventory",
        "service_level_achieved",
        "total_orders_placed",
    )

    def __init__(self, config: ScenarioConfig) -> None:
        self.config = config

    # ---- Public API -------------------------------------------------------

    def run(self) -> MetricsSummary:
        """Execute all Monte Carlo runs and return the aggregated summary."""
        cfg = self.config
        master_rng = np.random.default_rng(cfg.seed)

        per_run: List[RunMetrics] = []
        sample_trace: Optional[DailyTrace] = None

        for run_idx in range(cfg.num_runs):
            run_seed = int(master_rng.integers(0, 2**31 - 1))
            rng = np.random.default_rng(run_seed)
            metrics, trace = self._simulate_one_run(rng, capture_trace=(run_idx == 0))
            per_run.append(metrics)
            if run_idx == 0:
                sample_trace = trace

        return MetricsSummary(
            num_runs=cfg.num_runs,
            metrics=self._aggregate(per_run),
            sample_trace=sample_trace,
        )

    # ---- Single run -------------------------------------------------------

    def _simulate_one_run(
        self,
        rng: np.random.Generator,
        capture_trace: bool,
    ) -> tuple[RunMetrics, Optional[DailyTrace]]:
        cfg = self.config
        on_hand: float = float(cfg.initial_inventory)
        on_order: List[Dict] = []  # list of {"qty": int, "arrival_day": int}

        total_demand = 0.0
        total_fulfilled = 0.0
        stockout_days = 0
        on_hand_sum = 0.0
        orders_placed = 0

        trace = DailyTrace() if capture_trace else None

        for day in range(1, cfg.simulation_days + 1):
            arrived = [o for o in on_order if o["arrival_day"] == day]
            if arrived:
                on_hand += sum(o["qty"] for o in arrived)
                on_order = [o for o in on_order if o["arrival_day"] != day]

            demand = self._sample_demand(rng, day)
            fulfilled = min(on_hand, demand)
            on_hand -= fulfilled
            total_demand += demand
            total_fulfilled += fulfilled
            if fulfilled < demand:
                stockout_days += 1

            reorder_event = 0
            inventory_position = on_hand + sum(o["qty"] for o in on_order)
            if inventory_position <= cfg.reorder_point:
                lead_time_days = self._sample_lead_time(rng, day)
                arrival = min(cfg.simulation_days, day + lead_time_days)
                on_order.append({"qty": cfg.reorder_qty, "arrival_day": arrival})
                orders_placed += 1
                reorder_event = 1

            on_hand_sum += on_hand

            if trace is not None:
                trace.day.append(day)
                trace.on_hand.append(on_hand)
                trace.on_order.append(float(sum(o["qty"] for o in on_order)))
                trace.demand.append(demand)
                trace.fulfilled.append(fulfilled)
                trace.stockout_flag.append(1 if fulfilled < demand else 0)
                trace.reorder_events.append(reorder_event)

        fill_rate = (total_fulfilled / total_demand) if total_demand > 0 else 1.0
        avg_inventory = on_hand_sum / cfg.simulation_days
        service_level_achieved = 1.0 - (stockout_days / cfg.simulation_days)

        metrics = RunMetrics(
            stockout_days=stockout_days,
            fill_rate=fill_rate,
            avg_inventory=avg_inventory,
            service_level_achieved=service_level_achieved,
            total_orders_placed=orders_placed,
        )
        return metrics, trace

    # ---- Stochastic samplers ---------------------------------------------

    def _sample_demand(self, rng: np.random.Generator, day: int) -> float:
        cfg = self.config
        mean = cfg.demand_mean
        if cfg.demand_shock is not None:
            s = cfg.demand_shock
            if s.start_day <= day < s.start_day + s.duration_days:
                mean = mean * s.multiplier
        raw = rng.normal(mean, cfg.demand_std)
        return max(0.0, raw)

    def _sample_lead_time(self, rng: np.random.Generator, day: int) -> int:
        cfg = self.config
        mean = cfg.lead_time_mean
        if cfg.lead_time_shock is not None:
            s = cfg.lead_time_shock
            if s.start_day <= day < s.start_day + s.duration_days:
                mean = mean * s.multiplier
        raw = rng.normal(mean, cfg.lead_time_std)
        return max(1, int(round(raw)))

    # ---- Cross-run aggregation -------------------------------------------

    def _aggregate(self, per_run: List[RunMetrics]) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        for name in self.METRIC_NAMES:
            values = np.array([getattr(r, name) for r in per_run], dtype=float)
            out[name] = {
                "mean": float(np.mean(values)),
                "std": float(np.std(values, ddof=0)),
                "p10": float(np.percentile(values, 10)),
                "p50": float(np.percentile(values, 50)),
                "p90": float(np.percentile(values, 90)),
                "min": float(np.min(values)),
                "max": float(np.max(values)),
            }
        return out
