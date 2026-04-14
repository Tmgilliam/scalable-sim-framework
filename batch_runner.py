"""
Batch Runner
Executes every (scenario, seed) combination and logs results to a registry CSV.
"""
import copy
import csv
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

import yaml

from src.sim.inventory_types import SKUParams
from src.sim.sim_engine import simulate_inventory_weekly
from src.utils.run_utils import make_run_dir, run_id_from_dir, save_run_config, save_run_results

REGISTRY_PATH = "runs/registry.csv"
REGISTRY_FIELDS = [
    "run_id",
    "scenario",
    "seed",
    "timestamp_utc",
    "periods",
    "fill_rate",
    "backorder_units",
    "stockout_periods",
    "safety_stock_breaches",
    "demand_total",
    "demand_fulfilled",
    "run_dir",
    "gcs_path",
]


def _load_catalog(catalog_path: str) -> Dict:
    with open(catalog_path, encoding="utf-8") as f:
        return yaml.safe_load(f)["scenarios"]


def _build_cfg(scenario_cfg: Dict, seed: int) -> Dict:
    cfg = copy.deepcopy(scenario_cfg)
    cfg["run"] = {"seed": seed}
    return cfg


def _default_skus() -> List[SKUParams]:
    """
    Default SKU set. Replace or extend to load from a CSV/YAML for real runs.
    Three representative SKUs: high-volume, mid-volume, low-volume.
    """
    return [
        SKUParams(sku="SKU-A", weekly_demand=500, starting_on_hand=2000, safety_stock=500),
        SKUParams(sku="SKU-B", weekly_demand=200, starting_on_hand=800,  safety_stock=200),
        SKUParams(sku="SKU-C", weekly_demand=50,  starting_on_hand=300,  safety_stock=75),
    ]


def _registry_exists() -> bool:
    return os.path.exists(REGISTRY_PATH)


def _append_to_registry(row: Dict) -> None:
    os.makedirs(os.path.dirname(REGISTRY_PATH), exist_ok=True)
    write_header = not _registry_exists()
    with open(REGISTRY_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REGISTRY_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def run_batch(
    catalog_path: str = "scenarios/catalog.yaml",
    scenarios: Optional[List[str]] = None,
    seeds: Optional[List[int]] = None,
    skus: Optional[List[SKUParams]] = None,
    gcs_mirror_fn=None,          # injected by cloud layer; callable(run_dir) -> gcs_path or None
) -> List[Dict]:
    """
    Run all (scenario, seed) combinations.

    Args:
        catalog_path:   path to catalog YAML
        scenarios:      list of scenario names to run; None = all
        seeds:          list of integer seeds; default [42, 43, 44]
        skus:           list of SKUParams; default = _default_skus()
        gcs_mirror_fn:  optional callable that uploads run_dir and returns gcs_path string

    Returns:
        list of registry row dicts (also written to CSV)
    """
    catalog = _load_catalog(catalog_path)
    if scenarios is None:
        scenarios = list(catalog.keys())
    if seeds is None:
        seeds = [42, 43, 44]
    if skus is None:
        skus = _default_skus()

    rows = []
    total = len(scenarios) * len(seeds)
    done = 0

    for scenario_name in scenarios:
        if scenario_name not in catalog:
            print(f"[WARN] Scenario '{scenario_name}' not found in catalog, skipping.")
            continue

        for seed in seeds:
            cfg = _build_cfg(catalog[scenario_name], seed)
            run_dir = make_run_dir()
            run_id = run_id_from_dir(run_dir)

            save_run_config(run_dir, cfg)
            _, agg = simulate_inventory_weekly(cfg, skus)
            save_run_results(run_dir, agg)

            gcs_path = ""
            if gcs_mirror_fn is not None:
                try:
                    gcs_path = gcs_mirror_fn(run_dir) or ""
                except Exception as exc:
                    print(f"[WARN] GCS mirror failed for {run_id}: {exc}")

            row = {
                "run_id":                run_id,
                "scenario":              scenario_name,
                "seed":                  seed,
                "timestamp_utc":         datetime.now(timezone.utc).isoformat(),
                "periods":               agg["periods"],
                "fill_rate":             round(agg["fill_rate"], 4),
                "backorder_units":       round(agg["backorder_units"], 1),
                "stockout_periods":      agg["stockout_periods"],
                "safety_stock_breaches": agg["safety_stock_breaches"],
                "demand_total":          round(agg["demand_total"], 1),
                "demand_fulfilled":      round(agg["demand_fulfilled"], 1),
                "run_dir":               run_dir,
                "gcs_path":              gcs_path,
            }
            _append_to_registry(row)
            rows.append(row)

            done += 1
            fr = row["fill_rate"]
            bo = row["backorder_units"]
            print(f"[{done}/{total}] {scenario_name} seed={seed} | fill_rate={fr} backorders={bo}")

    print(f"\nBatch complete. {len(rows)} runs logged -> {REGISTRY_PATH}")
    return rows
