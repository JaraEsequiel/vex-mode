"""agy Stop hook: when the agent is about to finish with changes that are not pushed (uncommitted, or
commits no remote has), run the repo's check and, if it fails, send the error back so the agent fixes
it first.

Lives in <repo>/.agents/ and runs with that folder as cwd:
    python3 check_on_stop.py ../scripts/check

Prints nothing to let the agent stop: a normal finish with nothing unpushed, a passing check, a
cancel or error, odd input, or after 3 tries for the same user message. It never raises: a broken
hook must not trap the agent. A check that cannot run or hangs counts as a failure.
"""
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_CONTINUES = 3
TAIL_LINES = 60
TAIL_CHARS = 8000
TIMEOUT_S = int(os.environ.get("AGENT_READY_CHECK_TIMEOUT", "240"))  # below the hook's 300 s timeout


def _counter(root: Path, conversation: str, prompt: str) -> Path:
    key = hashlib.sha1(f"{root}\0{conversation}\0{prompt}".encode()).hexdigest()[:20]
    return Path(tempfile.gettempdir()) / "agent-ready" / key


def _git(root: Path, *args: str) -> str | None:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def _has_unpushed_changes(root: Path) -> bool:
    status = _git(root, "status", "--porcelain")
    if status is None:
        return False
    if status.strip():
        return True
    return bool((_git(root, "rev-list", "-n", "1", "HEAD", "--not", "--remotes") or "").strip())


def _run_check(check: list[str], root: Path) -> tuple[int, str]:
    try:
        proc = subprocess.Popen(check, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                start_new_session=True)
    except OSError as e:
        return 126, f"could not run {check[0]}: {e}"
    try:
        out, _ = proc.communicate(timeout=TIMEOUT_S)
        return proc.returncode, out.decode(errors="replace")
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out, _ = proc.communicate()
        return 124, f"check timed out after {TIMEOUT_S} s\n" + out.decode(errors="replace")


def decide(payload: dict, check: list[str], root: Path) -> dict | None:
    conversation = payload.get("conversationId")
    if not isinstance(conversation, str) or not conversation:
        return None
    if payload.get("terminationReason") != "NO_TOOL_CALL":
        return None
    if not _has_unpushed_changes(root):
        return None
    prompt = payload.get("lastUserInput") if isinstance(payload.get("lastUserInput"), str) else ""
    counter = _counter(root, conversation, prompt)
    try:
        used = int(counter.read_text())
    except (OSError, ValueError):
        used = 0  # missing or corrupt counter: start over
    if used >= MAX_CONTINUES:
        return None
    code, output = _run_check(check, root)
    if code == 0:
        return None
    counter.parent.mkdir(parents=True, exist_ok=True)
    counter.write_text(str(used + 1))
    tail = "\n".join(output.strip().splitlines()[-TAIL_LINES:])[-TAIL_CHARS:]
    return {"decision": "continue", "reason": f"{' '.join(check)} failed (exit {code}); fix it before finishing:\n{tail}"}


def main(argv: list[str]) -> None:
    try:
        payload = json.loads(sys.stdin.read() or "null")
        if not isinstance(payload, dict) or not argv:
            return
        here = Path(__file__).absolute().parent  # not resolve(): a symlinked hook keeps .agents/ as its home
        root = here.parent
        check = [str((here / a).resolve()) if a.startswith(("./", "../")) else a for a in argv]
        out = decide(payload, check, root)
        if out:
            print(json.dumps(out))
    except Exception:  # noqa: BLE001 - see module docstring
        return


if __name__ == "__main__":
    main(sys.argv[1:])
