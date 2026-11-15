from p2p.data_gen.master_data import make_materials, make_vendors
from p2p.data_gen.transactions import make_goods_receipts, make_purchase_orders


def build(seed: int = 42):
    vendors = make_vendors(seed)
    materials = make_materials(seed)
    headers, lines = make_purchase_orders(vendors, materials, seed)
    receipts = make_goods_receipts(lines, seed)
    return vendors, materials, headers, lines, receipts


def test_deterministic_for_same_seed():
    a, b = build(1), build(1)
    for left, right in zip(a, b, strict=True):
        assert left.equals(right)


def test_keys_unique():
    _, _, headers, lines, receipts = build()
    assert headers["po_number"].is_unique
    assert not lines.duplicated(["po_number", "line"]).any()
    assert receipts["gr_number"].is_unique


def test_po_currency_and_category_match_vendor():
    vendors, materials, headers, lines, _ = build()
    merged = headers.merge(vendors, on="vendor_id", suffixes=("_po", "_vendor"))
    assert (merged["currency_po"] == merged["currency_vendor"]).all()

    cat = lines.merge(headers[["po_number", "vendor_id"]], on="po_number")
    cat = cat.merge(vendors[["vendor_id", "category"]], on="vendor_id")
    cat = cat.merge(materials[["material_id", "category"]], on="material_id", suffixes=("_v", "_m"))
    assert (cat["category_v"] == cat["category_m"]).all()


def test_line_values_and_header_totals_add_up():
    _, _, headers, lines, _ = build()
    assert ((lines["quantity"] * lines["unit_price"]).round(2) == lines["net_value"]).all()
    sums = lines.groupby("po_number")["net_value"].sum().round(2)
    totals = headers.set_index("po_number")["net_total"]
    assert (sums - totals).abs().max() < 0.01


def test_receipts_sum_to_po_quantity_and_follow_order_date():
    _, _, headers, lines, receipts = build()
    got = receipts.groupby(["po_number", "line"])["quantity"].sum()
    want = lines.set_index(["po_number", "line"])["quantity"]
    assert (got == want).all()

    merged = receipts.merge(headers[["po_number", "order_date"]], on="po_number")
    assert (merged["gr_date"] > merged["order_date"]).all()


def test_some_deliveries_are_split():
    _, _, _, lines, receipts = build()
    assert len(receipts) > len(lines)
