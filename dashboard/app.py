"""Streamlit dashboard — operations-leadership view of the simulation framework.

Four panels:
    1. Scenario Configuration — preset loader + custom parameter form
       + validation messages + Run button.
    2. Results Summary — metric cards with p10/p50/p90 ranges and a
       plain-English interpretation.
    3. Scenario Comparison — up to three results side-by-side; the
       scenario meeting the service-level target at the lowest
       average inventory is flagged automatically.
    4. Stress Test Visualization — Plotly chart of inventory position
       over time for a sample run, with stockouts shaded and reorder
       events marked.

Run with:  streamlit run dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

# Allow `streamlit run dashboard/app.py` to find the simulation package
# whether invoked from the project root or elsewhere.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from simulation import (  # noqa: E402
    MonteCarloEngine,
    ScenarioConfig,
    list_scenarios,
    run_scenario,
)
from simulation.config import DemandShock, LeadTimeShock  # noqa: E402
from simulation.scenarios import ScenarioResult, _interpret  # noqa: E402


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------


st.set_page_config(
    page_title="Inventory Stress Testing Framework",
    layout="wide",
    initial_sidebar_state="expanded",
)


if "results" not in st.session_state:
    st.session_state.results: Dict[str, ScenarioResult] = {}


# ---------------------------------------------------------------------------
# Panel 1 — Scenario Configuration
# ---------------------------------------------------------------------------


def _panel_configuration() -> None:
    st.header("1. Scenario Configuration")
    st.caption(
        "Configure a single simulation run. Pick a pre-built scenario as a "
        "starting point, then tune parameters. Validation runs before any "
        "Monte Carlo work begins."
    )

    col_preset, col_runs = st.columns([2, 1])

    with col_preset:
        preset = st.selectbox(
            "Preset scenario",
            options=["custom"] + list_scenarios(),
            index=1,
            help="Load a pre-built scenario, or start from a blank template.",
        )

    with col_runs:
        num_runs = st.number_input(
            "Monte Carlo runs",
            min_value=10,
            max_value=2000,
            value=200,
            step=10,
            help="More runs = tighter confidence intervals, longer wall clock.",
        )
        simulation_days = st.number_input(
            "Simulation horizon (days)",
            min_value=30,
            max_value=730,
            value=180,
            step=30,
        )

    # Generate default parameter values from the chosen preset
    default_cfg = _default_config_for_preset(preset, int(num_runs), int(simulation_days))

    st.subheader("Inventory & policy parameters")
    c1, c2, c3 = st.columns(3)
    with c1:
        initial_inventory = st.number_input("Starting on-hand inventory", min_value=0, value=default_cfg.initial_inventory)
        reorder_point = st.number_input("Reorder point (units)", min_value=1, value=default_cfg.reorder_point)
        reorder_qty = st.number_input("Reorder quantity (units)", min_value=1, value=default_cfg.reorder_qty)
    with c2:
        demand_mean = st.number_input("Mean daily demand (units/day)", min_value=0.1, value=float(default_cfg.demand_mean))
        demand_std = st.number_input("Demand std dev", min_value=0.0, value=float(default_cfg.demand_std))
        service_level_target = st.slider(
            "Service level target",
            min_value=0.80,
            max_value=0.99,
            value=float(default_cfg.service_level_target),
            step=0.01,
        )
    with c3:
        lead_time_mean = st.number_input("Mean lead time (days)", min_value=0.5, value=float(default_cfg.lead_time_mean))
        lead_time_std = st.number_input("Lead time std dev", min_value=0.0, value=float(default_cfg.lead_time_std))
        seed = st.number_input("RNG seed", min_value=0, value=int(default_cfg.seed))

    st.subheader("Stress windows (optional)")
    cs1, cs2 = st.columns(2)
    with cs1:
        enable_demand_shock = st.checkbox("Inject demand shock", value=default_cfg.demand_shock is not None)
        if enable_demand_shock:
            d = default_cfg.demand_shock or DemandShock(start_day=60, duration_days=30, multiplier=2.0)
            ds_start = st.number_input("Demand shock start day", min_value=1, value=int(d.start_day))
            ds_duration = st.number_input("Demand shock duration (days)", min_value=1, value=int(d.duration_days))
            ds_mult = st.number_input("Demand multiplier", min_value=0.1, value=float(d.multiplier))
        else:
            ds_start = ds_duration = None  # type: ignore[assignment]
            ds_mult = None  # type: ignore[assignment]

    with cs2:
        enable_lt_shock = st.checkbox("Inject lead-time shock", value=default_cfg.lead_time_shock is not None)
        if enable_lt_shock:
            lts = default_cfg.lead_time_shock or LeadTimeShock(start_day=45, duration_days=45, multiplier=2.0)
            lt_start = st.number_input("Lead-time shock start day", min_value=1, value=int(lts.start_day))
            lt_duration = st.number_input("Lead-time shock duration (days)", min_value=1, value=int(lts.duration_days))
            lt_mult = st.number_input("Lead-time multiplier", min_value=0.1, value=float(lts.multiplier))
        else:
            lt_start = lt_duration = None  # type: ignore[assignment]
            lt_mult = None  # type: ignore[assignment]

    scenario_label = st.text_input(
        "Save result as (label for comparison panel)",
        value=preset if preset != "custom" else "custom_run",
    )

    if st.button("Run Simulation", type="primary"):
        try:
            cfg_kwargs: Dict = dict(
                name=scenario_label,
                description=f"Dashboard run derived from preset '{preset}'.",
                initial_inventory=int(initial_inventory),
                demand_mean=float(demand_mean),
                demand_std=float(demand_std),
                lead_time_mean=float(lead_time_mean),
                lead_time_std=float(lead_time_std),
                reorder_point=int(reorder_point),
                reorder_qty=int(reorder_qty),
                service_level_target=float(service_level_target),
                simulation_days=int(simulation_days),
                num_runs=int(num_runs),
                seed=int(seed),
            )
            if enable_demand_shock:
                cfg_kwargs["demand_shock"] = DemandShock(
                    start_day=int(ds_start),
                    duration_days=int(ds_duration),
                    multiplier=float(ds_mult),
                )
            if enable_lt_shock:
                cfg_kwargs["lead_time_shock"] = LeadTimeShock(
                    start_day=int(lt_start),
                    duration_days=int(lt_duration),
                    multiplier=float(lt_mult),
                )

            cfg = ScenarioConfig(**cfg_kwargs)
        except ValidationError as exc:
            st.error("Scenario configuration failed validation:\n\n" + _format_validation_errors(exc))
            return

        with st.spinner(f"Running {num_runs} Monte Carlo replications..."):
            summary = MonteCarloEngine(cfg).run()
            narrative = _interpret(scenario_label, cfg, summary)
            result = ScenarioResult(
                scenario_name=scenario_label,
                config=cfg,
                summary=summary,
                narrative=narrative,
            )
            st.session_state.results[scenario_label] = result
        st.success(f"Saved result as '{scenario_label}'. See panel 2 below.")


def _default_config_for_preset(preset: str, num_runs: int, simulation_days: int) -> ScenarioConfig:
    """Load the preset (with the chosen run count) WITHOUT actually executing it.

    We need the parameter defaults to populate the form. We do not want
    to pay the Monte Carlo cost just to render the form.
    """
    from simulation.scenarios import _baseline_config

    base = _baseline_config().with_overrides(num_runs=num_runs, simulation_days=simulation_days)

    if preset in ("custom", "baseline"):
        return base
    if preset == "demand_shock":
        return base.with_overrides(
            name="demand_shock",
            demand_shock=DemandShock(start_day=60, duration_days=30, multiplier=2.0).model_dump(),
        )
    if preset == "lead_time_crisis":
        return base.with_overrides(
            name="lead_time_crisis",
            lead_time_shock=LeadTimeShock(start_day=45, duration_days=45, multiplier=2.0).model_dump(),
        )
    if preset == "combined_stress":
        return base.with_overrides(
            name="combined_stress",
            demand_shock=DemandShock(start_day=60, duration_days=30, multiplier=1.8).model_dump(),
            lead_time_shock=LeadTimeShock(start_day=60, duration_days=30, multiplier=1.8).model_dump(),
        )
    if preset == "service_level_sensitivity":
        return base.with_overrides(name="service_level_sensitivity", service_level_target=0.95)
    return base


def _format_validation_errors(exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        loc = " -> ".join(str(p) for p in err["loc"])
        lines.append(f"- {loc}: {err['msg']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Panel 2 — Results Summary
# ---------------------------------------------------------------------------


def _panel_results() -> None:
    st.header("2. Results Summary")
    if not st.session_state.results:
        st.info("Run a scenario from Panel 1 to populate this panel.")
        return

    label = st.selectbox(
        "Scenario to display",
        options=list(st.session_state.results.keys()),
        index=len(st.session_state.results) - 1,
    )
    result: ScenarioResult = st.session_state.results[label]
    metrics = result.summary.metrics
    target = result.config.service_level_target

    c1, c2, c3, c4 = st.columns(4)
    _metric_card(c1, "Fill rate (median)", metrics["fill_rate"]["p50"], "{:.1%}",
                 p10=metrics["fill_rate"]["p10"], p90=metrics["fill_rate"]["p90"], fmt="{:.1%}")
    _metric_card(c2, "Stockout days (median)", metrics["stockout_days"]["p50"], "{:.0f}",
                 p10=metrics["stockout_days"]["p10"], p90=metrics["stockout_days"]["p90"], fmt="{:.0f}")
    _metric_card(c3, "Avg inventory (median)", metrics["avg_inventory"]["p50"], "{:.0f}",
                 p10=metrics["avg_inventory"]["p10"], p90=metrics["avg_inventory"]["p90"], fmt="{:.0f}")
    service_p50 = metrics["service_level_achieved"]["p50"]
    delta = service_p50 - target
    c4.metric(
        "Service level (median)",
        f"{service_p50:.1%}",
        delta=f"{delta:+.1%} vs target",
        delta_color="normal" if delta >= 0 else "inverse",
    )

    st.subheader("What this means")
    st.write(result.narrative)


def _metric_card(col, label: str, value: float, _value_fmt: str, *, p10: float, p90: float, fmt: str) -> None:
    col.metric(label, fmt.format(value))
    col.caption(f"p10 / p90 range: {fmt.format(p10)}  →  {fmt.format(p90)}")


# ---------------------------------------------------------------------------
# Panel 3 — Scenario Comparison
# ---------------------------------------------------------------------------


def _panel_comparison() -> None:
    st.header("3. Scenario Comparison")
    if len(st.session_state.results) < 2:
        st.info("Save at least two scenario results (Panel 1) to compare them.")
        return

    selected = st.multiselect(
        "Pick up to 3 scenarios to compare",
        options=list(st.session_state.results.keys()),
        default=list(st.session_state.results.keys())[: min(3, len(st.session_state.results))],
        max_selections=3,
    )
    if not selected:
        return

    results = [st.session_state.results[s] for s in selected]

    rows = []
    for r in results:
        m = r.summary.metrics
        rows.append({
            "Scenario": r.scenario_name,
            "Service-level target": f"{r.config.service_level_target:.0%}",
            "Fill rate p50": f"{m['fill_rate']['p50']:.1%}",
            "Fill rate p10": f"{m['fill_rate']['p10']:.1%}",
            "Stockout days p50": f"{m['stockout_days']['p50']:.0f}",
            "Stockout days p90": f"{m['stockout_days']['p90']:.0f}",
            "Avg inventory p50": f"{m['avg_inventory']['p50']:.0f}",
            "Achieved SL p50": f"{m['service_level_achieved']['p50']:.1%}",
            "Meets target?": "Yes" if m["service_level_achieved"]["p50"] >= r.config.service_level_target else "No",
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)

    winner = _pick_winner(results)
    if winner is not None:
        st.success(
            f"Recommended: **{winner.scenario_name}** — meets its "
            f"{winner.config.service_level_target:.0%} service-level target "
            f"at the lowest median average inventory "
            f"({winner.summary.metrics['avg_inventory']['p50']:.0f} units)."
        )
    else:
        st.warning(
            "None of the selected scenarios meet their service-level target at the median. "
            "Tighten the reorder point or increase reorder quantity and re-run."
        )


def _pick_winner(results: List[ScenarioResult]) -> Optional[ScenarioResult]:
    qualifying = [
        r
        for r in results
        if r.summary.metrics["service_level_achieved"]["p50"] >= r.config.service_level_target
    ]
    if not qualifying:
        return None
    return min(qualifying, key=lambda r: r.summary.metrics["avg_inventory"]["p50"])


# ---------------------------------------------------------------------------
# Panel 4 — Stress Test Visualization
# ---------------------------------------------------------------------------


def _panel_visualization() -> None:
    st.header("4. Stress Test Visualization")
    if not st.session_state.results:
        st.info("Run a scenario to populate this panel.")
        return

    label = st.selectbox(
        "Scenario to visualize",
        options=list(st.session_state.results.keys()),
        index=len(st.session_state.results) - 1,
        key="viz_select",
    )
    result: ScenarioResult = st.session_state.results[label]
    trace = result.summary.sample_trace
    if trace is None:
        st.warning("No sample trace was captured for this run.")
        return

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=trace.day, y=trace.on_hand, mode="lines", name="On-hand inventory",
        line=dict(color="#1f77b4", width=2),
    ))
    fig.add_trace(go.Scatter(
        x=trace.day, y=trace.on_order, mode="lines", name="On-order pipeline",
        line=dict(color="#7f7f7f", width=1, dash="dot"),
    ))
    fig.add_hline(
        y=result.config.reorder_point,
        line_dash="dash",
        line_color="#d62728",
        annotation_text=f"Reorder point ({result.config.reorder_point})",
        annotation_position="bottom right",
    )

    stockout_days = [d for d, flag in zip(trace.day, trace.stockout_flag) if flag]
    for d in stockout_days:
        fig.add_vrect(x0=d - 0.5, x1=d + 0.5, fillcolor="#d62728", opacity=0.10, line_width=0)

    reorder_days = [d for d, flag in zip(trace.day, trace.reorder_events) if flag]
    if reorder_days:
        fig.add_trace(go.Scatter(
            x=reorder_days,
            y=[result.config.reorder_point for _ in reorder_days],
            mode="markers",
            name="Reorder placed",
            marker=dict(symbol="triangle-up", size=10, color="#2ca02c"),
        ))

    fig.update_layout(
        title=f"Inventory position over time — {label} (run 1 of {result.summary.num_runs})",
        xaxis_title="Day",
        yaxis_title="Units",
        height=480,
        margin=dict(l=40, r=20, t=60, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Demand vs. fulfilled")
    fig2 = go.Figure()
    fig2.add_trace(go.Bar(x=trace.day, y=trace.demand, name="Demand", marker_color="#1f77b4"))
    fig2.add_trace(go.Bar(x=trace.day, y=trace.fulfilled, name="Fulfilled", marker_color="#2ca02c"))
    fig2.update_layout(
        barmode="overlay",
        title="Demand vs. fulfilled (red shading = stockout days)",
        xaxis_title="Day",
        yaxis_title="Units",
        height=320,
        margin=dict(l=40, r=20, t=50, b=40),
    )
    for d in stockout_days:
        fig2.add_vrect(x0=d - 0.5, x1=d + 0.5, fillcolor="#d62728", opacity=0.15, line_width=0)
    st.plotly_chart(fig2, use_container_width=True)


# ---------------------------------------------------------------------------
# Sidebar — quick-fill from the preset library
# ---------------------------------------------------------------------------


def _sidebar() -> None:
    st.sidebar.title("Quick fill")
    st.sidebar.caption(
        "Run every pre-built scenario in one click. Each run uses 100 Monte "
        "Carlo replications and a 120-day horizon — fast enough to populate "
        "the comparison panel in seconds."
    )
    if st.sidebar.button("Run all pre-built scenarios"):
        with st.spinner("Running pre-built scenario library..."):
            for name in list_scenarios():
                if name == "service_level_sensitivity":
                    continue
                result = run_scenario(name, num_runs=100, simulation_days=120)
                st.session_state.results[name] = result
        st.sidebar.success(f"Populated {len(st.session_state.results)} scenarios.")

    if st.session_state.results:
        st.sidebar.subheader("Saved results")
        for name in list(st.session_state.results.keys()):
            cols = st.sidebar.columns([3, 1])
            cols[0].write(name)
            if cols[1].button("X", key=f"del_{name}"):
                del st.session_state.results[name]
                st.rerun()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    st.title("Inventory Stress Testing Framework")
    st.write(
        "Test inventory policy decisions in a safe sandbox before committing "
        "them to production. Designed for operations leadership, powered by "
        "a Monte Carlo simulation engine that runs locally or on Vertex AI."
    )
    _sidebar()
    _panel_configuration()
    st.divider()
    _panel_results()
    st.divider()
    _panel_comparison()
    st.divider()
    _panel_visualization()


main()
