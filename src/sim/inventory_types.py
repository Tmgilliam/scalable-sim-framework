from dataclasses import dataclass, field
from typing import List


@dataclass
class SKUParams:
    sku: str
    weekly_demand: float
    starting_on_hand: int
    safety_stock: int
    initial_on_order: int = 0


@dataclass
class SKUState:
    on_hand: int
    on_order: List[dict] = field(default_factory=list)


@dataclass
class SKUResults:
    sku: str
    periods: int
    demand_total: float = 0.0
    demand_fulfilled: float = 0.0
    backorder_units: float = 0.0
    stockout_periods: int = 0
    safety_stock_breaches: int = 0
