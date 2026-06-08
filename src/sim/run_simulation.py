# src/sim/run_simulation.py
# NOTE: No emoji in prints (Windows cp1252 consoles can crash on )

import argparse
import json
from pathlib import Path

from src.sim.data_loader import load_skus_csv
from src.sim.scenario import build_scenario_config
from src.sim.sim_engine import simulate_inventory_weekly
from src.utils.run_utils import make_scenario_run_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="Base")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--skus", default="configs/data/sample_skus.csv")
    args = parser.parse_args()

    catalog_path = Path("configs/scenarios/catalog.yaml")
    sc = build_scenario_config(
        catalog_path=catalog_path,
        scenario_name=args.scenario,
        seed=args.seed,
    )

    run_dir = make_scenario_run_dir(
        base_dir="runs",
        scenario_name=sc.scenario_name,
        cfg_hash=sc.config_hash,
    )

    outputs_dir = run_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=False)

    # Store exact config used (reproducibility)
    with open(run_dir / "config.json", "w", encoding="utf-8") as f:
        json.dump(sc.config, f, indent=2, sort_keys=True)

    # Load data + simulate
    skus = load_skus_csv(args.skus)
    per_sku, agg = simulate_inventory_weekly(sc.config, skus)

    # Write KPIs
    with open(outputs_dir / "kpis_aggregate.json", "w", encoding="utf-8") as f:
        json.dump(agg, f, indent=2, sort_keys=True)

    with open(outputs_dir / "kpis_per_sku.json", "w", encoding="utf-8") as f:
        json.dump([r.__dict__ | {"fill_rate": r.fill_rate()} for r in per_sku], f, indent=2)

    # Console-safe prints (no emoji)
    print(f"Simulation run created: {run_dir}")
    print(f"Scenario: {sc.scenario_name} | Seed: {sc.config['run']['seed']}")
    print(f"Aggregate fill rate: {agg['fill_rate']:.3f}")
    print(f"Backorder units: {agg['backorder_units']:.1f}")


if __name__ == "__main__":
    main()