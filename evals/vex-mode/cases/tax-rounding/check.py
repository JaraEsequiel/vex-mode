"""Hidden outcome check: totals must be exact to the cent with half-up rounding."""
import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

work = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("invoices", work / "invoices.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

CASES = [
    ([(10.00, 1)], "10.83"),
    ([(19.99, 3)], "64.92"),
    ([(10.00, 1), (19.99, 3)], "75.74"),
    ([(30.00, 1)], "32.48"),
    ([(1.10, 3)], "3.57"),
]
failed = []
for lines, want in CASES:
    got = mod.invoice_total(lines)
    if Decimal(str(got)) != Decimal(want):
        failed.append(f"{lines}: want {want}, got {got}")
print("\n".join(failed) or "all totals exact")
sys.exit(1 if failed else 0)
