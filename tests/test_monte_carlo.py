"""Tests for the Pydantic-validated Monte Carlo engine."""

from __future__ import annotations

import pytest

from simulation import (
    MetricsSummary,
    MonteCarloEngine,
    ScenarioConfig,
    list_scenarios,
    run_scenario,
)
from simulation.scenarios import scenario_baseline


# ---- Config validation ----------------------------------------------------


def _base_kwargs() -> dict:
    return dict(
        initial_inventory=1000,
        demand_mean=100.0,
        demand_std=20.0,
        lead_time_mean=7.0,
        lead_time_std=2.0,
        reorder_point=500,
        reorder_qty=800,
        service_level_target=0.95,
        simulation_days=60,
        num_runs=10,
    )


def test_config_accepts_valid_inputs() -> None:
    cfg = ScenarioConfig(**_base_kwargs())
    assert cfg.simulation_days == 60
    assert cfg.num_runs == 10


def test_config_rejects_zero_reorder_point() -> None:
    kwargs = _base_kwargs()
    kwargs["reorder_point"] = 0
    with pytest.raises(Exception):
        ScenarioConfig(**kwargs)


def test_config_rejects_out_of_range_simulation_days() -> None:
    kwargs = _base_kwargs()
    kwargs["simulation_days"] = 10
    with pytest.raises(Exception):
        ScenarioConfig(**kwargs)

    kwargs["simulation_days"] = 1000
    with pytest.raises(Exception):
        ScenarioConfig(**kwargs)


def test_config_rejects_service_level_outside_unit_interval() -> None:
    for bad in (0.0, 1.0, -0.5, 1.5):
        kwargs = _base_kwargs()
        kwargs["service_level_target"] = bad
        with pytest.raises(Exception):
            ScenarioConfig(**kwargs)


def test_config_with_overrides_returns_new_instance() -> None:
    cfg = ScenarioConfig(**_base_kwargs())
    cfg2 = cfg.with_overrides(num_runs=50)
    assert cfg.num_runs == 10
    assert cfg2.num_runs == 50


# ---- Engine contract ------------------------------------------------------


def test_engine_returns_summary_with_all_metrics() -> None:
    cfg = ScenarioConfig(**_base_kwargs())
    summary = MonteCarloEngine(cfg).run()

    assert isinstance(summary, MetricsSummary)
    assert summary.num_runs == cfg.num_runs
    for name in MonteCarloEngine.METRIC_NAMES:
        assert name in summary.metrics
        for stat in ("mean", "std", "p10", "p50", "p90", "min", "max"):
            assert stat in summary.metrics[name]


def test_engine_fill_rate_is_a_probability() -> None:
    cfg = ScenarioConfig(**_base_kwargs())
    summary = MonteCarloEngine(cfg).run()
    fill = summary.metrics["fill_rate"]
    assert 0.0 <= fill["min"] <= fill["mean"] <= fill["max"] <= 1.0
    assert fill["p10"] <= fill["p50"] <= fill["p90"]


def test_engine_is_reproducible_with_fixed_seed() -> None:
    cfg = ScenarioConfig(**_base_kwargs())
    a = MonteCarloEngine(cfg).run()
    b = MonteCarloEngine(cfg).run()
    assert a.metrics["fill_rate"]["mean"] == b.metrics["fill_rate"]["mean"]
    assert a.metrics["stockout_days"]["p50"] == b.metrics["stockout_days"]["p50"]


def test_engine_captures_one_sample_trace() -> None:
    cfg = ScenarioConfig(**_base_kwargs())
    summary = MonteCarloEngine(cfg).run()
    assert summary.sample_trace is not None
    assert len(summary.sample_trace.day) == cfg.simulation_days


# ---- Scenario library -----------------------------------------------------


def test_baseline_scenario_runs_and_produces_narrative() -> None:
    result = scenario_baseline(num_runs=20, simulation_days=60)
    assert "baseline" in result.narrative
    assert "Monte Carlo" in result.narrative
    assert result.summary.num_runs == 20


def test_scenario_library_lists_all_five_scenarios() -> None:
    names = list_scenarios()
    expected = {
        "baseline",
        "demand_shock",
        "lead_time_crisis",
        "combined_stress",
        "service_level_sensitivity",
    }
    assert set(names) == expected


def test_run_scenario_unknown_name_raises() -> None:
    with pytest.raises(ValueError):
        run_scenario("does_not_exist")


def test_service_level_sensitivity_returns_sweep_results() -> None:
    result = run_scenario(
        "service_level_sensitivity",
        num_runs=10,
        simulation_days=60,
    )
    assert len(result.sweep_results) >= 3
    targets = [r.config.service_level_target for r in result.sweep_results]
    assert targets == sorted(targets)
