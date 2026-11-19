"""Weekly unattended `/correct` run on this repo (design §9.5). The agent does the work; this only
prepares a worktree, runs agy once, keeps the transcript and tells the user.

    python3 scripts/scheduled_correct.py run [--repo DIR] [--no-pr] [--base REF]
    python3 scripts/scheduled_correct.py install | uninstall

Environment: VEX_AGY (agy command), VEX_CORRECT_MODEL (default gemini-4-neon-high),
VEX_NOTIFY (default notify-send).
"""
import argparse
import datetime as dt
import fcntl
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_plugin import agy_command  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
STATE = Path.home() / ".cache/vex-mode/correct"
UNIT_DIR = Path.home() / ".config/systemd/user"
DEFAULT_MODEL = "gemini-4-neon-high"


def build_prompt(since: str) -> str:
    today = dt.date.today().isoformat()
    return f"""/correct
This is the weekly unattended run on the vex-mode repo, in this worktree. Nobody is watching: never ask a question; make the choice you can undo and say why.

1. Read `AGENTS.md` first.
2. Mine the mistakes since {since}: `git log --since={since}` (reverts included), and the PRs and review comments updated since then (`gh pr list --state all --search "updated:>={since}"`, `gh pr view <n> --comments`). A class counts once it has happened twice. If none has, make no commits and end with a report.
3. Keep a decision trail with the **show-me-your-work** skill at `docs/decisions/{today}-correct.tsv`, and commit it.
4. For a change to `skills/`, `hooks/`, `rules/`, `agents/`, `hooks.json` or `plugin.json`, follow `AGENTS.md` "How to change a skill", including the eval run and its verdict, so the change carries its result.
5. Run the verify command from `AGENTS.md` before each commit.
6. If you committed a fix, write the PR title on the first line of `.scratch/pr.md` and the body below it, following the Opening a PR playbook of the **vex-mode** skill.

Commit only: never push and never open a PR; the script that started you pushes this branch and opens the PR after you finish. Never merge: the user merges. A command the pause hook stops is not run, and in this headless run a paused command ends this run, so commit the trail after each row you add and avoid `rm -rf` on absolute paths. Keep scratch files in `.scratch/` in this worktree; git ignores it.
"""


def render_units(script: Path, repo: Path, *, path: str, agy: str) -> dict[str, str]:
    return {
        "vex-correct.service": f"""[Unit]
Description=vex-mode weekly unattended /correct run

[Service]
Type=oneshot
Environment=PATH={path}
Environment=VEX_AGY={agy}
ExecStart=/usr/bin/python3 {script} run --repo {repo}
""",
        "vex-correct.timer": """[Unit]
Description=Weekly vex-mode /correct run

[Timer]
OnCalendar=Sun *-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
""",
    }


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], check=check, capture_output=True, text=True)


def _notify(summary: str) -> None:
    cmd = shlex.split(os.environ.get("VEX_NOTIFY", "notify-send"))
    if not shutil.which(cmd[0]):
        return
    subprocess.run([*cmd, "vex-mode correct", summary], capture_output=True)


def _finished(transcript: Path) -> bool:
    for line in transcript.read_text().splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("event") == "result":
            return (event.get("result") or {}).get("status") == "SUCCESS"
    return False


def _new_branch(repo: Path, day: str) -> str:
    name, n = f"correct/{day}", 1
    while _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}", check=False).returncode == 0:
        n += 1
        name = f"correct/{day}-{n}"
    return name


def _plugin_home() -> Path:
    return Path(os.environ.get("VEX_PLUGIN_HOME", Path.home() / ".gemini/config/plugins"))


def _cache() -> Path:
    return Path(os.environ.get("VEX_CACHE", Path.home() / ".cache"))


def _preflight() -> str | None:
    """Refuse unless the installed plugin can run /correct and guards merges, and no eval swapped it."""
    plugin = _plugin_home() / "vex-mode"
    if not (plugin / "skills/correct/SKILL.md").is_file():
        return "the installed vex-mode plugin has no correct skill"
    probe = subprocess.run(
        [sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import irreversible; "
         "sys.exit(0 if irreversible.classify('gh pr merge 1') else 1)", str(plugin / "hooks")],
        capture_output=True)
    if probe.returncode != 0:
        return "the installed pause hook does not block merges"
    evals = _cache() / "vex-mode"
    if (evals / "restore-pending").exists():
        return "an eval left a variant installed (run python3 evals/run.py restore)"
    if (evals / "eval.lock").exists():
        with open(evals / "eval.lock") as held:
            try:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return "an eval is running and has swapped the installed plugin"
    return None


def _dirty_outside_trail(worktree: Path) -> bool:
    lines = _git(worktree, "status", "--porcelain", "--untracked-files=all").stdout.splitlines()
    return any(not line[3:].startswith(("docs/decisions/", ".scratch/")) for line in lines if line.strip())


def _open_pr(worktree: Path, branch: str) -> str:
    _git(worktree, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")
    gh = shlex.split(os.environ.get("VEX_GH", "gh"))
    pr = worktree / ".scratch/pr.md"
    if pr.is_file() and pr.read_text().strip():
        title, _, body = pr.read_text().strip().partition("\n")
        text = ["--title", title.strip(), "--body", body.strip() or title.strip()]
    else:
        text = ["--fill"]
    out = subprocess.run([*gh, "pr", "create", "--base", "main", "--head", branch, *text],
                         cwd=worktree, check=True, capture_output=True, text=True)
    return out.stdout.strip()


def _save_trail(worktree: Path, state: Path) -> None:
    """Keep a copy of the run's trail outside the worktree, which may be removed."""
    for trail in (worktree / "docs/decisions").glob("*-correct.tsv"):
        shutil.copyfile(trail, state / f"{worktree.name.removeprefix('wt-')}-correct.tsv")


def _commit_trail(worktree: Path) -> None:
    """A headless run can end before it commits its trail (a paused command ends the turn)."""
    if not _git(worktree, "status", "--porcelain", "--", "docs/decisions").stdout.strip():
        return
    _git(worktree, "add", "--", "docs/decisions")
    _git(worktree, "commit", "-q", "-m", "docs(decisions): commit the correct run's trail")


def run(repo: Path, *, state: Path, model: str, days: int = 7, timeout_s: int = 14400,
        open_pr: bool = True, base: str = "origin/main") -> int:
    state.mkdir(parents=True, exist_ok=True)
    lock = open(state / "run.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        print("another scheduled correct run holds the lock", file=sys.stderr)
        return 2
    try:
        refusal = _preflight()
        if refusal:
            _notify(f"refused: {refusal}")
            return 3
        return _run(repo, state, model, days, timeout_s, open_pr, base)
    except Exception as e:  # noqa: BLE001 - an unattended run must always tell the user
        _notify(f"failed: {e}")
        return 1
    finally:
        lock.close()


def _run(repo: Path, state: Path, model: str, days: int, timeout_s: int, open_pr: bool, base: str) -> int:
    today = dt.date.today()
    _git(repo, "fetch", "-q", "origin")
    branch = _new_branch(repo, today.isoformat())
    worktree = state / ("wt-" + branch.split("/", 1)[1])
    _git(repo, "worktree", "add", "-q", "--no-track", "-b", branch, str(worktree), base)
    (worktree / ".scratch").mkdir()
    (worktree / ".scratch/.gitignore").write_text("*\n")
    transcript = state / (worktree.name.removeprefix("wt-") + ".ndjson")
    since = (today - dt.timedelta(days=days)).isoformat()
    cmd = [*agy_command(), "--model", model, "--print-timeout", f"{timeout_s}s",
           "--output-format", "stream-json", "-p", build_prompt(since)]
    with open(transcript, "w") as out:
        env = {k: v for k, v in os.environ.items() if k not in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY")}
        code = subprocess.run(cmd, cwd=worktree, stdout=out, stderr=subprocess.STDOUT, env=env).returncode
    _save_trail(worktree, state)
    if code != 0 or not _finished(transcript):
        _notify(f"failed (exit {code}); worktree kept at {worktree}, transcript {transcript}")
        return 1
    if _dirty_outside_trail(worktree):
        _notify(f"failed: the run ended with uncommitted changes; worktree kept at {worktree}")
        return 1
    ahead = int(_git(worktree, "rev-list", "--count", f"{base}..HEAD").stdout.strip())
    if ahead == 0:
        _git(repo, "worktree", "remove", "--force", str(worktree))
        _git(repo, "branch", "-D", branch)
        _notify(f"no repeated mistake found; transcript {transcript}")
        return 0
    _commit_trail(worktree)
    where = _open_pr(worktree, branch) if open_pr else f"worktree {worktree}"
    _notify(f"{ahead} commit(s) on {branch}: {where}")
    return 0


def install(units: dict[str, str]) -> None:
    UNIT_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in units.items():
        (UNIT_DIR / name).write_text(text)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", "vex-correct.timer"], check=True)


def uninstall() -> None:
    subprocess.run(["systemctl", "--user", "disable", "--now", "vex-correct.timer"], capture_output=True)
    for name in ("vex-correct.service", "vex-correct.timer"):
        (UNIT_DIR / name).unlink(missing_ok=True)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--repo", type=Path, default=REPO)
    r.add_argument("--no-pr", action="store_true")
    r.add_argument("--base", default="origin/main")
    r.add_argument("--state", type=Path, default=STATE)
    sub.add_parser("install")
    sub.add_parser("uninstall")
    args = parser.parse_args(argv)
    if args.cmd == "install":
        agy = shutil.which(agy_command()[0])
        if not agy:
            print("agy not found on PATH", file=sys.stderr)
            return 1
        install(render_units(Path(__file__).resolve(), REPO, path=os.environ["PATH"], agy=agy))
        return 0
    if args.cmd == "uninstall":
        uninstall()
        return 0
    return run(args.repo.resolve(), state=args.state, model=os.environ.get("VEX_CORRECT_MODEL", DEFAULT_MODEL),
               open_pr=not args.no_pr, base=args.base)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
