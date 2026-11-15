"""Canonical invoice schema shared by generator, extractors, validators and warehouse loader.

Design note: the model does NOT reject inconsistent totals. Injected errors (and real-world
errors) must be representable so the validation layer can detect and route them.
"""

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class Currency(StrEnum):
    EUR = "EUR"
    CHF = "CHF"
    USD = "USD"
    GBP = "GBP"


class Language(StrEnum):
    EN = "en"
    FR = "fr"
    IT = "it"


class InvoiceLine(BaseModel):
    line_no: int = Field(ge=1)
    description: str
    material_id: str | None = None
    quantity: Decimal
    unit: str = "EA"
    unit_price: Decimal
    net_amount: Decimal
    tax_rate: Decimal = Decimal("0")  # e.g. 0.20 for 20%


class Invoice(BaseModel):
    invoice_number: str
    invoice_date: date
    vendor_name: str
    vendor_id: str | None = None  # LIFNR-style key from the vendor master
    po_number: str | None = None  # EBELN-style key
    currency: Currency
    language: Language = Language.EN
    payment_terms: str | None = None
    lines: list[InvoiceLine]
    net_total: Decimal
    tax_amount: Decimal
    gross_total: Decimal
    # Per-field confidence in [0, 1], filled by extractors; empty for ground truth
    confidence: dict[str, float] = Field(default_factory=dict)

    def lines_sum(self) -> Decimal:
        return sum((line.net_amount for line in self.lines), Decimal("0"))

    def totals_consistent(self, tol: Decimal = Decimal("0.02")) -> bool:
        lines_ok = abs(self.lines_sum() - self.net_total) <= tol
        gross_ok = abs(self.net_total + self.tax_amount - self.gross_total) <= tol
        return lines_ok and gross_ok

    def line_math_errors(self, tol: Decimal = Decimal("0.02")) -> list[int]:
        """Line numbers where quantity * unit_price != net_amount."""
        return [
            line.line_no
            for line in self.lines
            if abs(line.quantity * line.unit_price - line.net_amount) > tol
        ]


class ErrorType(StrEnum):
    """The seven injected error types; used in error_manifest.csv and for scoring."""

    DUPLICATE = "duplicate_invoice"
    PRICE_VARIANCE = "price_variance"
    QTY_MISMATCH = "quantity_mismatch"
    TOTAL_MISMATCH = "lines_not_summing_to_total"
    MISSING_PO = "missing_or_wrong_po"
    VAT_CURRENCY = "vat_or_currency_mismatch"
    BEFORE_GR = "invoice_before_goods_receipt"
