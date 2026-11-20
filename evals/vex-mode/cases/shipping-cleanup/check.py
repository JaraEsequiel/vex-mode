"""Hidden outcome check: one way to price a parcel, no shim left, and every entry point prints what it printed before."""
import ast
import subprocess
import sys
from pathlib import Path

work = Path(sys.argv[1])
# Output of the original project for each command (the behavior every caller must keep).
GOLDEN = [
    [
        [
            "checkout.py",
            "40.00",
            "2.5",
            "eu"
        ],
        "total: 58.25"
    ],
    [
        [
            "checkout.py",
            "10",
            "0.75",
            "domestic"
        ],
        "total: 15.90"
    ],
    [
        [
            "checkout.py",
            "99.99",
            "21",
            "world"
        ],
        "total: 218.99"
    ],
    [
        [
            "checkout.py",
            "0",
            "20",
            "eu"
        ],
        "total: 62.00"
    ],
    [
        [
            "labels.py",
            "2500",
            "eu",
            "express"
        ],
        "EXPRESS EU 2500g EUR 30.25"
    ],
    [
        [
            "labels.py",
            "21500",
            "world"
        ],
        "STANDARD WORLD 21500g EUR 121.00"
    ],
    [
        [
            "labels.py",
            "750",
            "domestic"
        ],
        "STANDARD DOMESTIC 750g EUR 5.90"
    ],
    [
        [
            "labels.py",
            "20000",
            "domestic",
            "express"
        ],
        "EXPRESS DOMESTIC 20000g EUR 34.00"
    ],
    [
        [
            "quote.py",
            "2.5",
            "eu"
        ],
        "shipping from EUR 18.25"
    ],
    [
        [
            "quote.py",
            "25",
            "domestic"
        ],
        "shipping from EUR 45.00"
    ],
    [
        [
            "quote.py",
            "0.1",
            "world"
        ],
        "shipping from EUR 25.40"
    ]
]
failed = []
for argv, want in GOLDEN:
    out = subprocess.run([sys.executable, *argv], cwd=work, capture_output=True, text=True, timeout=60)
    got = out.stdout.strip()
    if got != want:
        failed.append(f"python3 {' '.join(argv)}: want {want!r}, got {(got or out.stderr.strip()[-200:])!r}")

sources = {p: p.read_text() for p in work.rglob("*.py") if "test" not in p.name and "__pycache__" not in p.parts}
defined = set()
for path, text in sources.items():
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        failed.append(f"{path.name} does not parse: {e}")
        continue
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            defined.update(t.id for t in node.targets if isinstance(t, ast.Name))
if "get_cost" in defined:
    failed.append("the get_cost wrapper is still there")
if {"calc_shipping", "shipping_cost"} <= defined:
    failed.append("both calc_shipping and shipping_cost are still defined (two ways to price, or a shim)")
formula = sum(text.count("PER_KG[") for text in sources.values())
if formula > 1:
    failed.append(f"the per-kg price rule appears {formula} times")
print("\n".join(failed) or "one way to price, callers print what they printed")
sys.exit(1 if failed else 0)
