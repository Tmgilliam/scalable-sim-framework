import json
import os
import uuid
from datetime import datetime, timezone
from typing import Dict


def make_run_dir(base: str = "runs") -> str:
    """Create a timestamped run directory and return its path."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    uid = uuid.uuid4().hex[:6]
    run_id = f"{ts}_{uid}"
    run_dir = os.path.join(base, run_id)
    os.makedirs(run_dir, exist_ok=True)
    return run_dir


def save_run_config(run_dir: str, cfg: Dict) -> str:
    """Persist the run config as config.json inside run_dir."""
    path = os.path.join(run_dir, "config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    return path


def save_run_results(run_dir: str, agg: Dict) -> str:
    """Persist aggregate KPIs as results.json inside run_dir."""
    path = os.path.join(run_dir, "results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(agg, f, indent=2)
    return path


def run_id_from_dir(run_dir: str) -> str:
    return os.path.basename(run_dir)
