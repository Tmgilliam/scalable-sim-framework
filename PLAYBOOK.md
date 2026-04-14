# Scalable Simulation Framework — Operations Playbook

## What This Is
A Python-based supply chain simulation engine that stress-tests inventory policies
across four scenario severities (Base → BlackSwan) and produces decision-ready KPI reports.
Runs locally in seconds; designed to scale to Google Cloud (GCS + Vertex AI) with one flag.

---

## How to Run

### Prerequisites
```bash
pip install pyyaml          # core (always required)
pip install pandas matplotlib jupyter   # for reports
pip install google-cloud-storage        # only if using GCS
pip install google-cloud-aiplatform     # only if using Vertex AI
```

### Local batch run (all scenarios, 3 seeds)
```bash
python main.py
```

### Target specific scenarios / seeds
```bash
python main.py --scenarios Stress BlackSwan --seeds 42 43 44 99
```

### With GCS mirroring (uploads each run folder to gs://bucket/...)
```bash
python main.py --bucket my-gcs-bucket --prefix sim-runs
```

### Submit as Vertex AI Custom Job
```bash
python main.py --vertex \
  --project my-gcp-project \
  --bucket my-gcs-bucket \
  --image gcr.io/my-gcp-project/sim-framework:latest
```

### Generate the executive summary report
```bash
python reports/build_notebook.py        # rebuilds the notebook
jupyter notebook reports/exec_summary.ipynb   # open and run all cells
```

---

## Output Structure

```
runs/
├── registry.csv                        ← all runs, one row each
└── 20260414T050849_6bf3fa/
    ├── config.json                     ← exact parameters used
    └── results.json                    ← KPIs for that run

reports/
├── exec_summary.ipynb                  ← interactive report
├── fill_rate_by_scenario.png
├── backorders_by_scenario.png
└── risk_heatmap.png
```

---

## How to Read the Results

| KPI | What it means | Healthy range |
|---|---|---|
| **Fill Rate** | % of demand fulfilled on time | > 0.95 (Base/Conservative) |
| **Backorder Units** | Unmet demand units over 52 weeks | < 500 (Base) |
| **Stockout Periods** | Weeks with zero on-hand stock | < 5 (Base) |
| **Safety Stock Breaches** | Weeks inventory fell below safety buffer | < 15 (Base) |

**Scenario severity guide:**

| Scenario | Demand shock | Lead time | Policy | Represents |
|---|---|---|---|---|
| Base | None | 7–14 days | Min-Max | Normal ops |
| Conservative | +10%, 6 weeks | ~18 days avg | Min-Max | Mild disruption |
| Stress | +35%, 10 weeks | ~28 days avg | Min-Max | Major disruption |
| BlackSwan | +75%, 15 weeks | ~45 days avg | ROP | Extreme event |

---

## Guardrails & Known Limitations

- **Weekly granularity only.** Daily demand variation is not modelled.
- **Single-echelon.** No supplier tiers; lead time is a direct draw from a distribution.
- **Demand shocks are step functions.** Gradual ramp-up/down is not yet supported.
- **No substitution logic.** Stockouts are lost sales (or backorders), not re-routed.
- **Seeds determine reproducibility.** Always log seeds. Same seed + same config = identical run.
- **GCS / Vertex require GCP credentials.** Set `GOOGLE_APPLICATION_CREDENTIALS` or use ADC.

---

## Adding a New Scenario

Edit `scenarios/catalog.yaml` — copy any existing block and adjust parameters.
No code changes required.

---

## Extending the SKU Set

In `batch_runner.py`, replace `_default_skus()` return value, or load from a CSV:

```python
import csv
from src.sim.inventory_types import SKUParams

def load_skus_from_csv(path: str):
    with open(path) as f:
        return [SKUParams(**row) for row in csv.DictReader(f)]
```

---

*Last updated: April 2026 — Project A, Milestone 4*
