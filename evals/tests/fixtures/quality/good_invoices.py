"""Totals for customer invoices."""
import csv
from decimal import Decimal, ROUND_HALF_UP
import sys

TAX_RATE = Decimal("0.0825")
CENT = Decimal("0.01")


def _to_decimal(value):
    return value if isinstance(value, Decimal) else Decimal(str(value))


def line_total(price, quantity):
    return _to_decimal(price) * quantity


def invoice_total(lines, tax_rate=TAX_RATE):
    """Total of (price, quantity) lines plus sales tax, in dollars."""
    subtotal = sum((line_total(price, quantity) for price, quantity in lines), Decimal("0"))
    rate = _to_decimal(tax_rate)
    return (subtotal * (Decimal("1") + rate)).quantize(CENT, rounding=ROUND_HALF_UP)


def read_lines(path):
    with open(path, newline="") as f:
        return [(Decimal(row["price"]), int(row["quantity"])) for row in csv.DictReader(f)]


if __name__ == "__main__":
    print(f"{invoice_total(read_lines(sys.argv[1])):.2f}")
