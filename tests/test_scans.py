import random
import shutil
from collections import Counter

import pandas as pd
import pymupdf
import pytest

from p2p.data_gen.invoices import make_invoices, render_invoice_pdf
from p2p.data_gen.master_data import make_materials, make_vendors
from p2p.data_gen.scans import (
    CLEAN_SHARE,
    MILD_SHARE,
    assign_scan_quality,
    degrade_pdf,
    draw_params,
    make_scans,
)
from p2p.data_gen.transactions import make_goods_receipts, make_purchase_orders


@pytest.fixture(scope="module")
def clean_pdf(tmp_path_factory):
    seed = 42
    vendors = make_vendors(seed)
    materials = make_materials(seed)
    po_headers, po_lines = make_purchase_orders(vendors, materials, seed)
    receipts = make_goods_receipts(po_lines, seed)
    invoices, lines = make_invoices(vendors, po_headers, po_lines, receipts, seed)
    header = invoices.iloc[0].to_dict()
    items = lines[lines["invoice_id"] == header["invoice_id"]].to_dict("records")
    vendor = vendors.set_index("vendor_id", drop=False).loc[header["vendor_id"]].to_dict()
    path = tmp_path_factory.mktemp("scans") / "clean.pdf"
    render_invoice_pdf(header, items, vendor, path)
    return path


def test_quality_shares():
    ids = [f"INV{i:06d}" for i in range(1, 207)]
    counts = Counter(assign_scan_quality(ids, random.Random(1)).values())
    assert counts["clean"] == round(CLEAN_SHARE * 206)
    assert counts["mild"] == round(MILD_SHARE * 206)
    assert sum(counts.values()) == 206


def test_assignment_is_deterministic():
    ids = [f"INV{i:06d}" for i in range(1, 51)]
    assert assign_scan_quality(ids, random.Random(7)) == assign_scan_quality(ids, random.Random(7))


def test_degraded_pdf_is_image_only(clean_pdf, tmp_path):
    dst = tmp_path / "bad.pdf"
    degrade_pdf(clean_pdf, dst, draw_params(random.Random(3), "bad"), seed=3)
    with pymupdf.open(str(clean_pdf)) as a, pymupdf.open(str(dst)) as b:
        assert a[0].get_text().strip() != ""
        assert b[0].get_text().strip() == ""
        assert len(b[0].get_images()) == 1
        assert len(a) == len(b)
        assert a[0].rect.width == pytest.approx(b[0].rect.width)
        assert a[0].rect.height == pytest.approx(b[0].rect.height)


def test_make_scans_keeps_clean_text_and_degrades_the_rest(clean_pdf, tmp_path):
    clean_dir, out_dir = tmp_path / "clean", tmp_path / "out"
    clean_dir.mkdir()
    ids = [f"INV{i:06d}" for i in range(1, 21)]
    for invoice_id in ids:
        shutil.copyfile(clean_pdf, clean_dir / f"{invoice_id}.pdf")
    invoices = pd.DataFrame({"invoice_id": ids, "pdf_file": [f"{i}.pdf" for i in ids]})

    meta = make_scans(invoices, clean_dir, out_dir, seed=42)

    assert len(meta) == 20
    assert (meta["scan_quality"] == "clean").sum() == round(CLEAN_SHARE * 20)
    for row in meta.to_dict("records"):
        with pymupdf.open(str(out_dir / row["pdf_file"])) as doc:
            has_text = bool(doc[0].get_text().strip())
        assert has_text == (row["scan_quality"] == "clean")
