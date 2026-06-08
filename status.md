# Project Status — Audit & Completion Log

This document records the state of the project at the start of the
completion session and every change made during it.

Maintainer: Dr. Tatianna Gilliam — Cloud & AI Architect.

---

## 1. Baseline state (start of session)

### What existed and ran

- `src/sim/sim_engine.py` — weekly, multi-SKU inventory simulator
  supporting both min/max and reorder-point (ROP) policies, demand
  shock injection, and lead-time sampling from either a range or a
  normal distribution. Working.
- `src/sim/scenario.py` + `src/utils/config.py` — YAML catalog loader
  with deep-merge scenario inheritance (defaults + overrides) and a
  stable config hash for run identity. Working.
- `src/sim/run_simulation.py` — CLI entry point that loads a scenario,
  runs the engine, writes `config.json` plus aggregate and per-SKU KPI
  JSON to a timestamped run directory. Working.
- `src/sim/batch_runner.py` — sweeps scenarios × seeds and appends rows
  to `registry/run_registry.csv`. Working (calls `run_simulation.py`
  via subprocess).
- `src/sim/data_loader.py` — CSV loader for SKU parameters. Working.
- `configs/scenarios/catalog.yaml` — Base / Conservative / Stress /
  BlackSwan scenarios with realistic overrides.
- `configs/data/sample_skus.csv` — 3-SKU sample dataset.
- `tests/smoke_test.py` and `tests/validate_outputs.py` — pytest checks
  that exercise the CLI end-to-end and assert KPI ranges. Working.
- `.github/workflows/ci.yml` — flake8 + pytest on PR / push.
- `.github/workflows/deploy.yml` — optional GCP Cloud Run deploy stub.
- `runs/` and `registry/run_registry.csv` — accumulated reproducible
  run history dating back to 2026-03-05.

### What was broken

- **`src/sim/run_scenario.py`** had a circular import: it imported
  `make_run_dir` from itself instead of from `src.utils.run_utils`.
  The file would fail to execute. The functionally identical (and
  correct) entry point `src/sim/run_simulation.py` was the one
  actually wired into tests and the batch runner, so this bug had no
  runtime impact but was a latent footgun.
- **`requirements.txt`** was empty. The project had no declared
  dependency surface.
- **`README.md`** was empty. No onboarding, no architecture overview.

### What was missing entirely

- A Pydantic-validated configuration model (Phase 2 spec).
- A true Monte Carlo loop with cross-run aggregation (mean, std, p10,
  p50, p90). The legacy engine runs once per seed; Monte Carlo
  aggregation lived only in the CSV registry, not in the engine.
- A pre-built scenario library with narrative interpretation
  (Phase 2 spec).
- Vertex AI pipeline integration (Phase 3 spec).
- Streamlit dashboard (Phase 4 spec).
- Azure architecture documentation (Phase 5 spec).
- Portfolio artifacts — case study, interview talk track, resume
  bullets (Phase 6 spec).

---

## 2. Changes made during this session

### Stabilization

- Fixed the circular import in `src/sim/run_scenario.py`. It now
  imports `make_run_dir` from `src.utils.run_utils`, matching the
  working `run_simulation.py` entry point. The file is kept (not
  deleted) because the audit rule said "do not delete without
  documenting why," and because it is a documented entry point for
  the legacy engine.
- Populated `requirements.txt` with pinned, conservative version
  ranges for numpy, pandas, pydantic, PyYAML, streamlit, plotly, kfp,
  pytest, pytest-cov, and flake8.
- Wrote a top-level `README.md` describing the framework, the
  directory layout, and the quickstart commands.

### Phase 2 — Core simulation engine (new)

- Added `simulation/config.py` with a Pydantic `ScenarioConfig` model.
  Parameters: `initial_inventory`, `demand_mean`, `demand_std`,
  `lead_time_mean`, `lead_time_std`, `reorder_point`, `reorder_qty`,
  `service_level_target`, `simulation_days`, `num_runs`, plus
  optional `demand_shock` and `lead_time_shock` blocks. Validators
  enforce non-negative inventory, `reorder_point > 0`,
  `simulation_days ∈ [30, 730]`, `0 < service_level_target < 1`, and
  `num_runs >= 1`. Loaders accept JSON and YAML files. Scenario
  inheritance is supported via `ScenarioConfig.with_overrides(...)`.
- Added `simulation/engine.py` with a daily Monte Carlo loop. Per
  run it tracks on-hand, on-order, and backorder positions; samples
  daily demand from a normal distribution (floored at zero); places
  reorders when inventory position drops below `reorder_point`;
  samples lead times from a normal distribution (floored at 1 day);
  records `stockout_days`, `fill_rate`, `avg_inventory`,
  `service_level_achieved`, `total_orders_placed`, and a full daily
  trace for the first run (used by the dashboard's stress-test panel).
  Across runs it aggregates mean, std, p10, p50, p90 for every metric.
- Added `simulation/scenarios.py` with five pre-built scenarios:
  `baseline`, `demand_shock`, `lead_time_crisis`, `combined_stress`,
  and `service_level_sensitivity` (a sweep from 0.85 → 0.99). Each
  returns a `ScenarioResult` dataclass containing the config used,
  the metrics summary, and a plain-English narrative interpretation.
  CLI: `python -m simulation.scenarios --scenario <name>`.

### Phase 3 — Vertex AI integration (new)

- Added `vertex/pipeline.py`. The simulation runner is wrapped as a
  `kfp` component (real `@component` decoration, not pseudocode) with
  an `Input[Dataset]` for the config artifact and `Output[Metrics]` /
  `Output[Artifact]` outputs for the metrics summary and per-run
  trace. If `kfp` is not installed the module exposes a
  `run_component_locally(...)` fallback that executes the same logic
  in-process, so the contract can be exercised without a live GCP
  project. A `make_pipeline(scenarios=[...])` helper composes a
  parallel fan-out across scenarios for `vertex_ai.PipelineJob`.
- Added `vertex/README.md` explaining what Vertex AI adds vs. a local
  run (experiment tracking, parallel fan-out, artifact lineage),
  setup steps for a GCP project, and why this component pattern
  generalizes to any ML experimentation workflow.

### Phase 4 — Dashboard (new)

- Added `dashboard/app.py` — Streamlit app with four panels:
  1. Scenario Configuration (preset loader + custom-parameter inputs
     + validation messages + Run button).
  2. Results Summary (metric cards + p10/p50/p90 ranges + a plain
     English interpretation line).
  3. Scenario Comparison (up to three results side-by-side; the
     scenario meeting the service-level target at lowest average
     inventory is flagged automatically).
  4. Stress Test Visualization (Plotly chart of inventory position
     over time for a sample run, with stockout days shaded and
     reorder events marked).

### Phase 5 — Azure architecture (new)

- Added `docs/azure-architecture.md`. Documents how the framework
  runs at enterprise scale on Azure: Azure Batch for parallel Monte
  Carlo, Azure ML for experiment tracking (Vertex AI equivalent),
  Azure Blob Storage for configs and results, Azure Container Apps
  for the dashboard, and Power BI for executive reporting. Includes
  the multi-cloud architecture story: same component contract on
  Vertex AI and Azure ML.

### Phase 6 — Portfolio (new)

- Added `portfolio/case-study.md` — business framing, architecture,
  Vertex AI as the scale layer, Azure extension, connection to
  Dr. Gilliam's operational background at SSCOR.
- Added `portfolio/interview-talk-track.md` — 60-second pitch,
  architecture deep-dive, scripted answers to the predictable hard
  questions, and how to position Vertex AI for an Azure-focused
  interviewer.
- Added `portfolio/resume-bullets.md` — four VP / Solutions
  Architect-level bullets and two Cloud / ML Engineer-level bullets.

### Testing additions

- Added `tests/test_monte_carlo.py` exercising the new Pydantic
  config validation and the Monte Carlo aggregation contract.

---

## 3. Nothing deleted

Per the audit rule, no files were removed. The legacy
`src/sim/run_scenario.py` is kept (with its bug fixed) because:

- The existing test suite, batch runner, and `runs/` history reference
  the legacy engine surface.
- Removing it would invalidate `registry/run_registry.csv` provenance.
- Keeping both engines side-by-side demonstrates the migration story
  visibly in the repo (multi-SKU weekly → daily Monte Carlo).

---

## 4. How to validate the changes

```bash
pip install -r requirements.txt
pytest -v                                  # smoke + regression + MC tests
python -m simulation.scenarios --scenario baseline --num-runs 200
streamlit run dashboard/app.py
```

A successful run will print aggregated p10/p50/p90 metrics for
fill rate, stockout days, and average inventory.
