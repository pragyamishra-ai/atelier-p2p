from types import SimpleNamespace

import pytest

from p2p.data_gen.errors import ERROR_SHARES, inject_errors
from p2p.data_gen.invoices import DEFAULT_VAT, VAT_RATES, make_invoices, render_invoice_pdf
from p2p.data_gen.master_data import make_materials, make_vendors
from p2p.data_gen.transactions import make_goods_receipts, make_purchase_orders

# Which independent check should trip for each error type.
CHECK_FOR = {
    "duplicate_invoice": "duplicate",
    "price_variance": "price",
    "quantity_mismatch": "quantity",
    "line_sum_mismatch": "line_sum",
    "po_reference": "po_ref",
    "invoice_before_gr": "date",
}


def build(seed: int = 42) -> SimpleNamespace:
    vendors = make_vendors(seed)
    materials = make_materials(seed)
    po_headers, po_lines = make_purchase_orders(vendors, materials, seed)
    receipts = make_goods_receipts(po_lines, seed)
    clean, clean_lines = make_invoices(vendors, po_headers, po_lines, receipts, seed)
    invoices, lines, manifest = inject_errors(po_headers, receipts, clean, clean_lines, seed)
    return SimpleNamespace(
        vendors=vendors,
        po_headers=po_headers,
        po_lines=po_lines,
        receipts=receipts,
        clean=clean,
        invoices=invoices,
        lines=lines,
        manifest=manifest,
    )


@pytest.fixture(scope="module")
def world() -> SimpleNamespace:
    return build()


def expected_check(row: dict) -> str:
    if row["error_type"] == "vat_currency":
        return "vat" if row["subtype"] == "wrong_vat" else "currency"
    return CHECK_FOR[row["error_type"]]


def detect(w: SimpleNamespace) -> dict[str, set[str]]:
    """Independent rule checks, written without looking at the manifest."""
    vendor_country = w.vendors.set_index("vendor_id")["country"].to_dict()
    po_head = w.po_headers.set_index("po_number").to_dict("index")
    po_price = w.po_lines.set_index(["po_number", "line"])["unit_price"].to_dict()
    received = w.receipts.groupby(["po_number", "line"])["quantity"].sum().to_dict()
    last_gr = w.receipts.groupby("po_number")["gr_date"].max().to_dict()
    lines_by_invoice = {k: g.to_dict("records") for k, g in w.lines.groupby("invoice_id")}

    found: dict[str, set[str]] = {}

    def flag(invoice_id: str, check: str) -> None:
        found.setdefault(invoice_id, set()).add(check)

    for h in w.invoices.to_dict("records"):
        iid = h["invoice_id"]
        rows = lines_by_invoice[iid]
        if abs(sum(r["net_value"] for r in rows) - h["net_total"]) > 0.01:
            flag(iid, "line_sum")
        if h["vat_rate"] != VAT_RATES.get(vendor_country[h["vendor_id"]], DEFAULT_VAT):
            flag(iid, "vat")
        po = h["po_number"]
        if not po or po not in po_head or po_head[po]["vendor_id"] != h["vendor_id"]:
            flag(iid, "po_ref")
            continue
        if h["currency"] != po_head[po]["currency"]:
            flag(iid, "currency")
        if h["invoice_date"] <= last_gr[po]:
            flag(iid, "date")
        for r in rows:
            key = (po, r["po_line"])
            if r["unit_price"] != po_price[key]:
                flag(iid, "price")
            if r["quantity"] != received[key]:
                flag(iid, "quantity")

    ordered = w.invoices.sort_values("invoice_id")
    for cols in (["vendor_id", "invoice_number"], ["vendor_id", "po_number", "gross_total"]):
        for iid in ordered[ordered.duplicated(cols, keep="first")]["invoice_id"]:
            flag(iid, "duplicate")
    return found


def test_counts_match_shares(world):
    n = len(world.clean)
    counts = world.manifest["error_type"].value_counts()
    for kind, share in ERROR_SHARES.items():
        assert counts[kind] == round(share * n)
    assert len(world.invoices) == n + counts["duplicate_invoice"]


def test_one_error_per_invoice(world):
    assert world.manifest["error_id"].is_unique
    assert world.manifest["invoice_id"].is_unique
    assert set(world.manifest["invoice_id"]) <= set(world.invoices["invoice_id"])


def test_rule_checks_find_exactly_the_injected_errors(world):
    found = detect(world)
    # No false alarms on clean invoices, and nothing injected goes unnoticed.
    assert set(found) == set(world.manifest["invoice_id"])
    for row in world.manifest.to_dict("records"):
        assert found[row["invoice_id"]] == {expected_check(row)}, row


def test_deterministic():
    a, b = build(), build()
    assert a.manifest.equals(b.manifest)
    assert a.invoices.equals(b.invoices)
    assert a.lines.equals(b.lines)


def test_pdf_renders_without_po_reference(world, tmp_path):
    row = world.manifest[world.manifest["subtype"] == "missing"].iloc[0]
    iid = row["invoice_id"]
    header = world.invoices[world.invoices["invoice_id"] == iid].iloc[0].to_dict()
    items = world.lines[world.lines["invoice_id"] == iid].to_dict("records")
    vendor = world.vendors.set_index("vendor_id", drop=False).loc[header["vendor_id"]].to_dict()
    path = tmp_path / "x.pdf"
    render_invoice_pdf(header, items, vendor, path)
    assert header["po_number"] == ""
    assert path.read_bytes().startswith(b"%PDF")
