from datetime import datetime, timezone
from pathlib import Path


def make_run_dir(base_dir: str | Path, scenario_name: str, cfg_hash: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = f"{ts}_{scenario_name}_{cfg_hash}"
    run_dir = Path(base_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir