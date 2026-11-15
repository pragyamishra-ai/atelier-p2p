"""Synthetic data generator entry point (run with: make data)."""

from p2p.config import settings
from p2p.data_gen.errors import inject_errors
from p2p.data_gen.invoices import make_invoices, render_all
from p2p.data_gen.master_data import make_materials, make_vendors
from p2p.data_gen.scans import make_scans
from p2p.data_gen.transactions import make_goods_receipts, make_purchase_orders


def main() -> None:
    out = settings.generated_dir
    out.mkdir(parents=True, exist_ok=True)

    # DataFrames are passed in memory (not re-read from CSV), so IDs keep their leading zeros.
    vendors = make_vendors(settings.seed)
    materials = make_materials(settings.seed)
    po_headers, po_lines = make_purchase_orders(vendors, materials, settings.seed)
    receipts = make_goods_receipts(po_lines, settings.seed)
    invoices, invoice_lines = make_invoices(vendors, po_headers, po_lines, receipts, settings.seed)
    invoices, invoice_lines, manifest = inject_errors(
        po_headers, receipts, invoices, invoice_lines, settings.seed
    )

    vendors.to_csv(out / "vendors.csv", index=False)
    materials.to_csv(out / "materials.csv", index=False)
    po_headers.to_csv(out / "po_headers.csv", index=False)
    po_lines.to_csv(out / "po_lines.csv", index=False)
    receipts.to_csv(out / "goods_receipts.csv", index=False)
    invoices.to_csv(out / "invoices.csv", index=False)
    invoice_lines.to_csv(out / "invoice_lines.csv", index=False)
    manifest.to_csv(out / "error_manifest.csv", index=False)

    # Clean text PDFs for every invoice, then the eval inputs: clean copies or degraded scans.
    render_all(invoices, invoice_lines, vendors, out / "invoices_clean")
    meta = make_scans(invoices, out / "invoices_clean", out / "invoices", settings.seed)
    meta.to_csv(out / "invoice_meta.csv", index=False)

    q = meta["scan_quality"].value_counts().to_dict()
    print(
        f"seed={settings.seed}: {len(vendors)} vendors, {len(materials)} materials, "
        f"{len(po_headers)} POs, {len(po_lines)} PO lines, {len(receipts)} receipts, "
        f"{len(invoices)} invoice PDFs ({q.get('clean', 0)} clean, {q.get('mild', 0)} mild, "
        f"{q.get('bad', 0)} bad), {len(manifest)} injected errors -> {out}"
    )


if __name__ == "__main__":
    main()
