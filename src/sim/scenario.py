from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from src.utils.config import ScenarioConfig, deep_merge, load_yaml, stable_hash


def build_scenario_config(
    catalog_path: str | Path,
    scenario_name: str,
    seed: int,
) -> ScenarioConfig:
    catalog = load_yaml(catalog_path)

    defaults: Dict[str, Any] = catalog["defaults"]
    scenarios: Dict[str, Any] = catalog["scenarios"]

    if scenario_name not in scenarios:
        raise ValueError(f"Unknown scenario '{scenario_name}'. Available: {list(scenarios.keys())}")

    overrides = scenarios[scenario_name].get("overrides", {})
    final_cfg = deep_merge(defaults, overrides)

    # enforce reproducibility basics
    final_cfg["run"] = {
        "scenario": scenario_name,
        "seed": int(seed),
    }

    cfg_hash = stable_hash(final_cfg)
    return ScenarioConfig(scenario_name=scenario_name, config=final_cfg, config_hash=cfg_hash)