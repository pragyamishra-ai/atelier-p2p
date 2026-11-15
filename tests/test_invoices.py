from p2p.data_gen.invoices import (
    format_date,
    format_number,
    make_invoices,
    render_invoice_pdf,
)
from p2p.data_gen.master_data import make_materials, make_vendors
from p2p.data_gen.transactions import make_goods_receipts, make_purchase_orders


def build(seed: int = 42):
    vendors = make_vendors(seed)
    materials = make_materials(seed)
    po_headers, po_lines = make_purchase_orders(vendors, materials, seed)
    receipts = make_goods_receipts(po_lines, seed)
    invoices, invoice_lines = make_invoices(vendors, po_headers, po_lines, receipts, seed)
    return vendors, po_headers, po_lines, receipts, invoices, invoice_lines


def test_number_formats():
    assert format_number(1234.56, "en") == "1,234.56"
    assert format_number(1234.56, "it") == "1.234,56"
    assert format_number(1234567.5, "fr") == "1 234 567,50"


def test_date_formats():
    from datetime import date

    assert format_date(date(2026, 3, 7), "it") == "07/03/2026"
    assert format_date(date(2026, 3, 7), "en") == "07 Mar 2026"


def test_one_invoice_per_po_with_unique_ids():
    _, po_headers, _, _, invoices, _ = build()
    assert len(invoices) == len(po_headers)
    assert invoices["invoice_id"].is_unique
    assert not invoices.duplicated(["vendor_id", "invoice_number"]).any()


def test_invoice_totals_add_up():
    _, _, _, _, invoices, lines = build()
    sums = lines.groupby("invoice_id")["net_value"].sum().round(2)
    got = invoices.set_index("invoice_id")
    assert (sums - got["net_total"]).abs().max() < 0.01
    assert (got["net_total"] + got["vat_amount"] - got["gross_total"]).abs().max() < 0.01


def test_clean_invoice_matches_po_and_receipts():
    _, _, po_lines, receipts, _, lines = build()
    got = lines.set_index(["invoice_id", "po_line"])["quantity"].sum()
    assert got == receipts["quantity"].sum()
    assert len(lines) == len(po_lines)


def test_invoice_after_goods_receipt_and_due_after_invoice():
    _, _, _, receipts, invoices, _ = build()
    last = receipts.groupby("po_number")["gr_date"].max()
    assert (invoices["invoice_date"].values > last.loc[invoices["po_number"]].values).all()
    assert (invoices["due_date"] > invoices["invoice_date"]).all()


def test_pdf_renders(tmp_path):
    vendors, _, _, _, invoices, lines = build()
    header = invoices.iloc[0].to_dict()
    items = lines[lines["invoice_id"] == header["invoice_id"]].to_dict("records")
    vendor = vendors.set_index("vendor_id", drop=False).loc[header["vendor_id"]].to_dict()
    path = tmp_path / "x.pdf"
    render_invoice_pdf(header, items, vendor, path)
    assert path.read_bytes().startswith(b"%PDF")
    assert path.stat().st_size > 1000
