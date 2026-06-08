# Resume Bullets — Scalable Simulation Framework

Two leveled sets. Use the VP / Solutions Architect bullets on the
Architect / Director resume; use the Cloud / ML Engineer bullets when
applying to senior IC roles.

All bullets are written in the active voice, lead with the business
outcome, and end with the quantifiable architectural decision. Edit
the project name out if the resume word budget is tight.

---

## VP / Solutions Architect level (4 bullets)

- **Architected an enterprise inventory stress-testing platform** that
  replaces ad-hoc "test in production" policy decisions with a
  Monte Carlo experimentation framework — quantifying p10 / p50 / p90
  service-level risk for every reorder policy before commitment;
  designed for operations leadership consumption, not engineering.

- **Delivered a multi-cloud reference architecture** for a simulation
  workload, with first-class implementations on Vertex AI Pipelines
  and a documented enterprise port to Azure Batch + Azure ML +
  Container Apps + Power BI — proving compute portability by design
  and limiting cloud lock-in to a single thin orchestration adapter
  (AZ-305-aligned).

- **Translated operational ERP experience into a defensible analytics
  platform**: codified the same reorder-policy decisions previously
  owned in industry (SSCOR) into a typed, validated, reproducible
  framework, with narrative outputs in operations-director language
  — closing the standard "data team produces a number, business
  doesn't trust it" failure mode.

- **Established the engineering-maturity baseline for the platform**:
  Pydantic-validated configuration contract, pinned dependency
  surface, CI on every PR (flake8 + smoke + regression guards),
  config-hash provenance per run, and reproducible Monte Carlo runs
  with no mocked outputs anywhere in the test path.

---

## Cloud Engineer / ML Engineer level (2 bullets)

- **Built a daily-resolution Monte Carlo inventory simulation engine
  in Python (NumPy + Pydantic)** with stochastic demand and lead-
  time models, configurable shock-window injection, cross-run
  aggregation (mean / std / p10 / p50 / p90), and a per-run trace
  artifact for downstream visualization — 200-run baseline scenario
  executes in well under a second.

- **Wrapped the engine as a Vertex AI Pipelines component**
  (`@kfp.dsl.component` with `Output[Metrics]` and `Output[Dataset]`)
  supporting parallel scenario fan-out and Vertex Experiments
  lineage, plus an in-process `run_component_locally` fallback that
  exercises the same contract in CI without a live GCP project —
  paired with a Streamlit + Plotly operations dashboard hosted on
  Azure Container Apps for executive consumption.
