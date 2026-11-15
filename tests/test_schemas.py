from datetime import date
from decimal import Decimal

from p2p.schemas import Currency, ErrorType, Invoice, InvoiceLine


def make_invoice(gross: str = "120.00") -> Invoice:
    return Invoice(
        invoice_number="INV-001",
        invoice_date=date(2026, 11, 15),
        vendor_name="Atelier Cuir SA",
        currency=Currency.EUR,
        lines=[
            InvoiceLine(
                line_no=1,
                description="Calf leather",
                quantity=Decimal("10"),
                unit_price=Decimal("10.00"),
                net_amount=Decimal("100.00"),
                tax_rate=Decimal("0.20"),
            )
        ],
        net_total=Decimal("100.00"),
        tax_amount=Decimal("20.00"),
        gross_total=Decimal(gross),
    )


def test_consistent_invoice():
    inv = make_invoice()
    assert inv.totals_consistent()
    assert inv.line_math_errors() == []


def test_inconsistent_total_is_representable_and_detected():
    assert not make_invoice(gross="150.00").totals_consistent()


def test_seven_error_types():
    assert len(ErrorType) == 7
