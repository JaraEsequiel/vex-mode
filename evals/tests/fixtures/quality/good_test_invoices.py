"""Tests for invoice total calculations."""
from decimal import Decimal
from pathlib import Path
import unittest

import invoices


class InvoiceTotalTests(unittest.TestCase):
    def test_inv_1042_csv_rounds_half_up(self):
        csv_path = Path(__file__).with_name("inv-1042.csv")
        lines = invoices.read_lines(csv_path)
        self.assertEqual(invoices.invoice_total(lines), Decimal("10.83"))

    def test_half_cent_rounds_half_up(self):
        # 2.00 * 1.0825 = 2.165 -> 2.17 (half-up, not round-half-to-even 2.16)
        lines = [(Decimal("2.00"), 1)]
        self.assertEqual(invoices.invoice_total(lines), Decimal("2.17"))

    def test_multi_line_invoice(self):
        # (1.99 * 3) + (4.50 * 2) = 5.97 + 9.00 = 14.97
        # 14.97 * 1.0825 = 16.205025 -> 16.21
        lines = [(Decimal("1.99"), 3), (Decimal("4.50"), 2)]
        self.assertEqual(invoices.invoice_total(lines), Decimal("16.21"))

    def test_decimal_addition_no_float_drift(self):
        lines = [(Decimal("0.10"), 1), (Decimal("0.20"), 1)]
        self.assertEqual(
            invoices.invoice_total(lines, tax_rate=Decimal("0")),
            Decimal("0.30"),
        )

    def test_empty_lines(self):
        self.assertEqual(invoices.invoice_total([]), Decimal("0.00"))


if __name__ == "__main__":
    unittest.main()
