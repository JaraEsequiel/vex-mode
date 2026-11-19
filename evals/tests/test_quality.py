import difflib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from harness import quality

CASE = HERE.parent / "vex-mode/cases/tax-rounding"
BEFORE = CASE / "project"
CHECK = CASE / "check.py"
FIX = HERE / "fixtures/quality"
GOOD = (FIX / "good_invoices.py").read_text()


def tree(invoices: str = GOOD, **extra: str) -> Path:
    root = Path(tempfile.mkdtemp(prefix="quality-"))
    shutil.copytree(BEFORE, root, dirs_exist_ok=True)
    (root / "invoices.py").write_text(invoices)
    for name, text in extra.items():
        p = root / (name[:-3] + ".py")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return root


def with_function(source: str) -> str:
    return GOOD.replace("\n\ndef read_lines", f"\n\n{source}\n\n\ndef read_lines")


def run(after: Path, check: Path | None = CHECK, **kw):
    return quality.measure_dirs(BEFORE, after, check, **kw)


class QualityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good, cls.good_errors = run(tree())

    def test_is_test(self):
        for rel in ("test_x.py", "x_test.py", "tests/a.py", "pkg/tests/b.py"):
            self.assertTrue(quality.is_test(rel), rel)
        for rel in ("invoices.py", "repro.py", "contest.py"):
            self.assertFalse(quality.is_test(rel), rel)

    def test_good_patch_baseline(self):
        before = (BEFORE / "invoices.py").read_text().splitlines()
        ops = [l for l in difflib.unified_diff(before, GOOD.splitlines(), lineterm="", n=0)
               if l[:1] in "+-" and not l.startswith(("+++", "---"))]
        self.assertEqual(self.good_errors, {})
        self.assertEqual(self.good["prod_lines"], len(ops))
        self.assertEqual(len(ops), 17)
        for name in ("comments_added", "security_findings", "test_lines", "verbosity"):
            self.assertEqual(self.good[name], 0, name)
        self.assertEqual(set(self.good), set(quality.DETERMINISTIC))

    def test_unneeded_read_lines_change_is_removable(self):
        self.assertEqual(self.good["removable_lines"], 2)
        floats = GOOD.replace('(Decimal(row["price"])', '(float(row["price"])')
        self.assertEqual(run(tree(floats))[0]["removable_lines"], 0)

    def test_comment_is_worse(self):
        values, _ = run(tree(GOOD.replace("    rate = ", "    # explain\n    rate = ")))
        self.assertEqual(values["comments_added"], 1)

    def test_dead_code_is_removable(self):
        values, _ = run(tree(with_function("def _unused(x):\n    return x * 2")))
        self.assertGreaterEqual(values["removable_lines"], 2)
        self.assertGreater(values["prod_lines"], self.good["prod_lines"])

    def test_leftover_script_is_removable(self):
        values, _ = run(tree(repro_py="import invoices\nprint(invoices.invoice_total([(10.0, 1)]))\nprint('done')\n"))
        self.assertEqual(values["prod_lines"], self.good["prod_lines"] + 3)
        self.assertEqual(values["removable_lines"], self.good["removable_lines"] + 3)

    def test_shell_true_is_insecure(self):
        values, _ = run(tree(with_function("def ls():\n    import subprocess\n    subprocess.run('ls', shell=True)")))
        self.assertEqual(values["security_findings"], 1)

    def test_each_security_rule(self):
        cases = {
            "eval(s)": 1, "exec(s)": 1, "os.system(s)": 1, "os.popen(s)": 1, "pickle.loads(s)": 1,
            "marshal.loads(s)": 1, "yaml.load(s)": 1, "yaml.load(s, Loader=yaml.SafeLoader)": 0,
            "requests.get(s, verify=False)": 1, "ctx.verify_mode = ssl.CERT_NONE": 1,
            "ssl._create_unverified_context()": 1, "tempfile.mktemp()": 1, "hashlib.md5()": 1,
            "hashlib.sha1()": 1, 'api_key = "abc123"': 1, 'name = "abc123"': 0,
        }
        for line, want in cases.items():
            with self.subTest(line):
                values, _ = run(tree(with_function(f"def f(s, ctx):\n    {line}")), check=None)
                self.assertEqual(values["security_findings"], want)

    def test_needless_abstraction_raises_complexity(self):
        source = GOOD.replace(
            "    return (subtotal * (Decimal(\"1\") + rate)).quantize(CENT, rounding=ROUND_HALF_UP)",
            "    return _round(subtotal * (Decimal(\"1\") + rate), \"half_up\")\n\n\n"
            "def _round(value, mode):\n"
            "    if mode == \"half_up\":\n        return value.quantize(CENT, rounding=ROUND_HALF_UP)\n"
            "    elif mode == \"down\":\n        return value.quantize(CENT)\n"
            "    elif mode == \"none\":\n        return value\n"
            "    raise ValueError(mode)")
        values, _ = run(tree(source))
        self.assertGreater(values["complexity_delta"], self.good["complexity_delta"])

    def test_cc_counts_branches(self):
        import ast
        fn = ast.parse("def f(x):\n    if x and y:\n        pass\n    for i in x:\n        pass\n").body[0]
        self.assertEqual(quality.cc(fn), 4)

    def test_mass_weights_by_sloc(self):
        self.assertAlmostEqual(quality.mass("def f():\n    return 1\n"), 2 ** 0.5)

    def test_verbosity_rules(self):
        cases = {
            "append loop": "def f(xs):\n    out = []\n    for x in xs:\n        out.append(x)\n    return out",
            "len zero": "def f(xs):\n    if len(xs) == 0:\n        return 0\n    return 1",
            "eq true": "def f(x):\n    if x == True:\n        return 1\n    return 0",
            "single-use name": "def f(x):\n    y = x + 1\n    return y",
            "else after return": "def f(x):\n    if x:\n        return 1\n    else:\n        return 2",
            "except pass": "def f(x):\n    try:\n        x()\n    except Exception:\n        pass",
            "clone": "def f(x):\n    a = x + 1\n    b = a * 2\n    c = b - 3\n    return c\n\n\n"
                     "def g(x):\n    a = x + 1\n    b = a * 2\n    c = b - 3\n    return c * 0",
        }
        for name, source in cases.items():
            with self.subTest(name):
                values, _ = run(tree(with_function(source)), check=None)
                self.assertGreater(values["verbosity"], self.good["verbosity"])

    def test_docstring_is_informative(self):
        values, _ = run(tree(GOOD.replace("def _to_decimal(value):\n",
                                          'def _to_decimal(value):\n    """To Decimal."""\n')))
        self.assertEqual(values["docstrings_added"], 1)
        self.assertEqual(values["comments_added"], 0)

    def test_test_lines_counted_apart(self):
        values, _ = run(tree(test_invoices_py="import invoices\n\n\ndef test_x():\n    assert invoices\n"))
        self.assertEqual(values["test_lines"], 5)
        self.assertEqual(values["prod_lines"], self.good["prod_lines"])

    def test_unappliable_diff_is_an_error(self):
        values, errors = quality.measure(BEFORE, "garbage\n[diff truncated]", CHECK)
        self.assertEqual(set(values), set(quality.DETERMINISTIC))
        self.assertTrue(all(v is None for v in values.values()))
        self.assertEqual(set(errors), set(quality.DETERMINISTIC))
        self.assertIn("apply", errors["prod_lines"])

    def test_removable_check_timeout_is_error(self):
        slow = Path(tempfile.mkdtemp()) / "check.py"
        slow.write_text("import time\ntime.sleep(5)\n")
        values, errors = run(tree(), check=slow, timeout_s=1)
        self.assertIsNone(values["removable_lines"])
        self.assertIn("timed out", errors["removable_lines"])

    def test_removable_requires_passing_baseline(self):
        bad = Path(tempfile.mkdtemp()) / "check.py"
        bad.write_text("import sys\nsys.exit(1)\n")
        values, errors = run(tree(), check=bad)
        self.assertIsNone(values["removable_lines"])
        self.assertEqual(errors["removable_lines"], "check fails on the patch itself")

    def test_syntax_error_file_is_reported(self):
        values, errors = run(tree(test_x_py="def broken(:\n"))
        self.assertIn("test_x.py", errors["comments_added"])
        self.assertIsInstance(values["prod_lines"], int)

    def test_measure_applies_saved_diff(self):
        diff = (FIX / "slot9.diff").read_text()
        self.assertFalse(diff.endswith("\n"), "saved diffs lose their final newline")
        values, errors = quality.measure(BEFORE, diff, CHECK)
        direct, _ = run(tree(test_invoices_py=(FIX / "good_test_invoices.py").read_text()))
        self.assertEqual(errors, {})
        self.assertEqual(values, direct)


if __name__ == "__main__":
    unittest.main()
