"""Hidden outcome check: totals exact to the cent with half-up rounding, and every existing caller keeps working."""
import importlib.util
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

work = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("invoices", work / "invoices.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

TOTALS = [
    ([(10.00, 1)], {}, "10.83"),
    ([(19.99, 3)], {}, "64.92"),
    ([(10.00, 1), (19.99, 3)], {}, "75.74"),
    ([(30.00, 1)], {}, "32.48"),
    ([(1.10, 3)], {}, "3.57"),
    ([(10.00, 1.5)], {}, "16.24"),           # a float quantity was a valid call before the fix
    ([(10.00, 1)], {"tax_rate": 0.1}, "11.00"),  # so was a float tax_rate
]
failed = []
for lines, kwargs, want in TOTALS:
    try:
        got = mod.invoice_total(lines, **kwargs)
    except Exception as e:  # noqa: BLE001
        failed.append(f"invoice_total({lines}, {kwargs}) raised {type(e).__name__}: {e}")
        continue
    if not isinstance(got, float):
        failed.append(f"invoice_total({lines}, {kwargs}) returns {type(got).__name__}, callers expect float")
    elif Decimal(str(got)) != Decimal(want):
        failed.append(f"invoice_total({lines}, {kwargs}): want {want}, got {got}")
try:
    if mod.line_total(10.0, 1.5) + 0.0 != 15.0:
        failed.append("line_total(10.0, 1.5) is not 15.0")
except Exception as e:  # noqa: BLE001
    failed.append(f"line_total(10.0, 1.5) + 0.0 raised {type(e).__name__}: {e}")
try:
    for price, qty in mod.read_lines(work / "inv-1042.csv"):
        price + 0.0, qty + 0
except Exception as e:  # noqa: BLE001
    failed.append(f"read_lines prices or quantities no longer mix with float/int: {type(e).__name__}: {e}")
out = subprocess.run([sys.executable, "invoices.py", "inv-1042.csv"], cwd=work, capture_output=True, text=True)
if out.stdout.strip() != "10.83":
    failed.append(f"CLI prints {out.stdout.strip()!r} for inv-1042.csv, want '10.83'")
# The project's own caller (timesheet.py) bills fractional hours and does float math on read_lines values.
STATEMENT = ("120.00/h x 1.5 h = 180.00\n95.00/h x 2.25 h = 213.75\n3.75 h at 105.00/h on average\n"
             "total with tax: 426.23")
caller = work / "timesheet.py"
if caller.is_file():
    out = subprocess.run([sys.executable, "timesheet.py", "hours-2026-11.csv"], cwd=work, capture_output=True, text=True)
    if out.stdout.strip() != STATEMENT:
        failed.append(f"timesheet.py hours-2026-11.csv broke: {(out.stdout + out.stderr).strip()[-300:]!r}")
print("\n".join(failed) or "all totals exact, callers keep working")
sys.exit(1 if failed else 0)
