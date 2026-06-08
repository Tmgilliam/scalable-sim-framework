from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class SKUParams:
    sku: str
    starting_on_hand: int
    weekly_demand: float
    unit_cost: float
    lead_time_days: int
    safety_stock: int
    initial_on_order: int = 0


@dataclass
class SKUState:
    on_hand: int
    on_order: List[Dict] = field(default_factory=list)


@dataclass
class SKUResults:
    sku: str
    periods: int
    demand_total: float = 0.0
    demand_fulfilled: float = 0.0
    backorder_units: float = 0.0
    stockout_periods: int = 0
    safety_stock_breaches: int = 0

    def fill_rate(self) -> float:
        return 1.0 if self.demand_total <= 0 else (self.demand_fulfilled / self.demand_total)
