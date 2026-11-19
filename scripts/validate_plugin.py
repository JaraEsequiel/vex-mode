"""Run `agy plugin validate --strict` semantics with one documented exception.

The root AGENTS.md is for agents maintaining this repo (see the design, section 6.1),
so agy's "never loaded" warning for it is expected. Every other warning or error fails.
"""
import json
import subprocess
import sys
from pathlib import Path

ALLOWED = [("warning", "AGENTS.md", "never loaded")]


def evaluate(report: dict) -> list[str]:
    problems = []
    for f in report.get("findings", []):
        severity, file, message = f.get("severity"), f.get("file", ""), f.get("message", "")
        if severity not in ("warning", "error"):
            continue
        if any(severity == s and file == p and message.startswith(m) for s, p, m in ALLOWED):
            continue
        problems.append(f"{severity}: {file}: {message}")
    return problems


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    out = subprocess.run(["agy", "plugin", "validate", str(root), "--json"], capture_output=True, text=True)
    try:
        report = json.loads(out.stdout)
    except json.JSONDecodeError:
        print(out.stdout + out.stderr)
        return 1
    problems = evaluate(report)
    print(json.dumps(report.get("components", {})))
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
