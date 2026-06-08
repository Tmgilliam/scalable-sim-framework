"""Vertex AI / Kubeflow Pipelines wrapper for the Monte Carlo engine.

This module exposes the simulation as a Vertex AI Pipeline component
(`@kfp.dsl.component`) so it can be:
    * orchestrated as a step in a larger ML workflow,
    * fanned out in parallel across many scenarios in one PipelineJob,
    * tracked in Vertex AI Experiments with full artifact lineage.

Design choices
--------------
* The component uses `base_image=python:3.11-slim` and installs only
  numpy + pydantic + PyYAML at runtime. That keeps the container
  small and the cold start fast.
* It accepts the scenario config as a JSON-serialized parameter
  (not a file). For Monte Carlo scenarios the config is tiny
  (sub-kilobyte), so passing it inline avoids an unnecessary GCS
  round trip and removes a moving part from the pipeline.
* It writes two outputs: a `Metrics` artifact (visible in the Vertex
  Experiments UI) and a `Dataset` artifact (the full per-day trace
  for the dashboard).
* A `run_component_locally(...)` fallback runs the same logic in
  process so the contract is exercised by unit tests and developers
  without a live GCP project.

If `kfp` is not installed, the `@component` decorator is replaced by a
no-op pass-through so this module still imports cleanly. The
`make_pipeline(...)` helper raises a clear error in that case rather
than silently producing nothing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Optional kfp import
# ---------------------------------------------------------------------------

try:
    from kfp import dsl
    from kfp.dsl import Dataset, Input, Metrics, Output, component, pipeline

    _KFP_AVAILABLE = True
except ImportError:  # pragma: no cover — exercised only on hosts without kfp
    _KFP_AVAILABLE = False

    def component(*args: Any, **kwargs: Any):
        """No-op shim used when kfp is not installed."""

        def _wrap(fn):
            return fn

        if args and callable(args[0]):
            return args[0]
        return _wrap

    def pipeline(*args: Any, **kwargs: Any):
        def _wrap(fn):
            return fn

        if args and callable(args[0]):
            return args[0]
        return _wrap

    class _StubArtifact:
        def __init__(self) -> None:
            self.path = ""
            self.metadata: Dict[str, Any] = {}

        def log_metric(self, *_args: Any, **_kwargs: Any) -> None:
            pass

    class _Subscriptable:
        """Stub for Input[Metrics] / Output[Dataset] when kfp is absent.

        Class-level __class_getitem__ makes Input[Foo] return Input itself,
        which is enough to keep the module importable in environments that
        only need the local executor.
        """

        def __class_getitem__(cls, item):
            return cls

    Dataset = _StubArtifact  # type: ignore[assignment]
    Metrics = _StubArtifact  # type: ignore[assignment]
    Input = _Subscriptable  # type: ignore[assignment]
    Output = _Subscriptable  # type: ignore[assignment]
    dsl = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------


@component(
    base_image="python:3.11-slim",
    packages_to_install=[
        "numpy>=1.26,<3.0",
        "pydantic>=2.5,<3.0",
        "PyYAML>=6.0,<7.0",
    ],
)
def run_monte_carlo_scenario(
    scenario_name: str,
    config_json: str,
    metrics_out: Output[Metrics],
    trace_out: Output[Dataset],
) -> None:
    """Run one Monte Carlo scenario inside a Vertex AI Pipeline step.

    Args:
        scenario_name: Human-readable label written into the Metrics
            artifact for filtering in the Vertex Experiments UI.
        config_json: JSON-serialized `ScenarioConfig`. Passed inline
            because the payload is small and inline parameters do not
            require a GCS staging area.
        metrics_out: KFP `Metrics` output. We log mean / std / p10 /
            p50 / p90 for each tracked KPI so the Vertex UI can
            compare runs.
        trace_out: KFP `Dataset` output. We write the day-by-day
            trace as JSON so the downstream dashboard step can render
            inventory position over time.
    """
    import json as _json
    from pathlib import Path as _Path

    from simulation.config import ScenarioConfig
    from simulation.engine import MonteCarloEngine

    config = ScenarioConfig.from_dict(_json.loads(config_json))
    summary = MonteCarloEngine(config).run()

    for metric_name, stats in summary.metrics.items():
        for stat_name, value in stats.items():
            metrics_out.log_metric(f"{metric_name}_{stat_name}", float(value))
    metrics_out.log_metric("scenario", scenario_name)  # type: ignore[arg-type]

    trace_path = _Path(trace_out.path)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "scenario_name": scenario_name,
        "config": config.to_dict(),
        "summary": summary.to_dict(),
    }
    trace_path.write_text(_json.dumps(payload, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Pipeline composition
# ---------------------------------------------------------------------------


def make_pipeline(scenarios: List[Dict[str, Any]], pipeline_name: str = "inventory-stress-pipeline"):
    """Build a parallel-fanout pipeline that runs one component per scenario.

    Args:
        scenarios: List of {"name": str, "config": dict-or-ScenarioConfig}.
        pipeline_name: KFP pipeline name shown in Vertex AI Pipelines.

    Returns:
        A `@dsl.pipeline`-decorated function ready for
        `kfp.compiler.Compiler().compile(...)` or
        `vertex_ai.PipelineJob(...)`.

    Raises:
        ImportError if `kfp` is not installed. Use
        `run_component_locally(...)` instead.
    """
    if not _KFP_AVAILABLE:
        raise ImportError(
            "kfp is not installed. Install kfp>=2.7 to compile Vertex AI pipelines, "
            "or use run_component_locally(...) to exercise the component contract."
        )

    serialized_scenarios = []
    for s in scenarios:
        name = s["name"]
        cfg = s["config"]
        cfg_dict = cfg.to_dict() if hasattr(cfg, "to_dict") else dict(cfg)
        serialized_scenarios.append({"name": name, "config_json": json.dumps(cfg_dict)})

    @pipeline(name=pipeline_name)
    def _inventory_stress_pipeline() -> None:
        for s in serialized_scenarios:
            run_monte_carlo_scenario(
                scenario_name=s["name"],
                config_json=s["config_json"],
            )

    return _inventory_stress_pipeline


# ---------------------------------------------------------------------------
# Local execution fallback
# ---------------------------------------------------------------------------


def run_component_locally(
    scenario_name: str,
    config: Any,
    output_dir: str | Path = "runs/vertex_local",
) -> Dict[str, Any]:
    """Execute the component logic in-process, mirroring the Vertex AI step.

    Useful for:
        * unit tests of the pipeline contract,
        * developers without a live GCP project,
        * a CI dry-run before promoting the pipeline definition.

    Args:
        scenario_name: Label for the run.
        config: Either a ScenarioConfig instance or a dict acceptable
            to `ScenarioConfig.from_dict`.
        output_dir: Directory where the metrics + trace JSON files are
            written. Mirrors the Vertex `Dataset` artifact location.

    Returns:
        A dict containing the metrics summary and the artifact paths.
    """
    from simulation.config import ScenarioConfig
    from simulation.engine import MonteCarloEngine

    cfg = config if isinstance(config, ScenarioConfig) else ScenarioConfig.from_dict(config)
    summary = MonteCarloEngine(cfg).run()

    out = Path(output_dir) / scenario_name
    out.mkdir(parents=True, exist_ok=True)

    metrics_path = out / "metrics.json"
    trace_path = out / "trace.json"

    metrics_path.write_text(
        json.dumps({"scenario": scenario_name, "metrics": summary.metrics}, indent=2),
        encoding="utf-8",
    )
    trace_path.write_text(
        json.dumps(
            {
                "scenario_name": scenario_name,
                "config": cfg.to_dict(),
                "summary": summary.to_dict(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "scenario_name": scenario_name,
        "summary": summary.to_dict(),
        "metrics_path": str(metrics_path),
        "trace_path": str(trace_path),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> None:
    import argparse

    from simulation.scenarios import SCENARIO_LIBRARY

    parser = argparse.ArgumentParser(description="Local executor for the Vertex AI simulation component.")
    parser.add_argument(
        "--scenario",
        default="baseline",
        choices=list(SCENARIO_LIBRARY.keys()),
        help="Pre-built scenario to execute via the local component fallback.",
    )
    parser.add_argument("--num-runs", type=int, default=100)
    parser.add_argument("--simulation-days", type=int, default=120)
    parser.add_argument("--out", default="runs/vertex_local")
    parser.add_argument(
        "--compile-pipeline",
        action="store_true",
        help="Compile a multi-scenario Vertex AI pipeline YAML (requires kfp).",
    )
    args = parser.parse_args()

    if args.compile_pipeline:
        if not _KFP_AVAILABLE:
            raise SystemExit("kfp is not installed. Install with: pip install 'kfp>=2.7,<3.0'")
        from kfp import compiler  # type: ignore

        from simulation.scenarios import (
            scenario_baseline,
            scenario_demand_shock,
            scenario_lead_time_crisis,
            scenario_combined_stress,
        )

        scenarios = [
            {"name": "baseline", "config": scenario_baseline(num_runs=10, simulation_days=60).config},
            {"name": "demand_shock", "config": scenario_demand_shock(num_runs=10, simulation_days=60).config},
            {"name": "lead_time_crisis", "config": scenario_lead_time_crisis(num_runs=10, simulation_days=60).config},
            {"name": "combined_stress", "config": scenario_combined_stress(num_runs=10, simulation_days=60).config},
        ]
        pipeline_fn = make_pipeline(scenarios)
        output_path = Path(args.out) / "pipeline.yaml"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        compiler.Compiler().compile(pipeline_fn, str(output_path))
        print(f"Compiled Vertex AI pipeline -> {output_path}")
        return

    if args.scenario == "service_level_sensitivity":
        raise SystemExit(
            "The 'service_level_sensitivity' sweep produces multiple sub-runs; "
            "execute it via `python -m simulation.scenarios` rather than the Vertex local executor."
        )

    result = SCENARIO_LIBRARY[args.scenario](
        num_runs=args.num_runs,
        simulation_days=args.simulation_days,
    )

    payload = run_component_locally(
        scenario_name=args.scenario,
        config=result.config,
        output_dir=args.out,
    )
    print(f"Local component run complete. Metrics: {payload['metrics_path']}")
    print(f"Trace artifact: {payload['trace_path']}")


if __name__ == "__main__":
    _cli()
