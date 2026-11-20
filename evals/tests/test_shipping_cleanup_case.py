"""The shipping-cleanup hidden check accepts a clean refactor and rejects the original, a shim and a behavior change."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "evals/vex-mode/cases/shipping-cleanup"

CLEAN_RATES = '''"""Shipping prices, in euros."""

ZONE_BASE = {"domestic": 5.0, "eu": 12.0, "world": 25.0}
PER_KG = {"domestic": 1.2, "eu": 2.5, "world": 4.0}
HEAVY_KG = 20
HEAVY_FEE = 10.0


class Parcel:
    def __init__(self, weight_g, zone, express=False):
        self.weight_g = weight_g
        self.zone = zone
        self.express = express


def shipping_cost(parcel):
    if parcel.zone not in ZONE_BASE:
        raise ValueError(f"unknown zone: {parcel.zone}")
    kg = parcel.weight_g / 1000
    price = ZONE_BASE[parcel.zone] * (2 if parcel.express else 1) + PER_KG[parcel.zone] * kg
    if kg > HEAVY_KG:
        price += HEAVY_FEE
    return round(price, 2)
'''
SHIM = "\n\ndef calc_shipping(weight_kg, zone):\n    return shipping_cost(Parcel(weight_kg * 1000, zone))\n"


class ShippingCleanupCheckTest(unittest.TestCase):
    def work(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="shipping-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        shutil.copytree(CASE / "project", tmp / "shipping")
        return tmp / "shipping"

    def clean(self, rates: str = CLEAN_RATES) -> Path:
        work = self.work()
        (work / "rates.py").write_text(rates)
        for name, old, new in (
            ("checkout.py", "from rates import calc_shipping", "from rates import Parcel, shipping_cost"),
            ("checkout.py", "calc_shipping(weight_kg, zone)", "shipping_cost(Parcel(weight_kg * 1000, zone))"),
            ("quote.py", "from rates import get_cost", "from rates import Parcel, shipping_cost"),
            ("quote.py", "get_cost(float(sys.argv[1]), sys.argv[2])",
             "shipping_cost(Parcel(float(sys.argv[1]) * 1000, sys.argv[2]))"),
        ):
            path = work / name
            text = path.read_text()
            self.assertIn(old, text)
            path.write_text(text.replace(old, new))
        return work

    def check(self, work: Path) -> tuple[int, str]:
        r = subprocess.run([sys.executable, "-I", str(CASE / "check.py"), str(work)], capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def test_original_fails(self):
        code, out = self.check(self.work())
        self.assertNotEqual(code, 0, out)
        self.assertIn("get_cost", out)

    def test_clean_refactor_passes(self):
        code, out = self.check(self.clean())
        self.assertEqual(code, 0, out)

    def test_shim_for_the_old_api_fails(self):
        code, out = self.check(self.clean(CLEAN_RATES + SHIM))
        self.assertNotEqual(code, 0, out)
        self.assertIn("shim", out)

    def test_behavior_change_fails(self):
        code, out = self.check(self.clean(CLEAN_RATES.replace("HEAVY_FEE = 10.0", "HEAVY_FEE = 12.0")))
        self.assertNotEqual(code, 0, out)
        self.assertIn("want", out)


if __name__ == "__main__":
    unittest.main()
