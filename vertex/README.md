# Vertex AI Integration

This package wraps the Monte Carlo simulation engine as a Vertex AI
Pipeline component so the same simulation that runs on a laptop can
run, in parallel and with full lineage tracking, as part of a managed
ML workflow.

---

## Why Vertex AI vs. running locally

A local Monte Carlo run on a developer machine is enough to validate
a policy *idea*. It is not enough to defend a policy *decision* to
the business. Vertex AI adds three things the local engine cannot:

1. **Experiment tracking.** Vertex AI Experiments captures every
   metric (`fill_rate_mean`, `stockout_days_p90`, `avg_inventory_p50`,
   …) for every scenario run. The operations director can compare
   "the policy we are about to ship" against "the same policy from
   last quarter" without trusting that someone saved the right CSV.

2. **Parallel fan-out.** A single PipelineJob can launch one component
   per scenario, run them concurrently on Vertex-managed
   infrastructure, and write all results to a shared experiment.
   That turns a 5-scenario × 1,000-run sweep from a 30-minute
   sequential job into a 2-minute parallel one.

3. **Artifact lineage.** The Pipelines runtime records the exact
   container image, the exact input parameters, and the exact
   output artifacts (metrics + per-day trace) for every component
   step. When someone in 2027 asks "what assumptions did we test
   before approving the new reorder policy," the answer is two
   clicks in the Vertex console.

The local engine and the Vertex component share one configuration
schema (`simulation.ScenarioConfig`) and one runner
(`MonteCarloEngine`). The pipeline is a thin orchestration shell, not
a re-implementation. That is the architecture point: the simulation
core does not change when the scale layer changes.

---

## Setup

Prereqs:

- A GCP project with the Vertex AI API enabled.
- A staging GCS bucket for pipeline artifacts.
- A service account with `roles/aiplatform.user` on the project and
  write access to the staging bucket.
- `gcloud` authenticated and `kfp>=2.7,<3.0` installed:

```bash
pip install 'kfp>=2.7,<3.0' 'google-cloud-aiplatform>=1.50'
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

---

## Running a single scenario

### Locally (no GCP project required)

```bash
python -m vertex.pipeline --scenario baseline --num-runs 200 --simulation-days 180
```

This calls `run_component_locally(...)`, which executes the same
function body as the Vertex component step but in-process. It writes
`runs/vertex_local/<scenario>/metrics.json` and `trace.json`.

The local fallback is exactly what unit tests and CI use, so the
pipeline contract is enforced even without a GCP project. That is
the difference between "this looks like a Vertex pipeline" and
"this is a Vertex pipeline that happens to also run locally."

### As a Vertex AI Pipeline

```bash
python -m vertex.pipeline --compile-pipeline --out runs/vertex_local
```

This compiles a multi-scenario PipelineJob YAML
(`runs/vertex_local/pipeline.yaml`) you can submit with:

```python
from google.cloud import aiplatform

aiplatform.init(project="YOUR_PROJECT_ID", location="us-central1",
                staging_bucket="gs://YOUR_STAGING_BUCKET")

job = aiplatform.PipelineJob(
    display_name="inventory-stress-baseline-vs-shock",
    template_path="runs/vertex_local/pipeline.yaml",
    enable_caching=False,
)
job.submit(experiment="inventory-stress-2026Q3")
```

Each scenario becomes a parallel step. Metrics land in the
`inventory-stress-2026Q3` experiment; the per-day trace lands as a
Dataset artifact you can pull into Vertex AI Workbench notebooks or
BigQuery.

---

## Why this pattern generalizes

This is not a simulation-only pattern. It is the standard pattern for
any ML experimentation workflow where:

- the *core compute* is a deterministic, parameterized function,
- the *experiment* is a sweep over many parameter sets,
- the *deliverable* is a defensible comparison of outcomes.

Examples that drop into the same shape:

- Hyperparameter sweeps for an XGBoost model — one component, one
  config per trial, metrics into Experiments.
- Backtesting a trading strategy across N market regimes — one
  component, one regime per run, metrics into Experiments.
- A/B test simulation for a recommender — one component, one
  policy variant per run, metrics into Experiments.

The `@component` + `make_pipeline(scenarios=[...])` factory in this
module is reusable wholesale. Swap `MonteCarloEngine` for whatever
your core compute is.

---

## Multi-cloud note

The same component contract — `ScenarioConfig` in, `MetricsSummary`
out — runs on Azure ML pipelines with a one-file adapter (see
`docs/azure-architecture.md`). Vertex AI is the reference
implementation here because GCP was the initial target, not because
the architecture is GCP-coupled.
