# Interview Talk Track — Scalable Simulation Framework

How to talk about this project in interviews. Three lengths, the
predictable hard questions, and how to handle the Azure-focused
interviewer who sees Vertex AI on your repo.

The voice is operationally grounded, business-value first, architect
level. Resist the temptation to lead with the Python.

---

## 60-second pitch

> "Operations leaders make inventory decisions under uncertainty —
> demand changes, lead times slip, reorder rules behave differently
> under stress. Most organizations test those decisions in
> production, which means the first signal of a bad assumption is a
> stockout. I built a Monte Carlo simulation framework that replaces
> 'test in production' with a safe sandbox.
>
> It's a Python engine with Pydantic-validated configs that runs
> hundreds of stochastic replications per scenario and reports the
> full p10 / p50 / p90 distribution of every business KPI — fill
> rate, stockout days, average inventory. There's a pre-built
> scenario library — baseline, demand shock, lead-time crisis,
> combined stress — and a Streamlit dashboard that exposes the
> framework to operations leadership directly.
>
> For scale, I wrapped the engine as a Vertex AI Pipeline component
> with full experiment tracking and parallel fan-out. The same
> contract ports to Azure ML and Azure Batch — that's the multi-
> cloud architecture story, documented in detail in the repo. The
> simulation core doesn't change; only the orchestration wrapper
> does."

Hand-off line if they're still listening:
> "It's the system I wish I'd had when I owned these decisions at
> SSCOR. The Python is the means; the defensible answer to the
> operations question is the product."

---

## Architecture deep-dive (5–7 minutes)

Walk the architecture top-down: business problem → core engine →
orchestration → presentation layer → multi-cloud port.

**Step 1 — Frame the problem.**
> "Two things drive every inventory program — demand variability and
> lead-time variability. The interaction between them is what
> destroys service levels. Most organizations only model one at a
> time, and never quantify the tail risk. I wanted a framework that
> models both simultaneously and gives operations leadership the
> p10 outcome, not just the average."

**Step 2 — Walk the core engine.**
> "The engine is a daily Monte Carlo loop. Demand is normal,
> floored at zero. Lead time is normal, floored at one day. Reorders
> trigger when inventory position drops below a threshold. Per run
> we record stockout days, fill rate, average inventory, service
> level achieved, total orders placed. Across hundreds of runs we
> aggregate to mean, std, p10, p50, p90."
>
> "The config is Pydantic-validated. That matters because operations
> leadership runs this through a UI — we need configuration errors
> to fail loud and early, not three minutes into a thousand-run
> sweep. The config also has built-in cross-field validators — for
> example, a reorder quantity that doesn't cover the expected
> lead-time demand triggers a validation error, because operations
> would never run that policy."

**Step 3 — Walk the scenario library.**
> "Five pre-built scenarios. Baseline is steady-state. Demand shock
> doubles demand for 30 days — that models a launch event or panic
> buying. Lead-time crisis doubles lead time for 45 days — that
> models a port closure. Combined stress runs both shocks
> simultaneously, which is the case operations leadership actually
> worries about. And service-level sensitivity sweeps the target
> from 85% to 99% so we can quantify the inventory cost of every
> additional percentage point of service. Each scenario returns a
> narrative interpretation, written in the language operations uses
> to make decisions."

**Step 4 — Walk Vertex AI integration.**
> "Vertex AI adds three things the local simulator can't. One,
> Experiments — every scenario, every parameter, every metric is
> tracked with full lineage. Two, parallel fan-out — a five-scenario
> by 1,000-run sweep that takes 30 minutes sequentially takes two
> minutes in parallel. Three, artifact lineage — six months from
> now, when finance asks what assumptions we tested before approving
> the new policy, the answer is two clicks in the Vertex console.
>
> The component is real kfp syntax — `@kfp.dsl.component`,
> `Output[Metrics]`, `Output[Dataset]`. And it includes a
> `run_component_locally` fallback that executes the same logic
> in-process, so the contract is exercised in unit tests and on
> developer machines without a live GCP project."

**Step 5 — Walk the Azure architecture extension.**
> "The Azure story is in `docs/azure-architecture.md`. Azure Batch
> for the parallel Monte Carlo — it's the canonical embarrassingly-
> parallel batch pattern, low-priority spot VMs cut the cost by
> 60-80% because tasks are idempotent. Azure ML for experiment
> tracking with the same MLflow API. Blob Storage for configs and
> artifacts. Container Apps for the Streamlit dashboard because it
> scales to zero between operations planning sessions. Power BI on
> top of Synapse Serverless for the executive reporting layer.
>
> The architectural point is that the simulation core and the config
> contract don't change between Vertex AI and Azure ML. Only the
> orchestration wrapper changes. That's compute portability by
> design, cloud lock-in by deliberate decision."

**Step 6 — Land the connection to your background.**
> "I built this because I lived the problem. At SSCOR I owned these
> exact decisions — reorder thresholds, safety stock, service-level
> commitments. The ERP gave us recommendations; nobody could
> quantify the downside risk. This framework is the system I wish
> I had then."

---

## How to answer: "Why simulation instead of just analyzing historical data?"

> "Historical analysis answers 'what happened?' Simulation answers
> 'what could happen?'
>
> Three reasons that distinction matters in inventory. One — the
> future isn't the past. Lead-time distributions shift the day a
> supplier changes or a port closes; a policy validated on five
> years of normal history is silently invalid the day the next
> shock starts. Two — the past is rarely deep enough at the tails.
> Stockout days are rare events; most organizations have only a
> handful of real stockouts in their history, not enough to
> estimate p90 risk with any precision. Three — you can't A/B test
> inventory policy in production. You get one policy per quarter
> and you wear the outcome. The simulator is the only safe place
> to ask what the other policy would have produced."

If they push: "So you don't use historical data at all?"
> "Of course we use it — it's how we calibrate the demand mean,
> the demand std, the baseline lead-time distribution. The
> historical data is the input to the simulation. The simulation
> is what lets us extrapolate responsibly into futures we haven't
> observed."

---

## How to answer: "How does this connect to your ERP background?"

> "Directly. At SSCOR, my job was to sit between the ERP's MRP
> recommendations and the operations decisions that committed real
> money to real inventory. The ERP would say 'reorder 2,000 units
> of SKU 100.' I had to decide whether that number was right under
> our actual supply chain conditions.
>
> The shortcut answer was always 'trust MRP'. The honest answer was
> always 'we don't know what happens if the lead time slips.' This
> framework is the rigorous version of the question I used to ask
> in those meetings. Same business question, same business
> stakeholders, same business stakes — but now there's a defensible
> quantitative answer instead of a spreadsheet."

If they push on ERP specifics:
> "The framework's data contract — initial inventory, demand mean,
> demand std, lead time mean, lead time std, reorder point, reorder
> quantity — maps almost one-to-one onto the master data fields you
> already have in SAP, Oracle, NetSuite, or D365. The framework
> isn't a replacement for the ERP; it's a what-if layer that sits
> on top of the ERP's master data and answers questions the ERP
> can't."

---

## How to position Vertex AI for an Azure-focused interviewer

The trap: defending Vertex AI as a *choice* when the interviewer
wants to know whether you understand Azure.

The right move: pivot to the architecture, not the cloud.

> "Vertex AI is the reference implementation in the repo because
> GCP was where I built the first version. The architecture is
> deliberately cloud-agnostic — the simulation core and the config
> contract don't change when the orchestration layer moves to
> Azure. The Azure architecture doc walks the port component by
> component: Vertex AI Pipelines becomes Azure Batch plus Azure ML.
> Vertex Experiments becomes Azure ML Experiments via the same
> MLflow API. GCS becomes Blob Storage. Cloud Run becomes Container
> Apps. The same `@component` pattern in the repo ports by
> replacing one decorator and one set of artifact types.
>
> If anything, having the Vertex AI reference makes the Azure port
> stronger — it forces the architecture to be explicit about which
> capabilities live in the orchestration layer and which live in
> the compute. That's the AZ-305 lens applied to a real workload."

If they push: "But you don't have an Azure ML pipeline checked in."
> "Correct — what's checked in is the architecture document and the
> ported component contract. The Azure implementation is one
> dependency-injection swap away from what's already in the repo;
> I'd rather show the architecture that proves the port is real
> than ship a half-finished pipeline.yaml that doesn't run end-to-
> end. I'd build out the Azure ML pipeline as the next milestone
> in the role."

---

## Hard questions you should expect

**"How do you validate the simulation matches reality?"**
> "Three layers. One — calibrate the input distributions against
> historical demand and historical lead times for the SKU you're
> modeling. Two — run the baseline scenario and confirm the
> simulated fill rate falls inside the historical range. Three —
> use back-testing — replay the simulator against last quarter's
> conditions and confirm the simulated p10–p90 range contains the
> realized outcome. If the realized outcome falls outside the
> simulated p10–p90, the model is misspecified and we recalibrate."

**"What's the limitation of normal-distribution demand?"**
> "Two big ones. Normal demand has thin tails — real demand is
> closer to lognormal or has occasional spike events. Normal demand
> can go negative, which we clip to zero. For a production
> deployment I'd swap normal for either a fitted empirical
> distribution, or a lognormal with the parameters fit from
> historical data. The engine is already structured so the demand
> sampler is a single function — replacing it is a 10-line change."

**"What's the cost story?"**
> "On Azure Batch with low-priority VMs, a 1,000-scenario monthly
> sweep is in the five-to-fifteen dollar range. The Monte Carlo is
> not the expensive part of the inventory program — the stockouts
> it prevents are. If preventing one mid-sized stockout per year
> pays for the framework ten times over, the architecture is
> trivially defensible."

**"What would you build next?"**
> "Three things. One — the Azure ML pipeline implementation, side
> by side with the Vertex AI one, so the multi-cloud port is
> proven end-to-end, not just architected. Two — multi-SKU
> simulation with correlated demand, because real inventory programs
> have cross-product substitution that single-SKU runs can't model.
> Three — an integration with a real ERP master-data export so
> operations leadership can simulate against live policy parameters
> instead of YAML configs."
