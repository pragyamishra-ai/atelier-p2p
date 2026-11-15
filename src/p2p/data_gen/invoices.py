"""Invoices: clean invoice data (ground truth) plus PDF rendering in several layouts."""

import random
import re
from datetime import date, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

VAT_RATES = {"IT": 0.22, "FR": 0.20, "DE": 0.19, "GB": 0.20, "CH": 0.081}
DEFAULT_VAT = 0.20

LABELS = {
    "en": {
        "invoice": "Invoice",
        "number": "Invoice no.",
        "date": "Invoice date",
        "due": "Due date",
        "po": "Purchase order",
        "terms": "Payment terms",
        "vat_id": "VAT ID",
        "pos": "Pos.",
        "desc": "Description",
        "qty": "Qty",
        "unit": "Unit",
        "price": "Unit price",
        "amount": "Amount",
        "net": "Net total",
        "vat": "VAT",
        "total": "Total due",
    },
    "fr": {
        "invoice": "Facture",
        "number": "Facture n°",
        "date": "Date de facture",
        "due": "Échéance",
        "po": "Commande n°",
        "terms": "Conditions de paiement",
        "vat_id": "N° TVA",
        "pos": "Pos.",
        "desc": "Désignation",
        "qty": "Qté",
        "unit": "Unité",
        "price": "Prix",
        "amount": "Montant",
        "net": "Total HT",
        "vat": "TVA",
        "total": "Total TTC",
    },
    "it": {
        "invoice": "Fattura",
        "number": "Fattura n.",
        "date": "Data fattura",
        "due": "Scadenza",
        "po": "Ordine d'acquisto",
        "terms": "Condizioni di pagamento",
        "vat_id": "P. IVA",
        "pos": "Pos.",
        "desc": "Descrizione",
        "qty": "Q.tà",
        "unit": "UM",
        "price": "Prezzo",
        "amount": "Importo",
        "net": "Imponibile",
        "vat": "IVA",
        "total": "Totale fattura",
    },
}

# align: 0 = left, 2 = right
LAYOUTS = [
    {
        "font": "Helvetica",
        "bold": "Helvetica-Bold",
        "align": 0,
        "grid": True,
        "zebra": False,
        "accent": colors.HexColor("#222222"),
        "head_bg": colors.HexColor("#DDDDDD"),
    },
    {
        "font": "Times-Roman",
        "bold": "Times-Bold",
        "align": 2,
        "grid": False,
        "zebra": False,
        "accent": colors.HexColor("#1F4E79"),
        "head_bg": colors.white,
    },
    {
        "font": "Courier",
        "bold": "Courier-Bold",
        "align": 0,
        "grid": False,
        "zebra": True,
        "accent": colors.HexColor("#7A1F1F"),
        "head_bg": colors.HexColor("#EFE6E6"),
    },
]


def format_number(value: float, lang: str) -> str:
    """1234.56 -> '1,234.56' (en), '1.234,56' (it), '1 234,56' (fr)."""
    s = f"{value:,.2f}"
    if lang == "it":
        return s.replace(",", "X").replace(".", ",").replace("X", ".")
    if lang == "fr":
        return s.replace(",", " ").replace(".", ",")
    return s


def format_money(value: float, currency: str, lang: str) -> str:
    n = format_number(value, lang)
    return f"{currency} {n}" if lang == "en" else f"{n} {currency}"


def format_date(d: date, lang: str) -> str:
    return d.strftime("%d %b %Y") if lang == "en" else d.strftime("%d/%m/%Y")


def make_invoices(
    vendors: pd.DataFrame,
    po_headers: pd.DataFrame,
    po_lines: pd.DataFrame,
    receipts: pd.DataFrame,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One clean invoice per PO: received quantities at PO prices."""
    rng = random.Random(seed + 4)
    vend = vendors.set_index("vendor_id").to_dict("index")
    last_gr = receipts.groupby("po_number")["gr_date"].max()
    received = receipts.groupby(["po_number", "line"])["quantity"].sum()
    lines_by_po = {po: grp.to_dict("records") for po, grp in po_lines.groupby("po_number")}
    counters: dict[str, int] = {}

    headers, lines = [], []
    for n, po in enumerate(po_headers.to_dict("records"), start=1):
        v = vend[po["vendor_id"]]
        invoice_id = f"INV{n:06d}"
        if po["vendor_id"] not in counters:
            counters[po["vendor_id"]] = rng.randint(100, 900)
        counters[po["vendor_id"]] += 1
        invoice_date = last_gr[po["po_number"]] + timedelta(days=rng.randint(1, 10))
        match = re.search(r"NET(\d+)", po["payment_terms"])
        due_date = invoice_date + timedelta(days=int(match.group(1)) if match else 30)

        net_total = 0.0
        for pl in lines_by_po[po["po_number"]]:
            qty = int(received[(po["po_number"], pl["line"])])
            net_value = round(qty * pl["unit_price"], 2)
            net_total += net_value
            lines.append(
                {
                    "invoice_id": invoice_id,
                    "po_line": pl["line"],
                    "material_id": pl["material_id"],
                    "description": pl["description"],
                    "quantity": qty,
                    "unit": pl["unit"],
                    "unit_price": pl["unit_price"],
                    "net_value": net_value,
                }
            )
        net_total = round(net_total, 2)
        vat_rate = VAT_RATES.get(v["country"], DEFAULT_VAT)
        vat_amount = round(net_total * vat_rate, 2)
        headers.append(
            {
                "invoice_id": invoice_id,
                "invoice_number": f"{invoice_date.year}/{counters[po['vendor_id']]:05d}",
                "vendor_id": po["vendor_id"],
                "po_number": po["po_number"],
                "invoice_date": invoice_date,
                "due_date": due_date,
                "currency": po["currency"],
                "payment_terms": po["payment_terms"],
                "net_total": net_total,
                "vat_rate": vat_rate,
                "vat_amount": vat_amount,
                "gross_total": round(net_total + vat_amount, 2),
                "pdf_file": f"{invoice_id}.pdf",
            }
        )
    return pd.DataFrame(headers), pd.DataFrame(lines)


def render_invoice_pdf(header: dict, items: list[dict], vendor: dict, path: Path) -> None:
    lang = vendor["language"] if vendor["language"] in LABELS else "en"
    L = LABELS[lang]
    lay = LAYOUTS[int(vendor["vendor_id"]) % len(LAYOUTS)]
    cur = header["currency"]

    body = ParagraphStyle(
        "body", fontName=lay["font"], fontSize=9, leading=12, alignment=lay["align"]
    )
    title = ParagraphStyle(
        "title",
        parent=body,
        fontName=lay["bold"],
        fontSize=20,
        leading=24,
        textColor=lay["accent"],
        spaceAfter=6,
    )
    cell = ParagraphStyle("cell", fontName=lay["font"], fontSize=8.5, leading=10)

    story = [
        Paragraph(f"<b>{escape(vendor['name'])}</b>", body),
        Paragraph(f"{escape(vendor['country'])} · {L['vat_id']}: {vendor['vat_id']}", body),
        Spacer(1, 10 * mm),
        Paragraph(L["invoice"].upper(), title),
        Paragraph(f"{L['number']}: <b>{header['invoice_number']}</b>", body),
        Paragraph(f"{L['date']}: {format_date(header['invoice_date'], lang)}", body),
        Paragraph(f"{L['due']}: {format_date(header['due_date'], lang)}", body),
        Paragraph(f"{L['po']}: {header['po_number']}", body),
        Paragraph(f"{L['terms']}: {escape(header['payment_terms'])}", body),
        Spacer(1, 8 * mm),
    ]

    rows = [
        [
            L["pos"],
            L["desc"],
            L["qty"],
            L["unit"],
            f"{L['price']} ({cur})",
            f"{L['amount']} ({cur})",
        ]
    ]
    for i, it in enumerate(items, start=1):
        rows.append(
            [
                str(i * 10),
                Paragraph(escape(it["description"]), cell),
                f"{it['quantity']:,}".replace(",", " ") if lang == "fr" else str(it["quantity"]),
                it["unit"],
                format_number(it["unit_price"], lang),
                format_number(it["net_value"], lang),
            ]
        )
    widths = [12 * mm, 70 * mm, 18 * mm, 12 * mm, 29 * mm, 29 * mm]
    style = [
        ("FONTNAME", (0, 0), (-1, 0), lay["bold"]),
        ("FONTNAME", (0, 1), (-1, -1), lay["font"]),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), lay["head_bg"]),
    ]
    # Shrink any header label that is wider than its column (6 pt padding on each side).
    for col, (label, width) in enumerate(zip(rows[0], widths, strict=True)):
        size = 8.5
        while stringWidth(label, lay["bold"], size) > width - 12 and size > 6:
            size -= 0.25
        if stringWidth(label, lay["bold"], size) > width - 12:
            raise ValueError(f"Header '{label}' does not fit its column in {lay['bold']}")
        if size < 8.5:
            style.append(("FONTSIZE", (col, 0), (col, 0), size))
    if lay["grid"]:
        style.append(("GRID", (0, 0), (-1, -1), 0.5, colors.grey))
    else:
        style += [
            ("LINEBELOW", (0, 0), (-1, 0), 1, lay["accent"]),
            ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.grey),
        ]
    if lay["zebra"]:
        style.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.whitesmoke]))
    story.append(Table(rows, colWidths=widths, style=TableStyle(style), repeatRows=1))
    story.append(Spacer(1, 6 * mm))

    pct = f"{header['vat_rate'] * 100:g}".replace(".", "," if lang != "en" else ".")
    totals = Table(
        [
            [L["net"], format_money(header["net_total"], cur, lang)],
            [f"{L['vat']} {pct}%", format_money(header["vat_amount"], cur, lang)],
            [L["total"], format_money(header["gross_total"], cur, lang)],
        ],
        colWidths=[40 * mm, 45 * mm],
        hAlign="RIGHT",
        style=TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), lay["font"]),
                ("FONTNAME", (0, -1), (-1, -1), lay["bold"]),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LINEABOVE", (0, -1), (-1, -1), 1, lay["accent"]),
            ]
        ),
    )
    story.append(totals)

    SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=f"{L['invoice']} {header['invoice_number']}",
        invariant=1,
    ).build(story)


def render_all(
    headers: pd.DataFrame, lines: pd.DataFrame, vendors: pd.DataFrame, out_dir: Path
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.pdf"):
        old.unlink()
    vend = vendors.set_index("vendor_id", drop=False).to_dict("index")
    items_by_invoice = {k: g.to_dict("records") for k, g in lines.groupby("invoice_id")}
    for header in headers.to_dict("records"):
        render_invoice_pdf(
            header,
            items_by_invoice[header["invoice_id"]],
            vend[header["vendor_id"]],
            out_dir / header["pdf_file"],
        )
