import math
import random
from typing import Dict, List, Tuple

from src.sim.inventory_types import SKUParams, SKUResults, SKUState


def _periods_from_horizon(cfg: Dict) -> int:
    h = cfg["horizon"]
    if h["granularity"] != "weekly":
        raise NotImplementedError("Weekly only for now.")
    return int(h["periods"])


def _apply_demand_shock(cfg: Dict, base_weekly_demand: float, period_idx_1based: int) -> float:
    d = cfg["demand"]
    shock_pct = float(d["shock_pct"])
    start = int(d["shock_start_period"])
    dur = int(d["shock_duration_periods"])
    return base_weekly_demand * (1.0 + shock_pct) if start <= period_idx_1based < (start + dur) else base_weekly_demand


def _sample_lead_time_days(cfg: Dict, rng: random.Random) -> int:
    lt = cfg["lead_time"]
    if lt["mode"] == "range":
        lo, hi = lt["range_days"]
        return int(rng.randint(int(lo), int(hi)))

    if lt["mode"] == "distribution":
        dist = lt["distribution"]
        mean = float(dist["mean_days"])
        std = float(dist["std_days"])
        min_days = int(dist.get("min_days", 1))
        val = rng.gauss(mean, std)
        return max(min_days, int(round(val)))

    raise ValueError(f"Unknown lead_time mode: {lt['mode']}")


def simulate_inventory_weekly(cfg: Dict, skus: List[SKUParams]) -> Tuple[List[SKUResults], Dict]:
    periods = _periods_from_horizon(cfg)
    rng = random.Random(int(cfg["run"]["seed"]))

    # init state/results
    states: Dict[str, SKUState] = {}
    results: Dict[str, SKUResults] = {}

    for s in skus:
        st = SKUState(on_hand=int(s.starting_on_hand), on_order=[])
        if s.initial_on_order > 0:
            st.on_order.append({"qty": int(s.initial_on_order), "arrival_period": 1})
        states[s.sku] = st
        results[s.sku] = SKUResults(sku=s.sku, periods=periods)

    pol = cfg["reorder_policy"]
    policy = pol["policy"]

    # precompute policy params
    min_weeks = max_weeks = None
    review_weeks = None

    if policy == "minmax":
        min_dos = int(pol["minmax"]["min_days_of_supply"])
        max_dos = int(pol["minmax"]["max_days_of_supply"])
        min_weeks = max(1, math.ceil(min_dos / 7))
        max_weeks = max(1, math.ceil(max_dos / 7))

    elif policy == "rop":
        review_days = int(pol["rop"].get("review_period_days", 7))
        review_weeks = max(1, math.ceil(review_days / 7))

    else:
        raise NotImplementedError(f"Policy not supported yet: {policy}. Use minmax or rop.")

    # sim loop
    for t in range(1, periods + 1):
        for s in skus:
            st = states[s.sku]
            r = results[s.sku]

            # 1) receive arrivals
            arrivals = [o for o in st.on_order if int(o["arrival_period"]) == t]
            if arrivals:
                st.on_hand += sum(int(o["qty"]) for o in arrivals)
            st.on_order = [o for o in st.on_order if int(o["arrival_period"]) != t]

            # 2) demand
            demand = _apply_demand_shock(cfg, s.weekly_demand, t)
            r.demand_total += demand

            # 3) fulfill
            fulfilled = min(st.on_hand, int(round(demand)))
            st.on_hand -= fulfilled
            r.demand_fulfilled += fulfilled

            if fulfilled < demand:
                r.backorder_units += (demand - fulfilled)
                r.stockout_periods += 1

            # 4) safety stock breach
            if st.on_hand < s.safety_stock:
                r.safety_stock_breaches += 1

            # 5) reorder
            inv_pos = st.on_hand + sum(int(o["qty"]) for o in st.on_order)

            if policy == "minmax":
                target_level = int(round(max_weeks * s.weekly_demand))
                reorder_trigger = int(round(min_weeks * s.weekly_demand))

                if inv_pos <= reorder_trigger:
                    order_qty = max(0, target_level - inv_pos)
                    if order_qty > 0:
                        lt_days = _sample_lead_time_days(cfg, rng)
                        lt_weeks = max(1, math.ceil(lt_days / 7))
                        arrival_period = min(periods, t + lt_weeks)
                        st.on_order.append({"qty": int(order_qty), "arrival_period": int(arrival_period)})

            elif policy == "rop":
                # ROP = demand during lead time + safety stock
                lt_days = _sample_lead_time_days(cfg, rng)
                lt_weeks = max(1, math.ceil(lt_days / 7))

                rop_units = int(round((lt_weeks * s.weekly_demand) + s.safety_stock))
                order_up_to = int(round(((lt_weeks + review_weeks) * s.weekly_demand) + s.safety_stock))

                if inv_pos <= rop_units:
                    order_qty = max(0, order_up_to - inv_pos)
                    if order_qty > 0:
                        arrival_period = min(periods, t + lt_weeks)
                        st.on_order.append({"qty": int(order_qty), "arrival_period": int(arrival_period)})

    # aggregate KPIs
    agg = {
        "periods": periods,
        "demand_total": sum(r.demand_total for r in results.values()),
        "demand_fulfilled": sum(r.demand_fulfilled for r in results.values()),
        "backorder_units": sum(r.backorder_units for r in results.values()),
        "stockout_periods": sum(r.stockout_periods for r in results.values()),
        "safety_stock_breaches": sum(r.safety_stock_breaches for r in results.values()),
    }
    agg["fill_rate"] = (agg["demand_fulfilled"] / agg["demand_total"]) if agg["demand_total"] > 0 else 1.0

    return list(results.values()), agg