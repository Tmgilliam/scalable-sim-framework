# Scalable Simulation Framework — Inventory Stress Testing

A safe sandbox for testing inventory policy decisions before they hit production.

Operations and supply chain teams make planning calls under uncertainty —
demand fluctuates, lead times slip, reorder rules behave differently under
stress. Most organizations test those decisions in production, which means
the first signal of a bad assumption is a stockout or an overstock event
that has already cost money.

This framework replaces "test in production" with a repeatable Monte Carlo
experimentation platform. It runs locally, scales on Google Vertex AI, and
ports cleanly to Azure ML / Azure Batch for enterprise rollout.

---

## What's in the box

| Layer | Path | Purpose |
| --- | --- | --- |
| Core Monte Carlo engine | `simulation/` | Pydantic-configured daily simulation, N runs per scenario, p10/p50/p90 aggregation |
| Legacy weekly multi-SKU engine | `src/sim/` | Original portfolio engine — preserved, used by smoke tests and historical run registry |
| Pre-built scenario library | `simulation/scenarios.py` | Baseline, demand shock, lead-time crisis, combined stress, service-level sensitivity sweep |
| Vertex AI pipeline | `vertex/` | `kfp` component wrapping the engine with a local-executor fallback |
| Streamlit dashboard | `dashboard/app.py` | Operations-leadership view: configure, run, compare, visualize |
| Azure architecture extension | `docs/azure-architecture.md` | How the same framework runs on Azure Batch + Azure ML + Container Apps |
| Portfolio | `portfolio/` | Case study, interview talk track, resume bullets |
| CI | `.github/workflows/ci.yml` | flake8 + pytest smoke and regression guards |

---

## Quickstart

```bash
python -m venv .venv
. .venv/Scripts/activate     # PowerShell:  .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Run a single Monte Carlo scenario locally

```bash
python -m simulation.scenarios --scenario baseline --num-runs 200
```

### Run the legacy weekly engine (multi-SKU)

```bash
python -m src.sim.run_simulation --scenario Base --seed 42
```

### Launch the dashboard

```bash
streamlit run dashboard/app.py
```

### Run the test suite

```bash
pytest -v
```

---

## Architecture at a glance

```
   ┌──────────────────────┐
   │  Streamlit dashboard │  ← operations leadership
   └──────────┬───────────┘
              │
   ┌──────────▼───────────┐
   │  simulation/engine   │  ← Monte Carlo loop, Pydantic config
   └──────────┬───────────┘
              │
   ┌──────────▼───────────┐
   │   Vertex AI pipeline │  ← kfp @component, parallel scenarios, experiment lineage
   └──────────┬───────────┘
              │
              ▼
       Azure ML / Azure Batch (extension path — see docs/azure-architecture.md)
```

The framework was designed on Vertex AI and ports cleanly to Azure ML — same
component contract, same artifact lineage model. That's the multi-cloud
architecture story: pick the orchestration plane your organization standardized
on; the simulation core does not change.

---

## Status

See [`status.md`](./status.md) for the audit log from the most recent
completion session — what existed, what was broken, what was added, and why.
