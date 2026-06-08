"""Run directory + reproducibility helpers.

Two run-directory schemes are supported, side by side:

* ``make_scenario_run_dir(base_dir, scenario_name, cfg_hash)`` — used by
  the scenario-aware entry points in ``src.sim.run_simulation`` and
  ``src.sim.run_scenario``. Names directories as
  ``YYYYMMDD_HHMMSS_<scenario>_<config_hash>`` so the
  ``validate_outputs.py`` regression guard can glob ``*_Base_*``.
* ``make_run_dir(base="runs")`` — used by the legacy v1 batch runner
  (``batch_runner.py`` at repo root) and ``main.py``. Names directories
  as ``YYYYMMDDTHHMMSS_<uid6>``. Preserved verbatim from the
  pre-completion-session standalone repo so the v1 CLI still works.

The two helpers coexist; nothing in this module is mutually exclusive.
``save_run_config`` and ``save_run_results`` are simple JSON writers
shared by both paths.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict


def make_scenario_run_dir(base_dir: str | Path, scenario_name: str, cfg_hash: str) -> Path:
    """Scenario-aware run directory used by the v2 entry points."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = f"{ts}_{scenario_name}_{cfg_hash}"
    run_dir = Path(base_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def make_run_dir(base: str = "runs") -> str:
    """Timestamp + uid run directory used by the v1 batch runner.

    Returns a string path for backward compatibility with the v1 CLI.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    uid = uuid.uuid4().hex[:6]
    run_id = f"{ts}_{uid}"
    run_dir = os.path.join(base, run_id)
    os.makedirs(run_dir, exist_ok=True)
    return run_dir


def save_run_config(run_dir: str, cfg: Dict) -> str:
    """Persist the run config as ``config.json`` inside ``run_dir``."""
    path = os.path.join(run_dir, "config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    return path


def save_run_results(run_dir: str, agg: Dict) -> str:
    """Persist aggregate KPIs as ``results.json`` inside ``run_dir``."""
    path = os.path.join(run_dir, "results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(agg, f, indent=2)
    return path


def run_id_from_dir(run_dir: str) -> str:
    """Return the basename of ``run_dir`` (the canonical run identifier)."""
    return os.path.basename(run_dir)
