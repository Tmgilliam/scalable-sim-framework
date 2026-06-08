# Azure Architecture Extension

How the Scalable Simulation Framework runs at enterprise scale on
Microsoft Azure. This document is the multi-cloud counterpart to the
Vertex AI implementation in `vertex/`.

The framework was designed on Vertex AI first because GCP was the
initial deployment target. The architecture is deliberately cloud-
agnostic: the simulation core (`simulation.MonteCarloEngine`) and the
config contract (`simulation.ScenarioConfig`) are unchanged when the
orchestration layer moves to Azure. Only the wrapper around them
changes.

This is the same pattern Azure Well-Architected Framework recommends
for portable compute workloads: keep the domain logic free of cloud
SDK calls; isolate the orchestration plane in an adapter layer that
can be swapped per cloud.

---

## Reference architecture on Azure

```
              ┌──────────────────────────────────────────────┐
              │            Power BI (Premium)                │
              │   Executive reporting on scenario outcomes   │
              └────────────────────┬─────────────────────────┘
                                   │  (DirectQuery / import)
                                   ▼
              ┌──────────────────────────────────────────────┐
              │   Azure Blob Storage (Gen2, hierarchical)    │
              │   - scenario configs (JSON / YAML)           │
              │   - per-run metrics artifacts                │
              │   - per-day inventory traces                 │
              └────────────────────┬─────────────────────────┘
                                   │
            ┌──────────────────────┴─────────────────────┐
            │                                            │
            ▼                                            ▼
  ┌──────────────────────┐                  ┌────────────────────────┐
  │  Azure Machine       │                  │   Azure Batch          │
  │  Learning            │                  │   (parallel compute)   │
  │                      │                  │                        │
  │  - Experiments       │◄──── job links ──┤  - Pool: D-series VMs  │
  │  - Pipelines (jobs)  │                  │  - Tasks: one Monte    │
  │  - Model lineage     │                  │    Carlo scenario each │
  │  - Compute clusters  │                  │  - Autoscale formula   │
  └──────────┬───────────┘                  └────────────┬───────────┘
             │                                           │
             │                                           │
             ▼                                           ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │                  Azure Container Registry                        │
  │            (simulation/azure-runner:vN images)                   │
  └──────────────────────────────────────────────────────────────────┘
                                   ▲
                                   │  built by GitHub Actions on push
                                   │
  ┌──────────────────────┐                  ┌────────────────────────┐
  │  Azure Container     │                  │   Microsoft Entra ID   │
  │  Apps                │                  │   - service principal  │
  │  - Streamlit         │                  │     for AML pipelines  │
  │    dashboard         │                  │   - managed identities │
  │  - Scales to zero    │                  │     for Container Apps │
  │  - Front Door + WAF  │                  │     and Batch tasks    │
  └──────────────────────┘                  └────────────────────────┘
```

---

## Component mapping — Vertex AI vs Azure

| Concern | Vertex AI implementation | Azure equivalent |
| --- | --- | --- |
| Parallel Monte Carlo execution | `kfp` pipeline with one component per scenario, fan-out in `PipelineJob` | **Azure Batch** pool with one task per scenario, or **Azure ML pipeline** with parallel run step |
| Experiment tracking | Vertex AI Experiments | **Azure ML Experiments** (`mlflow` API natively supported by Azure ML) |
| Artifact lineage | Vertex Metadata Store | Azure ML Asset Store (datasets, models, components) |
| Config + results storage | GCS bucket | **Azure Blob Storage Gen2** (`abfss://`) |
| Container image registry | Artifact Registry | **Azure Container Registry** |
| Dashboard hosting | Cloud Run | **Azure Container Apps** (scales to zero, request-driven) |
| Executive reporting | Looker / BigQuery | **Power BI Premium** over Blob Storage / Synapse |
| Identity & secrets | Workload Identity + Secret Manager | **Microsoft Entra ID workload identity** + **Azure Key Vault** |
| CI/CD | GitHub Actions → Cloud Build → Vertex | GitHub Actions → ACR build → Azure ML / Container Apps |
| IaC | Terraform with `google` provider | **Bicep** (preferred for AZ-305 portfolio) or Terraform with `azurerm` |

---

## Why Azure Batch for Monte Carlo (not Functions, not AKS)

A Monte Carlo policy sweep is a textbook embarrassingly-parallel
batch workload:

- 1,000–10,000 independent tasks per sweep.
- Each task is CPU-bound, runs for tens of seconds to a few minutes.
- No inter-task communication.
- Tasks must be reproducible — same seed, same result.
- Scheduling window is bursty: zero load for hours, then full
  pool utilization for 5–10 minutes.

This pattern maps to Azure Batch exactly:

- **Job + task** model fits one-task-per-scenario perfectly.
- **Pool autoscale** with a formula like
  `$TargetDedicatedNodes = min(100, $PendingTasks.GetSample(1, 5))`
  spins the cluster up and back to zero around the work.
- **Per-task resource files** stream the scenario config from Blob
  Storage at the start of each task and stage results back at the
  end. No long-lived storage state inside the compute pool.
- **Low-priority / spot VMs** typically cut Monte Carlo cost by 60–80%
  because tasks are cheap to retry and idempotent.

Not Azure Functions: a 1,000-task sweep would hit the per-execution
timeout and concurrency limits, and the cold-start tax on each task
outweighs the work. Functions are right for the *trigger* (HTTP /
queue) that launches a Batch job, not for the compute itself.

Not AKS: AKS is the right answer when the workload is long-running,
needs custom networking, or shares a control plane with other
services. A pure batch sweep does not justify the operational tax
of running a Kubernetes cluster you have to patch and monitor.

---

## Why Azure ML for experiment tracking (alongside or replacing Vertex AI)

Azure ML provides three capabilities the Batch tier alone does not:

1. **Experiment grouping.** Every scenario sweep becomes a *Job* in
   an *Experiment*. Operations leadership can pull a single experiment
   ID and see every policy variation tested for that quarter.
2. **MLflow-compatible tracking API.** The component code logs
   metrics with `mlflow.log_metric(...)` — same call you would make
   on Databricks, on a local Mlflow server, or against Vertex
   Experiments via the Mlflow plugin. This is the single line of
   code that makes the framework multi-cloud at the tracking layer.
3. **Lineage from data → component → output.** When the Power BI
   dashboard surfaces "we recommend reorder point = 950," the lineage
   trail in Azure ML shows the exact scenario config, exact code
   version, and exact Blob Storage artifacts that produced the
   recommendation. That is the AZ-305 governance story.

For organizations that already standardized on Azure ML, the
`vertex/pipeline.py` component is ported by replacing the
`@kfp.dsl.component` decorator with `@azureml.dsl.command_component`,
swapping the `Output[Metrics]` / `Output[Dataset]` types for Azure ML
`Output(type="uri_file")`, and pointing the artifact paths at Blob
Storage. The underlying simulation call (`MonteCarloEngine(cfg).run()`)
does not change.

---

## Why Azure Container Apps for the Streamlit dashboard

The dashboard is a low-traffic, request-driven web service:

- Operations leadership uses it during planning sessions, not 24/7.
- It must scale to zero between sessions (no idle cost).
- It must integrate with Entra ID for SSO and managed identity for
  Blob Storage access.
- It must support a custom domain behind Azure Front Door + WAF.

Azure Container Apps gives all four without the operational tax of
AKS. Scale rule:

```yaml
scale:
  minReplicas: 0
  maxReplicas: 5
  rules:
    - name: http-rule
      http:
        metadata:
          concurrentRequests: "20"
```

App Service is a viable alternative, but Container Apps wins for
this profile because of native scale-to-zero (App Service Basic and
above always bill for at least one running instance).

---

## Power BI integration path

The executive reporting layer sits on top of Blob Storage, not on top
of the simulation engine. That separation keeps the analytics
workload from competing with the compute workload.

Recommended pipeline:

1. **Batch task** writes `metrics.json` + `trace.json` per scenario
   to `abfss://results@<account>.dfs.core.windows.net/<experiment>/<scenario>/`.
2. **Azure Synapse Serverless SQL** exposes the JSON files as a view
   using `OPENROWSET` — no ingestion step, no warehouse provisioning.
3. **Power BI Premium** connects via DirectQuery to the Synapse view.
   Operations leadership sees a live cost / service / risk dashboard;
   no refresh schedule to maintain.
4. **RLS in Power BI** restricts visibility per business unit if the
   framework is shared across the enterprise.

This pattern reuses Blob Storage as the source of truth and avoids
the standard anti-pattern of "Power BI dataset that grew until it
became the source of truth and nobody can audit it."

---

## Multi-cloud architecture note (the portfolio point)

This framework demonstrates a deliberate multi-cloud posture:

- **Simulation core** (Python, numpy, Pydantic) — cloud-agnostic.
- **Config contract** (`ScenarioConfig` JSON / YAML) — portable.
- **Orchestration adapters** (`vertex/pipeline.py`, the future
  `azure_ml/pipeline.py`) — thin, swappable, identical surface.
- **Storage adapter** — Blob Storage paths and GCS paths are
  interchangeable through a small `storage.py` adapter that the
  business logic does not import directly.

The architecture deliberately does not pick a winner. An enterprise
already on Azure runs this on Batch + Azure ML; an enterprise on GCP
runs it on Vertex AI; an enterprise on both can prove its
multi-cloud strategy on a real workload, not a slide.

This is the AZ-305 architectural lens applied to a real problem:
choose the cloud at the *orchestration* layer, not at the *compute*
layer. Compute portability is the default; cloud lock-in is a
deliberate decision made one adapter at a time.

---

## Deployment summary

A reference Bicep deployment provisions:

- Resource group + log analytics workspace + diagnostic settings.
- Azure Blob Storage (Standard_LRS, hierarchical namespace, private
  endpoint + RBAC, no public access).
- Azure Container Registry (Premium, with content trust enabled).
- Azure Container Apps environment + dashboard app (scale to zero,
  managed identity, Entra ID integration via Easy Auth).
- Azure ML workspace + default compute cluster (LowPriority,
  D4s_v5 nodes, autoscale 0–20).
- Azure Batch account + pool (LowPriority spot VMs, autoscale
  formula above).
- Key Vault for non-managed-identity secrets (CI/CD service principal
  fallback).
- Microsoft Entra ID app registration for the dashboard SSO.
- Azure Front Door Standard + WAF policy in front of the Container
  Apps environment.

Cost envelope for a 1,000-scenario monthly sweep on Low-Priority Batch
(D4s_v5, ~3 minutes per task, ~8 vCPU-hours per sweep) lands in the
$5–$15 range. The framework is enterprise-defensible from a cost
perspective; the Monte Carlo simulation is not the expensive part of
the inventory program — the stockouts it prevents are.
