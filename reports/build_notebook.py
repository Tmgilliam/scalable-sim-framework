"""
Generates reports/exec_summary.ipynb from scratch using nbformat.
Run with: python reports/build_notebook.py
"""
import nbformat as nbf

nb = nbf.v4.new_notebook()
nb.metadata["kernelspec"] = {
    "display_name": "Python 3",
    "language": "python",
    "name": "python3",
}

cells = []

# ── Title ──────────────────────────────────────────────────────────────────
cells.append(nbf.v4.new_markdown_cell("""\
# Scalable Simulation Framework — Executive Summary
*Auto-generated from `runs/registry.csv`. Re-run all cells to refresh.*
"""))

# ── 1. Imports & load ──────────────────────────────────────────────────────
cells.append(nbf.v4.new_code_cell("""\
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import warnings, os
warnings.filterwarnings("ignore")

REGISTRY = os.path.join(os.path.dirname(os.getcwd()), "runs", "registry.csv") \\
           if os.path.basename(os.getcwd()) == "reports" \\
           else "runs/registry.csv"

df = pd.read_csv(REGISTRY)
df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"])
print(f"Loaded {len(df)} runs | Scenarios: {sorted(df.scenario.unique())}")
df.head()
"""))

# ── 2. KPI summary table ───────────────────────────────────────────────────
cells.append(nbf.v4.new_markdown_cell("## 1 · KPI Summary by Scenario"))
cells.append(nbf.v4.new_code_cell("""\
summary = (
    df.groupby("scenario")
    .agg(
        runs=("seed", "count"),
        fill_rate_mean=("fill_rate", "mean"),
        fill_rate_min=("fill_rate", "min"),
        backorders_mean=("backorder_units", "mean"),
        backorders_max=("backorder_units", "max"),
        stockout_periods_mean=("stockout_periods", "mean"),
        ss_breaches_mean=("safety_stock_breaches", "mean"),
    )
    .round({"fill_rate_mean": 4, "fill_rate_min": 4,
            "backorders_mean": 1, "backorders_max": 1,
            "stockout_periods_mean": 1, "ss_breaches_mean": 1})
    .rename(columns={
        "runs": "Runs",
        "fill_rate_mean": "Fill Rate (avg)",
        "fill_rate_min": "Fill Rate (worst)",
        "backorders_mean": "Backorders (avg)",
        "backorders_max": "Backorders (worst)",
        "stockout_periods_mean": "Stockout Weeks (avg)",
        "ss_breaches_mean": "SS Breaches (avg)",
    })
)

# Ordered by severity
order = ["Base", "Conservative", "Stress", "BlackSwan"]
summary = summary.reindex([s for s in order if s in summary.index])
summary
"""))

# ── 3. Fill rate chart ─────────────────────────────────────────────────────
cells.append(nbf.v4.new_markdown_cell("## 2 · Fill Rate Distribution by Scenario"))
cells.append(nbf.v4.new_code_cell("""\
order = [s for s in ["Base", "Conservative", "Stress", "BlackSwan"]
         if s in df.scenario.unique()]

fig, ax = plt.subplots(figsize=(9, 4))
colors = {"Base": "#2ecc71", "Conservative": "#3498db",
          "Stress": "#e67e22", "BlackSwan": "#e74c3c"}

for i, sc in enumerate(order):
    vals = df[df.scenario == sc]["fill_rate"]
    ax.scatter([i] * len(vals), vals, color=colors.get(sc, "grey"),
               s=90, zorder=3, label=sc)
    ax.plot([i - 0.2, i + 0.2], [vals.mean(), vals.mean()],
            color=colors.get(sc, "grey"), lw=2.5)

ax.axhline(1.0, color="grey", lw=0.8, ls="--", alpha=0.5)
ax.axhline(0.95, color="orange", lw=0.8, ls="--", alpha=0.6, label="95% threshold")
ax.set_xticks(range(len(order)))
ax.set_xticklabels(order)
ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1))
ax.set_ylabel("Fill Rate")
ax.set_title("Fill Rate by Scenario  (dots = seeds, bar = mean)")
ax.legend(loc="lower left")
ax.set_ylim(0, 1.05)
plt.tight_layout()
plt.savefig("fill_rate_by_scenario.png", dpi=150)
plt.show()
print("Saved: fill_rate_by_scenario.png")
"""))

# ── 4. Backorder chart ─────────────────────────────────────────────────────
cells.append(nbf.v4.new_markdown_cell("## 3 · Backorder Units by Scenario"))
cells.append(nbf.v4.new_code_cell("""\
fig, ax = plt.subplots(figsize=(9, 4))

means = [df[df.scenario == sc]["backorder_units"].mean() for sc in order]
bar_colors = [colors.get(sc, "grey") for sc in order]

bars = ax.bar(order, means, color=bar_colors, edgecolor="white", linewidth=0.8)
for bar, val in zip(bars, means):
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 50,
            f"{val:,.0f}", ha="center", va="bottom", fontsize=10)

ax.set_ylabel("Avg Backorder Units (52 weeks)")
ax.set_title("Average Backorder Units by Scenario")
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
plt.tight_layout()
plt.savefig("backorders_by_scenario.png", dpi=150)
plt.show()
print("Saved: backorders_by_scenario.png")
"""))

# ── 5. Stockout + SS breach heatmap ───────────────────────────────────────
cells.append(nbf.v4.new_markdown_cell("## 4 · Risk Heatmap — Stockout Weeks & Safety Stock Breaches"))
cells.append(nbf.v4.new_code_cell("""\
import numpy as np

heat_data = summary[["Stockout Weeks (avg)", "SS Breaches (avg)"]].values.astype(float)
fig, ax = plt.subplots(figsize=(6, 3.5))
im = ax.imshow(heat_data, cmap="YlOrRd", aspect="auto")

ax.set_xticks([0, 1])
ax.set_xticklabels(["Stockout Weeks", "SS Breaches"])
ax.set_yticks(range(len(summary)))
ax.set_yticklabels(summary.index)

for i in range(heat_data.shape[0]):
    for j in range(heat_data.shape[1]):
        ax.text(j, i, f"{heat_data[i, j]:.1f}",
                ha="center", va="center", fontsize=11,
                color="white" if heat_data[i, j] > heat_data.max() * 0.6 else "black")

plt.colorbar(im, ax=ax, label="Avg periods / breaches")
ax.set_title("Risk Heatmap (avg across seeds)")
plt.tight_layout()
plt.savefig("risk_heatmap.png", dpi=150)
plt.show()
print("Saved: risk_heatmap.png")
"""))

# ── 6. Raw registry ────────────────────────────────────────────────────────
cells.append(nbf.v4.new_markdown_cell("## 5 · Full Run Registry"))
cells.append(nbf.v4.new_code_cell("""\
cols = ["run_id", "scenario", "seed", "fill_rate",
        "backorder_units", "stockout_periods", "safety_stock_breaches"]
df[cols].sort_values(["scenario", "seed"]).reset_index(drop=True)
"""))

nb.cells = cells

out = "reports/exec_summary.ipynb"
with open(f"/home/claude/scalable-sim-framework/{out}", "w") as f:
    nbf.write(nb, f)
print(f"Written: {out}")
