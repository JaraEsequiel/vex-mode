"""Hidden outcome check: one way to compute points, no shim, specs kept and passing, every README command prints what it printed."""
import ast
import re
import subprocess
import sys
import tempfile
from pathlib import Path

work = Path(sys.argv[1])
# Output of the original project for each command (the behavior every caller must keep).
GOLDEN = [
    [
        [
            "receipt.py",
            "42.50",
            "silver"
        ],
        "you earned 84 points"
    ],
    [
        [
            "receipt.py",
            "100.01",
            "basic"
        ],
        "you earned 150 points"
    ],
    [
        [
            "receipt.py",
            "100",
            "gold"
        ],
        "you earned 300 points"
    ],
    [
        [
            "receipt.py",
            "0.99",
            "basic"
        ],
        "you earned 0 points"
    ],
    [
        [
            "receipt.py",
            "250.99",
            "gold"
        ],
        "you earned 800 points"
    ],
    [
        [
            "statement.py",
            "15000",
            "gold",
            "promo"
        ],
        "GOLD order 150.00 EUR: 950 pts (promo x2)"
    ],
    [
        [
            "statement.py",
            "10001",
            "basic"
        ],
        "BASIC order 100.01 EUR: 150 pts"
    ],
    [
        [
            "statement.py",
            "10000",
            "silver",
            "promo"
        ],
        "SILVER order 100.00 EUR: 400 pts (promo x2)"
    ],
    [
        [
            "statement.py",
            "99",
            "gold"
        ],
        "GOLD order 0.99 EUR: 0 pts"
    ],
    [
        [
            "banner.py",
            "99.90",
            "basic"
        ],
        "buy now and earn 99 points"
    ],
    [
        [
            "banner.py",
            "100.01",
            "silver"
        ],
        "buy now and earn 250 points"
    ],
    [
        [
            "banner.py",
            "300.5",
            "gold"
        ],
        "buy now and earn 950 points"
    ],
    [
        [
            "export.py",
            "orders.csv"
        ],
        "A-1001,42\nA-1002,200\nA-1003,350\nA-1004,550\nA-1005,0"
    ]
]
# A fresh export input the candidate never saw, with the original's output.
HIDDEN_CSV = "order_id,total_eur,tier\nH-1,100.01,silver\nH-2,57.30,basic\nH-3,1000,gold\n"
HIDDEN_OUT = "H-1,250\nH-2,57\nH-3,3050"
MIN_SPECS = 4


def run(argv):
    return subprocess.run([sys.executable, *argv], cwd=work, capture_output=True, text=True, timeout=60)


failed = []
for argv, want in GOLDEN:
    out = run(argv)
    got = out.stdout.strip()
    if got != want:
        failed.append(f"python3 {' '.join(argv)}: want {want!r}, got {(got or out.stderr.strip()[-200:])!r}")

with tempfile.TemporaryDirectory() as tmp:
    csv_path = Path(tmp) / "orders.csv"
    csv_path.write_text(HIDDEN_CSV)
    out = run(["export.py", str(csv_path)])
    if out.stdout.strip() != HIDDEN_OUT:
        failed.append(f"export of unseen orders: want {HIDDEN_OUT!r}, got {(out.stdout.strip() or out.stderr.strip()[-200:])!r}")

specs = run(["points_spec.py"])
ran = re.search(r"(\d+) of (\d+) specs passed", specs.stdout)
if not ran or int(ran.group(2)) < MIN_SPECS:
    failed.append(f"the specs were dropped instead of moved to the remaining function ({ran.group(2) if ran else 0} ran)")
elif specs.returncode != 0:
    failed.append(f"python3 points_spec.py fails: {(specs.stdout + specs.stderr).strip()[-300:]!r}")

def top_level(text, name):
    """Names a module defines at its top level (functions, classes, assignments): local variables do not count."""
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        failed.append(f"{name} does not parse: {e}")
        return set()
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


files = [p for p in work.rglob("*.py") if "__pycache__" not in p.parts]
sources = {p: p.read_text() for p in files if not p.name.endswith("_spec.py")}
defined = set().union(*(top_level(text, p.name) for p, text in sources.items()))
in_specs = set().union(*(top_level(p.read_text(), p.name) for p in files if p.name.endswith("_spec.py")))
if "earned" in defined | in_specs:
    failed.append("the earned wrapper is still there")
if {"points_for", "order_points"} <= defined:
    failed.append("both points_for and order_points are still defined (two ways to compute points, or a shim)")
for name in sorted({"points_for", "order_points", "earned"} & in_specs - defined):
    failed.append(f"the specs keep a local {name} shim for a deleted function")
rule = sum(text.count("TIER_RATE[") for text in sources.values())
if rule > 1:
    failed.append(f"the tier-rate rule appears {rule} times")
print("\n".join(failed) or "one way to compute points, specs kept, every command prints what it printed")
sys.exit(1 if failed else 0)
