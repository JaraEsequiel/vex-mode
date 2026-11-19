"""Reads that invalidate a run (cursor/plugins#877, design §8.2).

A run is invalid when its parent conversation reads, by read_file or through a shell command:
anything under a forbidden root (the eval cache, the repo), another run's project copy, any
`evals/` folder, or a skill file outside the arm's install. Subagent reads are not visible
(separate conversations; see docs/decisions/2026-11-18-m2-first-eval.md).
"""
import os
import shlex
from pathlib import Path, PurePosixPath

from .transcript import Transcript

SHELL_MARKERS = ("vex-mode/runs", "vex-work", "/evals", "evals/")


def _norm(raw: str, workdir: Path | None, home: Path | None) -> PurePosixPath:
    if home is not None and (raw == "~" or raw.startswith("~/")):
        raw = str(home) + raw[1:]
    if not raw.startswith("/") and workdir is not None:
        raw = str(workdir / raw)
    return PurePosixPath(os.path.normpath(raw))


def _under(path: PurePosixPath, root: Path) -> bool:
    root = PurePosixPath(os.path.normpath(str(root)))
    return path == root or root in path.parents


def _skill_names(plugin_root: Path) -> set[str] | None:
    skills = plugin_root / "skills"
    return {d.name for d in skills.iterdir() if d.is_dir()} if skills.is_dir() else None


def _path_problem(path: PurePosixPath, *, plugin_root, forbidden, workdir, work_root, names) -> str | None:
    if any(_under(path, root) for root in forbidden):
        return "a forbidden path"
    if work_root is not None and _under(path, work_root) and not (workdir is not None and _under(path, workdir)):
        return "another project copy"
    if "evals" in path.parts:
        return "an evals folder"
    parts = path.parts
    for i, part in enumerate(parts[:-1]):
        if part == "skills" and (names is None or parts[i + 1] in names):
            return None if _under(path, plugin_root) else "a skill outside the installed arm"
    return None


def violations(t: Transcript, *, plugin_root: Path, forbidden: list[Path], workdir: Path | None = None,
               work_root: Path | None = None, home: Path | None = None, cache: Path | None = None) -> list[str]:
    names = _skill_names(plugin_root)
    roots = list(forbidden) + ([cache / "vex-mode"] if cache is not None else [])
    ctx = dict(plugin_root=plugin_root, forbidden=roots, workdir=workdir, work_root=work_root, names=names)
    found = []
    for raw in t.reads:
        if problem := _path_problem(_norm(raw, workdir, home), **ctx):
            found.append(f"read {problem}: {raw}")
    for cmd in t.commands:
        if any(m in cmd for m in SHELL_MARKERS):
            found.append(f"command touches eval files: {cmd}")
            continue
        try:
            tokens = shlex.split(cmd)
        except ValueError:
            tokens = cmd.split()
        for token in tokens:
            if "/" not in token and token not in ("..", "~"):
                continue
            if problem := _path_problem(_norm(token, workdir, home), **ctx):
                found.append(f"command reaches {problem}: {cmd}")
                break
    return found
