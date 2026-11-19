"""Reads that invalidate a run: anything under a forbidden root, or a skill file outside the arm's install (cursor/plugins#877)."""
from pathlib import PurePosixPath, Path

from .transcript import Transcript


def _under(path: PurePosixPath, root: Path) -> bool:
    return path == PurePosixPath(root) or PurePosixPath(root) in path.parents


def _skill_names(plugin_root: Path) -> set[str] | None:
    skills = plugin_root / "skills"
    return {d.name for d in skills.iterdir() if d.is_dir()} if skills.is_dir() else None


def violations(t: Transcript, *, plugin_root: Path, forbidden: list[Path]) -> list[str]:
    names = _skill_names(plugin_root)
    found = []
    for raw in t.reads:
        path = PurePosixPath(raw)
        if any(_under(path, root) for root in forbidden):
            found.append(f"read a forbidden path: {raw}")
            continue
        parts = path.parts
        for i, part in enumerate(parts[:-1]):
            if part == "skills" and (names is None or parts[i + 1] in names):
                if not _under(path, plugin_root):
                    found.append(f"read a skill outside the installed arm: {raw}")
                break
    return found
