"""Quick simulation validation — minimal run, output structure, sensible ranges."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_smoke_simulation_run() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "src.sim.run_simulation", "--scenario", "Base", "--seed", "42"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout

    runs = sorted((ROOT / "runs").glob("*_Base_*"), key=lambda p: p.stat().st_mtime)
    assert runs, "Expected a Base scenario run directory"
    run_dir = runs[-1]
    agg_path = run_dir / "outputs" / "kpis_aggregate.json"
    assert agg_path.is_file(), f"Missing aggregate KPIs: {agg_path}"

    agg = json.loads(agg_path.read_text(encoding="utf-8"))
    assert "fill_rate" in agg and "backorder_units" in agg
    assert 0.0 <= float(agg["fill_rate"]) <= 1.0
    assert float(agg["backorder_units"]) >= 0.0

    per_sku_path = run_dir / "outputs" / "kpis_per_sku.json"
    per_sku = json.loads(per_sku_path.read_text(encoding="utf-8"))
    assert isinstance(per_sku, list) and len(per_sku) > 0
