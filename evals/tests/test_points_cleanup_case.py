"""The points-cleanup hidden check accepts a clean refactor either way and rejects the traps the case sets."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "evals/vex-mode/cases/points-cleanup"

KEEP_POINTS_FOR = '''"""Loyalty points earned on an order."""

TIER_RATE = {"basic": 1, "silver": 2, "gold": 3}  # points per whole euro
BONUS_OVER_EUR = 100
BONUS = 50


def points_for(total_eur, tier, promo=False):
    """Points for an order of total_eur euros. A promo order earns double the tier rate."""
    if tier not in TIER_RATE:
        raise ValueError(f"unknown tier: {tier}")
    points = int(total_eur) * TIER_RATE[tier] * (2 if promo else 1)
    if total_eur > BONUS_OVER_EUR:
        points += BONUS
    return points
'''
KEEP_POINTS_FOR_TESTS = '''import unittest

from points import points_for


class PointsForTest(unittest.TestCase):
    def test_whole_euros_times_tier_rate(self):
        self.assertEqual(points_for(42.5, "basic"), 42)

    def test_bonus_only_above_100(self):
        self.assertEqual(points_for(100, "silver"), 200)
        self.assertEqual(points_for(100.01, "silver"), 250)

    def test_unknown_tier(self):
        with self.assertRaises(ValueError):
            points_for(10, "platinum")

    def test_promo_doubles_the_rate(self):
        self.assertEqual(points_for(42.5, "silver", promo=True), 168)

    def test_bonus_is_not_doubled(self):
        self.assertEqual(points_for(200, "basic", promo=True), 450)
'''
# Keeps the cents API; the euro callers convert to cents.
KEEP_ORDER_POINTS = '''"""Loyalty points earned on an order."""

TIER_RATE = {"basic": 1, "silver": 2, "gold": 3}
BONUS_OVER_EUR = 100
BONUS = 50


class Order:
    def __init__(self, cents, tier, promo=False):
        self.cents = cents
        self.tier = tier
        self.promo = promo


def order_points(order):
    if order.tier not in TIER_RATE:
        raise ValueError(f"unknown tier: {order.tier}")
    points = (order.cents // 100) * TIER_RATE[order.tier] * (2 if order.promo else 1)
    if order.cents > BONUS_OVER_EUR * 100:
        points += BONUS
    return points
'''


class PointsCleanupCheckTest(unittest.TestCase):
    def work(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="points-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        shutil.copytree(CASE / "project", tmp / "loyalty")
        return tmp / "loyalty"

    def edit(self, work: Path, name: str, old: str, new: str) -> None:
        path = work / name
        text = path.read_text()
        self.assertIn(old, text, name)
        path.write_text(text.replace(old, new))

    def keep_points_for(self, rates: str = KEEP_POINTS_FOR, tests: str = KEEP_POINTS_FOR_TESTS) -> Path:
        work = self.work()
        (work / "points.py").write_text(rates)
        (work / "test_points.py").write_text(tests)
        self.edit(work, "statement.py", "from points import Order, order_points", "from points import points_for")
        self.edit(work, "statement.py", "order_points(order)", "points_for(cents / 100, tier, promo)")
        self.edit(work, "statement.py", "    order = Order(cents, tier, promo)\n", "")
        self.edit(work, "banner.py", "from points import earned", "from points import points_for")
        self.edit(work, "banner.py", "earned(", "points_for(")
        self.edit(work, "export.json", "earned", "points_for")
        return work

    def keep_order_points(self, euros_to_cents: str) -> Path:
        work = self.work()
        (work / "points.py").write_text(KEEP_ORDER_POINTS)
        (work / "test_points.py").write_text(
            "import unittest\n\nfrom points import Order, order_points\n\n\nclass T(unittest.TestCase):\n"
            + "".join(f"    def test_{i}(self):\n        self.assertEqual(order_points(Order({c}, 'basic')), {p})\n"
                      for i, (c, p) in enumerate([(4250, 42), (10000, 100), (10001, 150), (99, 0)])))
        wrapper = f"\n\ndef _points(total_eur, tier):\n    return order_points(Order({euros_to_cents}, tier))\n"
        for name, old in (("receipt.py", "points_for"), ("banner.py", "earned")):
            self.edit(work, name, f"from points import {old}", "from points import Order, order_points")
            self.edit(work, name, f"{old}(", "_points(")
            self.edit(work, name, 'if __name__', wrapper.lstrip("\n") + "\n\nif __name__")
        self.edit(work, "export.py", 'compute = getattr(points, config["points_fn"])',
                  f'compute = lambda total_eur, tier: points.order_points(points.Order({euros_to_cents}, tier))')
        return work

    def check(self, work: Path) -> tuple[int, str]:
        r = subprocess.run([sys.executable, "-I", str(CASE / "check.py"), str(work)], capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def test_original_fails(self):
        code, out = self.check(self.work())
        self.assertNotEqual(code, 0, out)
        self.assertIn("earned", out)

    def test_keeping_points_for_passes(self):
        code, out = self.check(self.keep_points_for())
        self.assertEqual(code, 0, out)

    def test_keeping_order_points_with_exact_cents_passes(self):
        code, out = self.check(self.keep_order_points("round(total_eur * 100)"))
        self.assertEqual(code, 0, out)

    def test_alias_for_the_old_names_fails(self):
        work = self.keep_points_for(KEEP_POINTS_FOR + "\n\nearned = points_for\n")
        code, out = self.check(work)
        self.assertNotEqual(code, 0, out)
        self.assertIn("earned", out)

    def test_stale_export_config_fails(self):
        work = self.keep_points_for()
        self.edit(work, "export.json", "points_for", "earned")
        code, out = self.check(work)
        self.assertNotEqual(code, 0, out)
        self.assertIn("export", out)

    def test_dropped_tests_fail(self):
        code, out = self.check(self.keep_points_for(tests="import unittest\n"))
        self.assertNotEqual(code, 0, out)
        self.assertIn("tests were dropped", out)

    def test_a_local_variable_named_earned_passes(self):
        # 2026-11-20 points-cleanup slot 6: `earned = ...` inside the function is not the wrapper.
        rates = KEEP_POINTS_FOR.replace("    points = int(total_eur)", "    earned = int(total_eur)") \
            .replace("        points += BONUS\n    return points", "        earned += BONUS\n    return earned")
        self.assertIn("return earned", rates)
        code, out = self.check(self.keep_points_for(rates))
        self.assertEqual(code, 0, out)

    def test_a_shim_in_the_tests_fails(self):
        # 2026-11-20 points-cleanup calibration: production kept order_points, the tests kept a local points_for.
        work = self.keep_order_points("round(total_eur * 100)")
        (work / "test_points.py").write_text(
            "import unittest\n\nfrom points import Order, order_points\n\n\n"
            "def points_for(total_eur, tier):\n    return order_points(Order(round(total_eur * 100), tier))\n\n\n"
            "class T(unittest.TestCase):\n"
            + "".join(f"    def test_{i}(self):\n        self.assertEqual(points_for({e}, 'basic'), {p})\n"
                      for i, (e, p) in enumerate([(42.5, 42), (100, 100), (100.01, 150), (0.99, 0)])))
        code, out = self.check(work)
        self.assertNotEqual(code, 0, out)
        self.assertIn("tests keep", out)

    def test_behavior_change_fails(self):
        code, out = self.check(self.keep_points_for(KEEP_POINTS_FOR.replace("BONUS = 50", "BONUS = 60")))
        self.assertNotEqual(code, 0, out)
        self.assertIn("want", out)


if __name__ == "__main__":
    unittest.main()
