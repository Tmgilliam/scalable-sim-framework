import csv
from pathlib import Path
from typing import List

from src.sim.inventory_types import SKUParams


def load_skus_csv(path: str | Path) -> List[SKUParams]:
    out: List[SKUParams] = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            out.append(
                SKUParams(
                    sku=row["sku"],
                    starting_on_hand=int(row["starting_on_hand"]),
                    weekly_demand=float(row["weekly_demand"]),
                    unit_cost=float(row["unit_cost"]),
                    lead_time_days=int(row["lead_time_days"]),
                    safety_stock=int(row["safety_stock"]),
                    initial_on_order=int(row.get("initial_on_order", 0) or 0),
                )
            )
    return out
