"""Error injection: break a share of the clean invoices on purpose and record every error.

POs, goods receipts and vendors stay clean (they are the SAP truth). Only the invoice tables
change, and error_manifest.csv says which invoice has which error. Each invoice gets at most
one error, so scoring stays unambiguous.
"""

import random
import re
from dataclasses import dataclass
from datetime import timedelta

import pandas as pd

# Share of the clean invoices that get each error type.
ERROR_SHARES = {
    "duplicate_invoice": 0.03,
    "price_variance": 0.04,
    "quantity_mismatch": 0.04,
    "line_sum_mismatch": 0.02,
    "po_reference": 0.03,
    "vat_currency": 0.02,
    "invoice_before_gr": 0.02,
}

WRONG_VAT_RATES = [0.0, 0.10, 0.19, 0.20, 0.22]
CURRENCIES = ["EUR", "USD", "GBP", "CHF"]

MANIFEST_COLUMNS = [
    "error_id",
    "invoice_id",
    "pdf_file",
    "error_type",
    "subtype",
    "field",
    "line",
    "true_value",
    "invoice_value",
    "related_invoice_id",
    "expected_finding",
]


@dataclass
class _Ctx:
    po_head: dict  # po_number -> PO header fields
    first_gr: dict  # po_number -> date of the first goods receipt


def _terms_days(terms: str) -> int:
    match = re.search(r"NET(\d+)", terms)
    return int(match.group(1)) if match else 30


def _refresh_vat(header: dict) -> None:
    header["vat_amount"] = round(header["net_total"] * header["vat_rate"], 2)
    header["gross_total"] = round(header["net_total"] + header["vat_amount"], 2)


def _refresh_totals(header: dict, rows: list[dict]) -> None:
    header["net_total"] = round(sum(r["net_value"] for r in rows), 2)
    _refresh_vat(header)


def _price_variance(rng: random.Random, h: dict, rows: list[dict], i: int, ctx: _Ctx) -> dict:
    row = rng.choice(rows)
    under = i % 4 == 3
    old = row["unit_price"]
    factor = 1 - rng.uniform(0.06, 0.20) if under else 1 + rng.uniform(0.06, 0.30)
    row["unit_price"] = round(old * factor, 2)
    row["net_value"] = round(row["quantity"] * row["unit_price"], 2)
    _refresh_totals(h, rows)
    pct = (row["unit_price"] / old - 1) * 100
    return {
        "subtype": "under" if under else "over",
        "field": "unit_price",
        "line": row["po_line"],
        "true": old,
        "seen": row["unit_price"],
        "finding": (
            f"Line {row['po_line']}: unit price {row['unit_price']} vs PO {old} ({pct:+.1f}%)"
        ),
    }


def _quantity_mismatch(rng: random.Random, h: dict, rows: list[dict], i: int, ctx: _Ctx) -> dict:
    row = rng.choice(rows)
    old = row["quantity"]
    under = i % 4 == 3 and old >= 2
    if under:
        new = min(old - 1, max(1, round(old * rng.uniform(0.5, 0.95))))
    else:
        new = old + max(1, round(old * rng.uniform(0.05, 0.30)))
    row["quantity"] = new
    row["net_value"] = round(new * row["unit_price"], 2)
    _refresh_totals(h, rows)
    return {
        "subtype": "under" if under else "over",
        "field": "quantity",
        "line": row["po_line"],
        "true": old,
        "seen": new,
        "finding": f"Line {row['po_line']}: invoiced {new} vs received {old}",
    }


def _line_sum_mismatch(rng: random.Random, h: dict, rows: list[dict], i: int, ctx: _Ctx) -> dict:
    sign = rng.choice([-1, 1])
    if i % 2 == 0:
        old = h["net_total"]
        h["net_total"] = round(old * (1 + sign * rng.uniform(0.02, 0.10)), 2)
        _refresh_vat(h)
        return {
            "subtype": "total_off",
            "field": "net_total",
            "line": "",
            "true": old,
            "seen": h["net_total"],
            "finding": f"Net total {h['net_total']} does not equal the sum of the lines ({old})",
        }
    row = rng.choice(rows)
    old = row["net_value"]
    row["net_value"] = round(old * (1 + sign * rng.uniform(0.03, 0.12)), 2)
    return {
        "subtype": "line_amount_off",
        "field": "net_value",
        "line": row["po_line"],
        "true": old,
        "seen": row["net_value"],
        "finding": f"Line {row['po_line']}: amount {row['net_value']} is not qty x price ({old})",
    }


def _po_reference(rng: random.Random, h: dict, rows: list[dict], i: int, ctx: _Ctx) -> dict:
    true = h["po_number"]
    subtype = ["missing", "nonexistent", "other_vendor"][i % 3]
    if subtype == "missing":
        seen = ""
        finding = f"No PO reference on the invoice (expected {true})"
    elif subtype == "nonexistent":
        seen = str(int(true) + rng.randint(300, 900))
        while seen in ctx.po_head:
            seen = str(int(seen) + 1)
        finding = f"PO {seen} does not exist (expected {true})"
    else:
        others = sorted(p for p, v in ctx.po_head.items() if v["vendor_id"] != h["vendor_id"])
        seen = rng.choice(others)
        finding = f"PO {seen} belongs to another vendor (expected {true})"
    h["po_number"] = seen
    return {
        "subtype": subtype,
        "field": "po_number",
        "line": "",
        "true": true,
        "seen": seen,
        "finding": finding,
    }


def _vat_currency(rng: random.Random, h: dict, rows: list[dict], i: int, ctx: _Ctx) -> dict:
    if i % 2 == 0:
        old = h["vat_rate"]
        h["vat_rate"] = rng.choice([r for r in WRONG_VAT_RATES if r != old])
        _refresh_vat(h)
        return {
            "subtype": "wrong_vat",
            "field": "vat_rate",
            "line": "",
            "true": old,
            "seen": h["vat_rate"],
            "finding": f"VAT rate {h['vat_rate']:.1%} charged, expected {old:.1%} for the vendor",
        }
    old = h["currency"]
    h["currency"] = rng.choice([c for c in CURRENCIES if c != old])
    return {
        "subtype": "wrong_currency",
        "field": "currency",
        "line": "",
        "true": old,
        "seen": h["currency"],
        "finding": f"Invoice currency {h['currency']} differs from PO currency {old}",
    }


def _invoice_before_gr(rng: random.Random, h: dict, rows: list[dict], i: int, ctx: _Ctx) -> dict:
    old = h["invoice_date"]
    first = ctx.first_gr[h["po_number"]]
    earliest = ctx.po_head[h["po_number"]]["order_date"] + timedelta(days=1)
    h["invoice_date"] = max(earliest, first - timedelta(days=rng.randint(2, 15)))
    h["due_date"] = h["invoice_date"] + timedelta(days=_terms_days(h["payment_terms"]))
    return {
        "subtype": "",
        "field": "invoice_date",
        "line": "",
        "true": old.isoformat(),
        "seen": h["invoice_date"].isoformat(),
        "finding": (
            f"Invoice dated {h['invoice_date'].isoformat()} is before the first "
            f"goods receipt on {first.isoformat()}"
        ),
    }


def _duplicate(
    rng: random.Random, h: dict, rows: list[dict], i: int, new_id: str
) -> tuple[dict, list[dict], dict]:
    """Return (copy header, copy lines, manifest info). The original stays untouched."""
    subtype = ["exact_copy", "reformatted_number", "renumbered"][i % 3]
    copy = dict(h, invoice_id=new_id, pdf_file=f"{new_id}.pdf")
    year, num = h["invoice_number"].split("/")
    if subtype != "exact_copy":
        shift = timedelta(days=rng.randint(3, 20))
        copy["invoice_date"] = h["invoice_date"] + shift
        copy["due_date"] = h["due_date"] + shift
    if subtype == "reformatted_number":
        copy["invoice_number"] = f"{year}-{num}"
        finding = f"Same vendor, PO and amount as {h['invoice_id']}; number only reformatted"
    elif subtype == "renumbered":
        copy["invoice_number"] = f"{year}/{int(num) + rng.randint(1000, 1999):05d}"
        finding = f"Same vendor, PO and amount as {h['invoice_id']} under a new number"
    else:
        finding = f"Same vendor and invoice number as {h['invoice_id']}"
    copy_rows = [dict(r, invoice_id=new_id) for r in rows]
    field = "gross_total" if subtype == "renumbered" else "invoice_number"
    info = {
        "subtype": subtype,
        "field": field,
        "line": "",
        "true": h[field],
        "seen": copy[field],
        "finding": finding,
    }
    return copy, copy_rows, info


_INJECTORS = {
    "price_variance": _price_variance,
    "quantity_mismatch": _quantity_mismatch,
    "line_sum_mismatch": _line_sum_mismatch,
    "po_reference": _po_reference,
    "vat_currency": _vat_currency,
    "invoice_before_gr": _invoice_before_gr,
}


def inject_errors(
    po_headers: pd.DataFrame,
    receipts: pd.DataFrame,
    invoices: pd.DataFrame,
    invoice_lines: pd.DataFrame,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (invoices, invoice_lines, error_manifest) with the errors applied."""
    rng = random.Random(seed + 5)
    ctx = _Ctx(
        po_head=po_headers.set_index("po_number").to_dict("index"),
        first_gr=receipts.groupby("po_number")["gr_date"].min().to_dict(),
    )
    headers = invoices.to_dict("records")
    items = {k: g.to_dict("records") for k, g in invoice_lines.groupby("invoice_id")}
    n = len(headers)

    # Disjoint targets: shuffle once, then hand out slices, one slice per error type.
    order = list(range(n))
    rng.shuffle(order)
    picks, start = {}, 0
    for kind, share in ERROR_SHARES.items():
        count = max(1, round(share * n))
        picks[kind] = [headers[j] for j in order[start : start + count]]
        start += count
    if start > n:
        raise ValueError("Error shares add up to more than the number of invoices")

    manifest: list[dict] = []
    new_headers: list[dict] = []

    def log(h: dict, kind: str, info: dict, related: str = "") -> None:
        manifest.append(
            {
                "invoice_id": h["invoice_id"],
                "pdf_file": h["pdf_file"],
                "error_type": kind,
                "subtype": info["subtype"],
                "field": info["field"],
                "line": str(info["line"]),
                "true_value": str(info["true"]),
                "invoice_value": str(info["seen"]),
                "related_invoice_id": related,
                "expected_finding": info["finding"],
            }
        )

    for i, h in enumerate(picks["duplicate_invoice"]):
        new_id = f"INV{n + i + 1:06d}"
        copy, copy_rows, info = _duplicate(rng, h, items[h["invoice_id"]], i, new_id)
        items[new_id] = copy_rows
        new_headers.append(copy)
        log(copy, "duplicate_invoice", info, related=h["invoice_id"])

    for kind, injector in _INJECTORS.items():
        for i, h in enumerate(picks[kind]):
            log(h, kind, injector(rng, h, items[h["invoice_id"]], i, ctx))

    all_headers = headers + new_headers
    out_invoices = pd.DataFrame(all_headers, columns=invoices.columns)
    out_lines = pd.DataFrame(
        [row for h in all_headers for row in items[h["invoice_id"]]],
        columns=invoice_lines.columns,
    )
    out_manifest = pd.DataFrame(manifest).sort_values("invoice_id", ignore_index=True)
    out_manifest.insert(0, "error_id", [f"ERR{k:03d}" for k in range(1, len(out_manifest) + 1)])
    out_manifest["related_invoice_id"] = out_manifest["related_invoice_id"].fillna("")
    return out_invoices, out_lines, out_manifest[MANIFEST_COLUMNS]
