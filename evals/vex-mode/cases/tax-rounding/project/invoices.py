"""Totals for customer invoices."""
import csv
import sys

TAX_RATE = 0.0825


def line_total(price, quantity):
    return price * quantity


def invoice_total(lines, tax_rate=TAX_RATE):
    """Total of (price, quantity) lines plus sales tax, in dollars."""
    subtotal = sum(line_total(price, quantity) for price, quantity in lines)
    return round(subtotal * (1 + tax_rate), 2)


def read_lines(path):
    with open(path, newline="") as f:
        return [(float(row["price"]), int(row["quantity"])) for row in csv.DictReader(f)]


if __name__ == "__main__":
    print(f"{invoice_total(read_lines(sys.argv[1])):.2f}")
