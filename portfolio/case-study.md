# Case Study — Scalable Simulation Framework for Inventory Stress Testing

**Owner:** Dr. Tatianna Gilliam, Cloud & AI Architect
**Repo:** `scalable-sim-framework`
**Scope:** Python · Pydantic · NumPy · Monte Carlo · Vertex AI · Azure ML · Azure Batch · Streamlit · CI/CD

---

## The business problem

Operations and supply-chain teams make inventory policy decisions
under uncertainty. Demand fluctuates. Lead times slip. Reorder rules
that look conservative on paper behave very differently under stress.

Most organizations test these decisions in production. That means
the first signal of a bad assumption is a stockout that drains
revenue, or an overstock event that ties up working capital. By the
time the signal arrives, the decision is months old, the inventory is
already on a ship or in a warehouse, and the operations leader is
explaining the variance to finance instead of preventing it.

The cost of "test in production" in inventory is not theoretical. At
SSCOR, I sat in the exact decision meetings this framework is built
for — ERP screens full of MRP recommendations and no rigorous way to
ask "what happens to fill rate if our usual 7-day supplier slips to
14 days for the next quarter?" The answer was always somebody's
spreadsheet, and the spreadsheet was always wrong at the tails.

This framework replaces the spreadsheet with a repeatable, defensible
experimentation platform.

---

## What it does

The framework is a Monte Carlo inventory simulator wrapped in three
layers of operational maturity:

1. **Core simulation engine** (`simulation/engine.py`): a daily,
   stochastic inventory model. Demand is sampled from a normal
   distribution; lead times are sampled from a normal distribution
   with a 1-day floor; reorders trigger when inventory position
   crosses a configurable threshold. Each scenario runs hundreds of
   independent replications and reports the p10 / p50 / p90 of every
   business KPI — fill rate, stockout days, average inventory, and
   service level achieved.
2. **Pre-built scenario library** (`simulation/scenarios.py`):
   baseline, demand shock, lead-time crisis, combined stress, and a
   service-level sensitivity sweep that quantifies the inventory
   cost of each additional percentage point of service. Every
   scenario returns a narrative interpretation written for an
   operations director, not a data scientist.
3. **Two cloud orchestration layers**: a Vertex AI Pipelines
   component (`vertex/pipeline.py`) that runs scenarios in parallel
   with full experiment and lineage tracking, and a documented Azure
   architecture (`docs/azure-architecture.md`) that ports the same
   workload to Azure Batch + Azure ML.

The dashboard layer (`dashboard/app.py`) — Streamlit on Plotly —
exposes the framework to operations leadership directly. No notebook
access required. No Python required. Configure, run, compare,
visualize.

---

## Why Monte Carlo, specifically

Monte Carlo simulation is not a statistics exercise. It is a *risk
quantification tool*. The output of one historical analysis is one
number ("last quarter we hit 94% fill rate"). The output of a 1,000-
run Monte Carlo simulation is a *distribution* of outcomes ("under
these conditions, you would expect 94% half the time, but 10% of
plausible futures take you below 89% — is that acceptable?").

The operations leader makes a categorically different decision when
the question shifts from "what was the average?" to "what does the
left tail look like?" Inventory programs do not fail because of the
average outcome. They fail because of the bad tail — the quarter
where demand spiked while the lead time slipped, and the policy that
worked at the mean lost on both axes at once.

The `combined_stress` scenario in this framework is exactly that
tail. The framework's job is to put it on the operations director's
desk *before* the quarter starts.

---

## Why historical data alone is not enough

Historical analysis answers "what happened?" Simulation answers
"what could happen?"

Three reasons that distinction matters for inventory:

1. **The future is not the past.** Lead-time distributions shift
   when a supplier changes, a port closes, or a tariff changes. A
   policy validated on five years of "normal" history is silently
   invalid the day the next shock starts. The simulator can ingest
   the new lead-time assumption and re-run all five scenarios in
   minutes.
2. **The past is rarely deep enough at the tails.** Stockout days
   are rare events. Most organizations have only a handful of real
   stockouts in their history — not enough to estimate p90 risk with
   any precision. Monte Carlo manufactures the tail by replicating
   the policy thousands of times against the assumed distribution.
3. **You cannot A/B test inventory policy in production.** Unlike
   a recommendation algorithm, you cannot give half your customers
   policy A and half policy B. You get one policy per quarter and
   you wear the outcome. The simulator is the only safe place to
   ask "what would the other policy have produced?"

---

## Vertex AI as the scale layer

The Vertex AI integration is the difference between *a Python
notebook* and *an enterprise-grade decision support system*.

Specifically, Vertex AI adds three things the local simulator cannot:

- **Experiment tracking.** Every scenario, every parameter, every
  metric is captured in Vertex AI Experiments. Six months from now,
  when finance asks "what assumptions did we test before approving
  the new reorder policy?", the answer is two clicks in the Vertex
  console, not an archeological dig through somebody's Downloads
  folder.
- **Parallel fan-out.** A `kfp` pipeline launches one component per
  scenario and runs them concurrently on Vertex-managed compute.
  A five-scenario × 1,000-run sweep that takes 30 minutes
  sequentially takes two minutes in parallel.
- **Artifact lineage.** The Pipelines runtime captures container
  image, input parameters, and output artifacts for every step. The
  audit trail is automatic.

The component contract (`@kfp.dsl.component` with `Output[Metrics]`
and `Output[Dataset]`) is real kfp syntax, not pseudocode. The
module includes a `run_component_locally(...)` fallback so the same
contract is exercised in unit tests and on developer machines
without requiring a live GCP project. That dual-mode pattern is what
makes the framework usable end-to-end without infrastructure cost
during development.

---

## Azure extension — multi-cloud architecture credibility

The Azure architecture document (`docs/azure-architecture.md`) is
not aspirational. It documents the exact port of every Vertex AI
component to its Azure equivalent — Azure Batch for parallel Monte
Carlo, Azure ML for experiment tracking, Blob Storage for configs
and artifacts, Container Apps for the dashboard, Power BI for the
executive reporting layer.

The architectural point is deliberate. The simulation core
(`simulation.MonteCarloEngine`) and the config contract
(`simulation.ScenarioConfig`) are unchanged when the orchestration
layer moves between clouds. Only the wrapper around them changes.

That is the AZ-305 lens applied to a real workload: compute
portability is the default; cloud lock-in is a deliberate decision
made one adapter at a time. An enterprise already on Azure runs
this framework on Batch + Azure ML; an enterprise on GCP runs it on
Vertex AI; an enterprise on both can prove its multi-cloud strategy
on a real workload, not on a deck.

The Azure-specific architecture choices in that document — Batch
over Functions for the compute layer, Container Apps over App
Service for scale-to-zero economics, Synapse Serverless over a
provisioned warehouse for the reporting view — are all
AZ-305-defensible. The doc is written to survive an architect-level
interview, not just to fill a deliverable slot.

---

## How this connects to my operational background

This is not a generic data-science exercise. I built this framework
because I lived the problem.

At SSCOR I owned the operational responsibility for exactly these
decisions — reorder thresholds, safety stock, service-level
commitments to customers. The ERP gave us recommendations. The
spreadsheets behind those recommendations gave us a single-point
estimate. Nobody could quantify the downside risk of accepting an
MRP recommendation against a stressed supply chain.

The framework is the system I wish I had then. It answers, in
minutes, the question that used to take three days of cross-
functional meetings and still produced an answer nobody trusted at
the tails:

> "If we ship this reorder policy and the supply chain misbehaves
>  the way it did last quarter, what is the probability that we
>  break our service-level commitment?"

That is not a Python question. It is an operations question. The
Python is the means; the *defensible answer to the operations
question* is the product.

---

## What this demonstrates

- **Architecture-level Python.** Pydantic-validated configs,
  type-annotated public APIs, separation between domain logic and
  orchestration layer, parallel test execution.
- **Cloud-native experimentation patterns.** Real Vertex AI Pipeline
  component, real KFP `@component`, real Monte Carlo replication
  semantics. Same contract ported to Azure ML.
- **Multi-cloud thinking.** Two orchestration layers wrapping one
  simulation core. Compute portability by design.
- **Business framing.** Every metric output is interpreted in
  operations-director language, not in p-values.
- **Operationally grounded.** Built by someone who has owned the
  decision the framework supports — inventory leader at SSCOR, now
  Cloud & AI Architect.

The repo is production-shaped: pinned dependencies, CI on every PR,
flake8 + pytest smoke and regression guards, reproducible runs with
config-hash provenance, no mocked outputs anywhere in the test path.
