import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from src.sim.run_simulation import main as run_sim_main  # we'll call the module via subprocess instead (cleaner)
import subprocess


def run_one(scenario: str, seed: int) -> str:
    """Runs one simulation and returns the created run folder name."""
    # Run module as a subprocess so it behaves exactly like CLI and prints normal logs
    cmd = ["python", "-m", "src.sim.run_simulation", "--scenario", scenario, "--seed", str(seed)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Run failed for {scenario} seed={seed}\nSTDERR:\n{result.stderr}\nSTDOUT:\n{result.stdout}")

    # Parse created run folder from stdout line: "✅ Simulation run created: runs\...."
    run_line = [ln for ln in result.stdout.splitlines() if "Simulation run created:" in ln]
    if not run_line:
        raise RuntimeError(f"Could not find run folder in output.\n{result.stdout}")
    run_path = run_line[0].split("Simulation run created:")[1].strip()
    return run_path


def read_aggregate_kpis(run_path: str) -> dict:
    p = Path(run_path) / "outputs" / "kpis_aggregate.json"
    import json
    return json.loads(p.read_text(encoding="utf-8"))


def append_registry_row(registry_path: Path, row: dict, header: List[str]) -> None:
    file_exists = registry_path.exists()
    with open(registry_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        if not file_exists:
            w.writeheader()
        w.writerow(row)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", nargs="+", default=["Base", "Conservative", "Stress", "BlackSwan"])
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 123, 999])
    parser.add_argument("--registry", default="registry/run_registry.csv")
    args = parser.parse_args()

    registry_path = Path(args.registry)
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    header = [
        "timestamp_utc",
        "scenario",
        "seed",
        "run_path",
        "fill_rate",
        "backorder_units",
        "stockout_periods",
        "safety_stock_breaches",
        "demand_total",
        "demand_fulfilled",
    ]

    ts = datetime.now(timezone.utc).isoformat()

    for scenario in args.scenarios:
        for seed in args.seeds:
            run_path = run_one(scenario, seed)
            agg = read_aggregate_kpis(run_path)
            row = {
                "timestamp_utc": ts,
                "scenario": scenario,
                "seed": seed,
                "run_path": run_path,
                "fill_rate": agg.get("fill_rate"),
                "backorder_units": agg.get("backorder_units"),
                "stockout_periods": agg.get("stockout_periods"),
                "safety_stock_breaches": agg.get("safety_stock_breaches"),
                "demand_total": agg.get("demand_total"),
                "demand_fulfilled": agg.get("demand_fulfilled"),
            }
            append_registry_row(registry_path, row, header)
            print(f"✅ Logged: {scenario} seed={seed} → {run_path}")

    print(f"\n📌 Registry updated: {registry_path}")


if __name__ == "__main__":
    main()