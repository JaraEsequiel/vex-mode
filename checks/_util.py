import json
from pathlib import Path

SCOPE = ("skills/**/*", "rules/**/*", "agents/**/*")


def iter_files(root: Path, globs=SCOPE) -> list[Path]:
    found = set()
    for pattern in globs:
        found.update(p for p in root.glob(pattern) if p.is_file() and "__pycache__" not in p.parts)
    return sorted(found)


def load_lock(root: Path) -> dict | None:
    path = root / "vendor.lock"
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def parse_frontmatter(text: str) -> dict[str, str]:
    """Flat `key: value` YAML between leading '---' fences. Returns {} if absent."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    result = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return result
        if ":" in line and not line.startswith((" ", "\t", "-")):
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip().strip('"').strip("'")
    return {}
