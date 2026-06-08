"""Regression guard — fixed-seed Base scenario KPI ranges."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Ranges from reproducible Base seed=42 runs (update if catalog defaults change intentionally).
EXPECTED_AGGREGATE_RANGES = {
    "fill_rate": (0.85, 1.0),
    "backorder_units": (0.0, 500.0),
    "demand_total": (1000.0, 50000.0),
}


def _latest_base_run() -> Path:
    runs = sorted((ROOT / "runs").glob("*_Base_*"), key=lambda p: p.stat().st_mtime)
    assert runs, "No Base run found — run smoke_test or python -m src.sim.run_simulation first"
    return runs[-1]


def test_fixed_seed_aggregate_ranges() -> None:
    run_dir = _latest_base_run()
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    assert config.get("run", {}).get("seed") == 42, "Expected seed=42 Base run for regression guard"

    agg = json.loads((run_dir / "outputs" / "kpis_aggregate.json").read_text(encoding="utf-8"))
    for key, (lo, hi) in EXPECTED_AGGREGATE_RANGES.items():
        val = float(agg[key])
        assert lo <= val <= hi, f"{key}={val} outside [{lo}, {hi}]"
