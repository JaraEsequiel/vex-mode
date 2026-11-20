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


def skill_tree_sha256(skill_dir: Path) -> str:
    """Hash of every file in a skill folder (paths + contents), ignoring __pycache__."""
    import hashlib

    lines = []
    for p in sorted(skill_dir.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            rel = p.relative_to(skill_dir).as_posix()
            lines.append(f"{rel}\0{hashlib.sha256(p.read_bytes()).hexdigest()}\n")
    return hashlib.sha256("".join(lines).encode()).hexdigest()


# Plugin parts that change how every /vex-mode run behaves, so they belong to the vex-mode skill's identity.
PLUGIN_WIDE = ("hooks", "hooks.json", "rules", "agents", "plugin.json")


def plugin_tree_sha256(root: Path, skill: str) -> str:
    """The skill's tree hash; for vex-mode it also covers the plugin-wide parts (tests and __pycache__ left out),
    so a hook change is measurable and old evidence stops matching. `root` is a repo or a plugin build."""
    import hashlib

    if skill != "vex-mode":
        return skill_tree_sha256(root / "skills" / skill)
    lines = [f"skills/vex-mode\0{skill_tree_sha256(root / 'skills' / skill)}\n"]
    for part in PLUGIN_WIDE:
        top = root / part
        files = [top] if top.is_file() else sorted(top.rglob("*")) if top.is_dir() else []
        for p in files:
            if p.is_file() and not {"tests", "__pycache__"} & set(p.relative_to(root).parts):
                lines.append(f"{p.relative_to(root).as_posix()}\0{hashlib.sha256(p.read_bytes()).hexdigest()}\n")
    return hashlib.sha256("".join(lines).encode()).hexdigest()


def model_family(model: str) -> str:
    """claude-* / gemini-* / gpt-* by prefix; anything else is its text before the first '-'."""
    for family in ("claude", "gemini", "gpt"):
        if model.startswith(family + "-"):
            return family
    return model.split("-", 1)[0]


# Words a blinded agent must never see (pstack eval playbook, line 7).
BANNED = ("eval", "test", "judge", "experiment", "rubric", "score", "compare", "benchmark", "candidate", "arena")


def banned_hits(text: str) -> list[str]:
    """Tokens (split on non-letters and camelCase) that start with a banned word."""
    import re

    tokens = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])", text)
    return sorted({t.lower() for t in tokens if t.lower().startswith(BANNED)})


QUALITY_BLOCKING = ("prod_lines", "removable_lines", "complexity_delta", "verbosity", "comments_added",
                    "security_findings", "judge_reuse", "judge_simplicity", "judge_contract")
QUALITY_ALL = QUALITY_BLOCKING + ("test_lines", "docstrings_added")


def promote_blockers(result: dict) -> list[str]:
    """Why a result may not be promoted (design §8.2.1): outcome worse, or a blocking quality measure worse or errored."""
    s = (result.get("signals") or {}).get("B_vs_A") or {}
    out = ["outcome worse"] if s.get("outcome") == "worse" else []
    return out + [f"{n} {s[n]}" for n in QUALITY_BLOCKING if s.get(n) in ("worse", "error")]
