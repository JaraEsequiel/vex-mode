"""Reads that invalidate a run (cursor/plugins#877, design §8.2).

A run is invalid when its parent conversation reads, by read_file or through a shell command:
anything under a forbidden root (the eval cache, the repo), another run's project copy, any
`evals/` folder, or a skill file outside the arm's install. A run owns its whole private folder
(`vex-work/<token>/`), not only its workdir: a worktree it adds next to the workdir is its own. Subagent reads are not visible
(separate conversations; see docs/decisions/2026-11-18-m2-first-eval.md).
"""
import os
import re
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
    if workdir is not None and _under(path, workdir):  # the run's own fresh copy of the project
        return None
    if "evals" in path.parts:
        return "an evals folder"
    parts = path.parts
    for i, part in enumerate(parts[:-1]):
        if part == "skills" and (names is None or parts[i + 1] in names):
            return None if _under(path, plugin_root) else "a skill outside the installed arm"
    return None


def _own_folder(workdir: Path | None, work_root: Path | None) -> Path | None:
    """The run's private folder under work_root (vex-work/<token>/), which holds its workdir and nothing of other runs."""
    if workdir is None or work_root is None:
        return workdir
    path, root = _norm(str(workdir), None, None), PurePosixPath(os.path.normpath(str(work_root)))
    if root not in path.parents:
        return workdir
    return Path(str(root / path.relative_to(root).parts[0]))


def violations(t: Transcript, *, plugin_root: Path, forbidden: list[Path], workdir: Path | None = None,
               work_root: Path | None = None, home: Path | None = None, cache: Path | None = None) -> list[str]:
    names = _skill_names(plugin_root)
    roots = list(forbidden) + ([cache / "vex-mode"] if cache is not None else [])
    own = _own_folder(workdir, work_root)
    ctx = dict(plugin_root=plugin_root, forbidden=roots, workdir=own, work_root=work_root, names=names)
    found = []
    for raw in t.reads:
        if problem := _path_problem(_norm(raw, workdir, home), **ctx):
            found.append(f"read {problem}: {raw}")
    for cmd in t.commands:
        # the run's own folder is allowed; the lookahead keeps a longer name (another token) intact
        mine = re.sub(re.escape(str(own)) + r"(?![\w.-])", ".", cmd) if own is not None else cmd
        if any(m in mine for m in SHELL_MARKERS):
            found.append(f"command touches eval files: {cmd}")
            continue
        if problem := _command_problem(cmd, workdir, home, ctx):
            found.append(f"command reaches {problem}: {cmd}")
    return found


def _segments(cmd: str) -> list[list[str]]:
    try:
        lexer = shlex.shlex(cmd, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:  # unbalanced quotes (a heredoc with an apostrophe): still cut at the separators
        tokens = re.findall(r"[^\s;&|()]+|[;&|()]+", cmd)
    segments, current = [], []
    for tok in tokens:
        if tok and all(c in "&|;()" for c in tok):
            segments.append(current)
            current = []
        else:
            current.append(tok)
    return [*segments, current]


CODE_PUNCTUATION = "[]{}<>,'\""  # around a path in code (a heredoc, `python -c`), not part of it
ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
SHELLS = {"bash", "sh", "zsh", "dash"}
WRAPPERS = {"command", "nohup", "time", "exec", "builtin"}
WRAPPER_ARGS = {
    "sudo": {"-u", "-g", "-C", "-h", "-p", "-U"},
    "env": {"-u", "-C", "-S"},
    "xargs": {"-I", "-n", "-P", "-d", "-L", "-s", "-E", "-a"},
}
MAX_SHELL_DEPTH = 5


def _expand(token: str, env: dict[str, str]) -> str:
    return re.sub(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", lambda m: env.get(m.group(1), m.group(0)), token)


def _check_path_token(raw: str, cwd: Path | None, home: Path | None, env: dict[str, str], ctx: dict) -> str | None:
    token = _expand(raw, env).strip(CODE_PUNCTUATION)
    if "$" in token or "`" in token:  # a shell expansion is not a path we can resolve
        return None
    if "/" not in token and token not in ("..", "~"):
        return None
    if cwd is None and not token.startswith(("/", "~")):
        return None
    return _path_problem(_norm(token, cwd, home), **ctx)


def _record_assign(tok: str, env: dict[str, str]) -> bool:
    m = ASSIGN.match(tok)
    if not m:
        return False
    val = _expand(m.group(2), env)
    if "$" not in val and "`" not in val:
        env[m.group(1)] = val
    return True


def _unwrap(seg: list[str], env: dict[str, str]) -> tuple[list[str], dict[str, str]]:
    """Strip inline assignments and wrapper commands so nested shell / eval invocations surface."""
    seg_env = dict(env)
    rest = seg
    while rest:
        head = os.path.basename(rest[0])
        if _record_assign(rest[0], seg_env):
            rest = rest[1:]
        elif head in WRAPPERS:
            rest = rest[1:]
        elif head in WRAPPER_ARGS:
            takes_arg = WRAPPER_ARGS[head]
            rest = rest[1:]
            while rest and (rest[0].startswith("-") or (head == "env" and ASSIGN.match(rest[0]))):
                if head == "env" and _record_assign(rest[0], seg_env):
                    rest = rest[1:]
                else:
                    rest = rest[2:] if rest[0] in takes_arg else rest[1:]
        else:
            break
    return rest, seg_env


def _command_problem(cmd: str, workdir: Path | None, home: Path | None, ctx: dict,
                     *, env: dict[str, str] | None = None, depth: int = 0) -> str | None:
    """Resolve path-like tokens against the directory a simple `cd X &&` chain leaves the shell in.
    `NAME=value` assignments (standalone, `export`, or inline) are expanded and their values checked;
    wrapped `bash/sh -c` and `eval` strings are inspected recursively up to MAX_SHELL_DEPTH; after a `cd`
    to a place that cannot be resolved, relative paths are not judged (absolute ones still are)."""
    if depth > MAX_SHELL_DEPTH:
        return "a deeply nested shell command"
    cwd, cur_env = workdir, dict(env or {})
    for seg in _segments(cmd):
        if not seg:
            continue
        if seg[0] == "export":
            for tok in seg[1:]:
                _record_assign(tok, cur_env)
            rest, seg_env = seg, cur_env
        elif all(ASSIGN.match(tok) for tok in seg):
            for tok in seg:
                _record_assign(tok, cur_env)
            rest, seg_env = [], cur_env
        else:
            rest, seg_env = _unwrap(seg, cur_env)
        for raw in seg:
            if m := ASSIGN.match(raw):
                if problem := _check_path_token(m.group(2), cwd, home, seg_env, ctx):
                    return problem
            if problem := _check_path_token(raw, cwd, home, seg_env, ctx):
                return problem
        if rest:
            head, args = os.path.basename(rest[0]), rest[1:]
            if head in SHELLS:
                for i, a in enumerate(args[:-1]):
                    if re.fullmatch(r"-[a-zA-Z]*c[a-zA-Z]*", a):
                        if problem := _command_problem(args[i + 1], cwd, home, ctx, env=seg_env, depth=depth + 1):
                            return problem
                        break
            elif head == "eval" and args:
                if problem := _command_problem(" ".join(args), cwd, home, ctx, env=seg_env, depth=depth + 1):
                    return problem
            elif len(rest) == 2 and rest[0] == "cd":
                target = _expand(rest[1], seg_env)
                cwd = None if "$" in target or "`" in target or (cwd is None and not target.startswith(("/", "~"))) \
                    else Path(str(_norm(target, cwd, home)))
    return None
