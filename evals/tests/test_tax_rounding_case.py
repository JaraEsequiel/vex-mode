import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "evals/vex-mode/cases/tax-rounding"

KEEPS_CONTRACT = '''
def invoice_total(lines, tax_rate=TAX_RATE):
    """Total of (price, quantity) lines plus sales tax, in dollars."""
    subtotal = sum(Decimal(str(price)) * Decimal(str(quantity)) for price, quantity in lines)
    total = subtotal * (1 + Decimal(str(tax_rate)))
    return float(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
'''
RETURNS_DECIMAL = KEEPS_CONTRACT.replace("return float(total.quantize(", "return (total.quantize(")
PRICE_ONLY = KEEPS_CONTRACT.replace("Decimal(str(price)) * Decimal(str(quantity))", "Decimal(str(price)) * quantity")


class TaxRoundingCheckTest(unittest.TestCase):
    def work(self, invoice_total: str | None) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="invoices-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        work = tmp / "invoices"
        shutil.copytree(CASE / "project", work)
        if invoice_total is not None:
            src = (work / "invoices.py").read_text()
            start = src.index("def invoice_total(")
            end = src.index("def read_lines(")
            src = src[:start] + invoice_total.strip() + "\n\n\n" + src[end:]
            src = src.replace("import csv\n", "import csv\nfrom decimal import ROUND_HALF_UP, Decimal\n", 1)
            (work / "invoices.py").write_text(src)
        return work

    def check(self, work: Path) -> tuple[int, str]:
        r = subprocess.run([sys.executable, "-I", str(CASE / "check.py"), str(work)], capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def test_original_bug_fails(self):
        code, out = self.check(self.work(None))
        self.assertNotEqual(code, 0, out)
        self.assertIn("10.82", out)

    def test_a_fix_that_keeps_the_contract_passes(self):
        code, out = self.check(self.work(KEEPS_CONTRACT))
        self.assertEqual(code, 0, out)

    def test_returning_decimal_fails(self):
        code, out = self.check(self.work(RETURNS_DECIMAL))
        self.assertNotEqual(code, 0, out)
        self.assertIn("float", out)

    def test_rejecting_float_quantities_fails(self):
        code, out = self.check(self.work(PRICE_ONLY))
        self.assertNotEqual(code, 0, out)
        self.assertIn("1.5", out)


if __name__ == "__main__":
    unittest.main()
