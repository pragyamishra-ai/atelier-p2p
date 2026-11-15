"""Purchase orders and goods receipts: the clean 'truth' before errors are injected."""

import random
from datetime import date, timedelta

import pandas as pd

# Units of currency per 1 EUR. Fixed on purpose, so results are reproducible.
FX_PER_EUR = {"EUR": 1.0, "CHF": 0.94, "GBP": 0.85, "USD": 1.08}

START_DATE = date(2026, 1, 5)
ORDER_SPAN_DAYS = 180


def _quantity(rng: random.Random, unit: str) -> int:
    if unit == "EA":
        return rng.randrange(100, 5001, 100)
    return rng.randint(10, 200)  # M, M2


def make_purchase_orders(
    vendors: pd.DataFrame, materials: pd.DataFrame, seed: int, n_pos: int = 200
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (po_headers, po_lines)."""
    rng = random.Random(seed + 2)
    vendor_rows = vendors.to_dict("records")
    by_category = {cat: grp.to_dict("records") for cat, grp in materials.groupby("category")}

    headers, lines = [], []
    for i in range(n_pos):
        vendor = rng.choice(vendor_rows)
        po_number = str(4500000000 + i)
        order_date = START_DATE + timedelta(days=rng.randint(0, ORDER_SPAN_DAYS))
        fx = FX_PER_EUR[vendor["currency"]]
        picks = rng.sample(by_category[vendor["category"]], rng.randint(1, 5))

        total = 0.0
        for j, mat in enumerate(picks, start=1):
            qty = _quantity(rng, mat["unit"])
            unit_price = round(mat["std_price_eur"] * fx * rng.uniform(0.92, 1.08), 2)
            net_value = round(qty * unit_price, 2)
            total += net_value
            lines.append(
                {
                    "po_number": po_number,
                    "line": j * 10,
                    "material_id": mat["material_id"],
                    "description": mat["description"],
                    "quantity": qty,
                    "unit": mat["unit"],
                    "unit_price": unit_price,
                    "net_value": net_value,
                    "delivery_date": order_date + timedelta(days=rng.randint(14, 45)),
                }
            )
        headers.append(
            {
                "po_number": po_number,
                "vendor_id": vendor["vendor_id"],
                "order_date": order_date,
                "currency": vendor["currency"],
                "payment_terms": vendor["payment_terms"],
                "net_total": round(total, 2),
            }
        )
    return pd.DataFrame(headers), pd.DataFrame(lines)


def make_goods_receipts(
    po_lines: pd.DataFrame, seed: int, split_rate: float = 0.12
) -> pd.DataFrame:
    """One receipt per PO line; about split_rate of lines arrive in two partial receipts."""
    rng = random.Random(seed + 3)
    rows = []

    def add(line: dict, qty: int, gr_date: date) -> None:
        rows.append(
            {
                "gr_number": str(5000000000 + len(rows)),
                "po_number": line["po_number"],
                "line": line["line"],
                "material_id": line["material_id"],
                "quantity": qty,
                "unit": line["unit"],
                "gr_date": gr_date,
            }
        )

    for line in po_lines.to_dict("records"):
        qty = int(line["quantity"])
        first_date = line["delivery_date"] + timedelta(days=rng.randint(-3, 7))
        if qty >= 2 and rng.random() < split_rate:
            first_qty = max(1, min(qty - 1, round(qty * rng.uniform(0.3, 0.7))))
            add(line, first_qty, first_date)
            add(line, qty - first_qty, first_date + timedelta(days=rng.randint(3, 14)))
        else:
            add(line, qty, first_date)
    return pd.DataFrame(rows)
