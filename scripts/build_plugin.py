"""Export only the plugin's parts, so an install never carries repo files (docs, evals, .git).

`agy plugin install <dir>` copies the whole folder (design §8.2), so install from this build:
    python3 scripts/build_plugin.py [--ref REF] [--install] <out>

`--harness claude-code` writes the Claude Code tree instead, the way pstack's
scripts/generate-pstack-harness-trees.mjs writes harness/pstack/claude-code. The tree is committed at
harness/claude-code/ and published by .claude-plugin/marketplace.json; `--check` fails when it is stale:
    python3 scripts/build_plugin.py --harness claude-code [--check] [harness/claude-code]
"""
import argparse
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

PLUGIN_PARTS = ("plugin.json", "skills", "agents", "rules", "hooks.json", "hooks", "LICENSES")
EXCLUDED_DIRS = {"__pycache__", "tests"}


def _excluded(rel: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in rel.parts[:-1])


def _copy_parts(src: Path, out: Path) -> None:
    _copy_parts_from(src, out, PLUGIN_PARTS)


def _copy_parts_from(src: Path, out: Path, parts: tuple[str, ...]) -> None:
    for part in parts:
        path = src / part
        if path.is_file():
            files = [path]
        elif path.is_dir():
            files = [p for p in path.rglob("*") if p.is_file()]
        else:
            continue
        for f in files:
            rel = f.relative_to(src)
            if _excluded(rel):
                continue
            dest = out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)


def build(repo_root: Path, out: Path, ref: str | None = None) -> Path:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    if ref is None:
        _copy_parts(repo_root, out)
        return out
    archive = subprocess.run(
        ["git", "-C", str(repo_root), "archive", "--format=tar", ref],
        check=True, capture_output=True,
    ).stdout
    with tempfile.TemporaryDirectory(prefix="vex-build-") as tmp:
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(tmp, filter="data")
        _copy_parts(Path(tmp), out)
    return out


CLAUDE_TREE = Path("harness/claude-code")
CLAUDE_PARTS = ("skills", "agents", "rules", "hooks", "adapters", "LICENSES")
ADAPTER = "adapters/claude-code.md"
COMMAND = "python3 scripts/build_plugin.py --harness claude-code"
# Agent frontmatter keys Claude Code understands; agy's subagent/mainAgent/tools (agy tool names) are dropped,
# so vex-agent gets every tool and the session model (docs/decisions/2026-11-19-claude-code-probes.md, finding 6).
AGENT_KEYS = ("name", "description")
# Each agy name a skill folder uses, and the text of the adapter row that maps it.
TERMS = [
    ("todolist", re.compile(r"\btodo ?list\b", re.I)),
    ("shows a person a question", re.compile(r"shows a person a question")),
    ("Run another vex-mode skill", re.compile(r"the \*\*[a-z0-9-]+\*\* skill|`/[a-z][a-z0-9-]+`")),
    ("`/vex-mode`", re.compile(r"`/vex-mode`|/vex-mode\b")),
    ("`vex-agent`", re.compile(r"vex-agent")),
    ("Run it in the background", re.compile(r"in the background")),
    ("another vendor's model", re.compile(r"another vendor's model|agy --model|agy models")),
    (".agents/skills/", re.compile(r"\.agents/skills")),
    ("~/.gemini/config/skills/", re.compile(r"\.gemini/config/skills")),
    ("~/.gemini/config/plugins/", re.compile(r"\.gemini/config/plugins")),
    ("the vex-mode `plugin.json`", re.compile(r"vex-mode `plugin\.json`")),
    ("transcript.jsonl", re.compile(r"transcript\.jsonl|antigravity-cli/brain")),
    (".agents/hooks.json", re.compile(r"\.agents/hooks\.json|\.agents/`")),
    ("`evals/run.py`", re.compile(r"`agy -p`")),
    ("agy hook template", re.compile(r"\bagy (Stop )?hook")),
    ("`Claude Code:` line", re.compile(r"^\s*- (agy|Claude Code):|agy or Claude Code")),
]
# A line naming agy that no term covers means the adapter is missing a row.
AGY = re.compile(r"\bagy\b|Antigravity|\.gemini|\.agents/")
README = f"""# vex-mode for Claude Code

This folder is generated from `skills/`, `agents/`, `rules/`, `hooks/`, `adapters/`, `LICENSES/` and `plugin.json`
of the vex-mode repo. Do not edit it by hand. After editing those sources, run `{COMMAND}` from the repository
root and commit the result. CI fails while this copy is out of date.

Install: `claude plugin marketplace add JaraEsequiel/vex-mode`, then `claude plugin install vex-mode@vex`.
Full mode: `/vex-mode:vex-mode`. The always-on core loads at session start.
"""


def _hook(script: str) -> list[dict]:
    return [{"type": "command", "command": f'python3 "${{CLAUDE_PLUGIN_ROOT}}/hooks/{script}"', "timeout": 10}]


# Claude Code events for the same hooks (docs/decisions/2026-11-19-claude-code-probes.md).
CLAUDE_HOOKS = {"hooks": {
    "SessionStart": [{"hooks": _hook("session_start.py")}],
    "UserPromptSubmit": [{"hooks": _hook("activate.py")}],
    "PreToolUse": [{"matcher": "Bash", "hooks": _hook("irreversible.py")}],
    "Stop": [{"hooks": _hook("stop_gate.py")}],
}}


class TreeError(Exception):
    pass


def _agent(text: str) -> str:
    _, front, body = text.split("---\n", 2)
    keep = [line for line in front.splitlines() if line.split(":", 1)[0] in AGENT_KEYS]
    return "---\n" + "\n".join(keep) + "\n---\n" + body


def _terms(folder: Path) -> tuple[set[str], list[str]]:
    used, unmapped = set(), []
    for path in sorted(folder.rglob("*.md")):
        for n, line in enumerate(path.read_text().splitlines(), 1):
            hits = {key for key, rx in TERMS if rx.search(line)}
            used |= hits
            if AGY.search(line) and not hits:
                unmapped.append(f"{path.name}:{n}")
    return used, unmapped


def render_claude(src: Path) -> dict[str, tuple[bytes, bool]]:
    """Every file of the Claude Code tree: relative path -> (bytes, executable)."""
    with tempfile.TemporaryDirectory(prefix="vex-cc-") as tmp:
        _copy_parts_from(src, Path(tmp), CLAUDE_PARTS)
        root = Path(tmp)
        adapter = (root / ADAPTER).read_text()
        problems = []
        for skill in sorted(p.parent for p in root.glob("skills/*/SKILL.md")):
            used, unmapped = _terms(skill)
            problems += [f"skills/{skill.name}/{u} names agy but no adapter row covers it" for u in unmapped]
            problems += [f"{ADAPTER} has no row for {key}, used by skills/{skill.name}" for key in sorted(used) if key not in adapter]
            if not used:
                continue
            md = skill / "SKILL.md"
            text = md.read_text()
            if not re.search(r"^# ", text, re.M):
                problems.append(f"skills/{skill.name}/SKILL.md uses agy names but has no H1")
                continue
            line = (f"In Claude Code, read [the Claude Code adapter](../../{ADAPTER}) once per session before you "
                    "follow this skill. It maps the agy names in vex-mode skills to Claude Code.")
            md.write_text(re.sub(r"^(# .*)\n+", lambda m: f"{m.group(1)}\n\n{line}\n\n", text, count=1, flags=re.M))
        if problems:
            raise TreeError("\n".join(problems))
        for agent in root.glob("agents/*.md"):
            agent.write_text(_agent(agent.read_text()))
        files = {p.relative_to(root).as_posix(): (p.read_bytes(), os.access(p, os.X_OK))
                 for p in sorted(root.rglob("*")) if p.is_file()}
    files["hooks/hooks.json"] = ((json.dumps(CLAUDE_HOOKS, indent=2) + "\n").encode(), False)
    files["README.md"] = (README.encode(), False)
    digest = hashlib.sha256()
    for path, (data, _) in sorted(files.items()):
        digest.update(path.encode() + b"\0" + data + b"\0")
    manifest = json.loads((src / "plugin.json").read_text())
    # Claude Code re-copies an installed plugin only when its version changes, so the version carries the content hash.
    manifest["version"] = f"{manifest.get('version', '0.0.0')}+{digest.hexdigest()[:12]}"
    files[".claude-plugin/plugin.json"] = ((json.dumps(manifest, indent=2) + "\n").encode(), False)
    return files


def _on_disk(tree: Path) -> dict[str, tuple[bytes, bool]]:
    if not tree.is_dir():
        return {}
    return {p.relative_to(tree).as_posix(): (p.read_bytes(), os.access(p, os.X_OK))
            for p in tree.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


def check_claude(src: Path, tree: Path) -> list[str]:
    """Paths where the committed tree differs from a fresh render."""
    want, have = render_claude(src), _on_disk(tree)
    return sorted(p for p in set(want) | set(have) if want.get(p) != have.get(p))


def write_claude(src: Path, tree: Path) -> Path:
    files = render_claude(src)
    if tree.exists():
        shutil.rmtree(tree)
    for rel, (data, executable) in files.items():
        dest = tree / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        dest.chmod(0o755 if executable else 0o644)
    return tree


def agy_command() -> list[str]:
    return shlex.split(os.environ.get("VEX_AGY", "agy"))


def uninstall() -> None:
    subprocess.run([*agy_command(), "plugin", "uninstall", "vex-mode"], capture_output=True)


def install(out: Path) -> None:
    uninstall()
    subprocess.run([*agy_command(), "plugin", "install", str(out)], check=True, capture_output=True)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path, nargs="?")
    parser.add_argument("--ref")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--harness", choices=("agy", "claude-code"), default="agy")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parents[1]
    if args.harness == "claude-code":
        tree = (args.out or repo / CLAUDE_TREE).resolve()
        try:
            if args.check:
                stale = check_claude(repo, tree)
                for p in stale[:20]:
                    print(f"{tree.name}/{p}")
                if stale:
                    print(f"{tree} is out of date. Run `{COMMAND}` and commit the result.")
                    return 1
                print(f"{tree} is up to date.")
                return 0
            print(write_claude(repo, tree))
            return 0
        except TreeError as e:
            print(e)
            return 1
    if args.out is None:
        parser.error("out is required for the agy build")
    out = build(Path(__file__).resolve().parents[1], args.out.resolve(), args.ref)
    if args.install:
        install(out)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
