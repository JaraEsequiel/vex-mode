"""Skill frontmatter, size budgets and dangling references."""
import re
from pathlib import Path

from _util import iter_files, load_lock, parse_frontmatter

SKILL_MAX = 16384
RULE_MAX = 24576
BOLD_REF = re.compile(r"\*\*([a-z0-9-]+)\*\* (?:skill|principle)")
PRINCIPLE_REF = re.compile(r"\bprinciple-[a-z0-9-]+\b")
PLAYBOOK_REF = re.compile(r"playbooks/[a-z0-9-]+\.md")
LINK_REF = re.compile(r"\]\((\.\.?/[^)\s]+)\)")


def _skill_exists(root: Path, name: str) -> bool:
    return (root / "skills" / name / "SKILL.md").is_file() or (root / "skills" / f"principle-{name}" / "SKILL.md").is_file()


def _check_refs(root: Path, path: Path, rel: str, text: str, pending: set) -> list[str]:
    errors = []
    names = set(BOLD_REF.findall(text)) | set(PRINCIPLE_REF.findall(text))
    for name in sorted(names):
        if name not in pending and not _skill_exists(root, name):
            errors.append(f"{rel}: references missing skill '{name}'")
    parts = Path(rel).parts
    if parts[0] == "skills" and len(parts) > 2:
        skill_dir = root / parts[0] / parts[1]
        for ref in sorted(set(PLAYBOOK_REF.findall(text))):
            if ref not in pending and not (skill_dir / ref).is_file():
                errors.append(f"{rel}: references missing {ref}")
    for ref in sorted(set(LINK_REF.findall(text))):
        if ref not in pending and not (path.parent / ref.split("#")[0]).exists():
            errors.append(f"{rel}: broken link {ref}")
    return errors


def run(root: Path) -> list[str]:
    lock = load_lock(root) or {}
    pending = {f["path"]: set(f.get("pending_refs", [])) for f in lock.get("files", [])}
    errors = []
    for path in iter_files(root):
        rel = path.relative_to(root).as_posix()
        if path.suffix != ".md":
            continue
        data = path.read_bytes()
        text = data.decode("utf-8", errors="replace")
        if path.name == "SKILL.md":
            folder = path.parent.name
            fm = parse_frontmatter(text)
            if fm.get("name") != folder:
                errors.append(f"{rel}: frontmatter name '{fm.get('name')}' must match folder '{folder}'")
            if not fm.get("description"):
                errors.append(f"{rel}: frontmatter description is required")
            if len(data) > SKILL_MAX:
                errors.append(f"{rel}: {len(data)} bytes exceeds SKILL.md budget of {SKILL_MAX}")
        if rel.startswith("rules/") and len(data) > RULE_MAX:
            errors.append(f"{rel}: {len(data)} bytes exceeds agy rule cap of {RULE_MAX}")
        errors += _check_refs(root, path, rel, text, pending.get(rel, set()))
        for ref in sorted(pending.get(rel, set())):
            if not re.search(r"(?<![A-Za-z0-9-])" + re.escape(ref) + r"(?![A-Za-z0-9-])", text):
                errors.append(f"{rel}: stale pending_ref '{ref}' (no longer referenced; remove it from vendor.lock)")
    return errors
