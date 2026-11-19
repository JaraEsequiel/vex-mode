"""Every rule in AGENTS.md '## Rules' names an enforcer that exists in the repo."""
import re
from pathlib import Path

BACKTICK = re.compile(r"`([^`]+)`")


def _rules_rows(text: str) -> list[list[str]] | None:
    lines = text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == "## Rules")
    except StopIteration:
        return None
    rows = []
    seen_table = False
    for line in lines[start + 1:]:
        s = line.strip()
        if s.startswith("## "):
            break
        if s.startswith("|"):
            seen_table = True
            cells = [c.strip() for c in s.strip("|").split("|")]
            if set(cells[0]) <= set("-: ") or cells[0] == "Rule":
                continue
            rows.append(cells)
        elif seen_table:
            break
    return rows


def run(root: Path) -> list[str]:
    path = root / "AGENTS.md"
    if not path.is_file():
        return ["AGENTS.md: missing"]
    rows = _rules_rows(path.read_text())
    if rows is None:
        return ["AGENTS.md: missing '## Rules' heading"]
    if not rows:
        return ["AGENTS.md: '## Rules' table has no rows"]
    errors = []
    for cells in rows:
        rule = cells[0]
        enforcer = cells[1] if len(cells) > 1 else ""
        paths = BACKTICK.findall(enforcer)
        if not paths:
            errors.append(f"AGENTS.md rule '{rule}': no enforcer path")
            continue
        for p in paths:
            if not (root / p).exists():
                errors.append(f"AGENTS.md rule '{rule}': enforcer {p} does not exist")
    return errors
