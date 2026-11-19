"""agy Stop hook: when the agent is about to finish with uncommitted changes, run the repo's check
and, if it fails, send the error back so the agent fixes it first.

Lives in <repo>/.agents/ and runs with that folder as cwd:
    python3 check_on_stop.py ../scripts/check

Prints nothing to let the agent stop (a clean tree, a passing check, odd input, or after 3 tries in
one conversation). It never raises: a broken hook must not trap the agent.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_CONTINUES = 3
TAIL_LINES = 60


def _counter(root: Path, conversation: str) -> Path:
    key = hashlib.sha1(str(root).encode()).hexdigest()[:12]
    safe = "".join(c for c in conversation if c.isalnum() or c in "-_")[:64]
    return Path(tempfile.gettempdir()) / "agent-ready" / f"{key}-{safe}"


def decide(payload: dict, check: list[str], root: Path) -> dict | None:
    conversation = payload.get("conversationId")
    if not isinstance(conversation, str) or not conversation:
        return None
    status = subprocess.run(["git", "-C", str(root), "status", "--porcelain"], capture_output=True, text=True)
    if status.returncode != 0 or not status.stdout.strip():
        return None
    counter = _counter(root, conversation)
    used = int(counter.read_text()) if counter.exists() else 0
    if used >= MAX_CONTINUES:
        return None
    try:
        run = subprocess.run(check, cwd=root, capture_output=True, text=True, timeout=600)
        code, output = run.returncode, run.stdout + run.stderr
    except FileNotFoundError:
        code, output = 127, f"{check[0]} not found"
    if code == 0:
        return None
    counter.parent.mkdir(parents=True, exist_ok=True)
    counter.write_text(str(used + 1))
    tail = "\n".join(output.strip().splitlines()[-TAIL_LINES:])
    return {"decision": "continue", "reason": f"{' '.join(check)} failed (exit {code}); fix it before finishing:\n{tail}"}


def main(argv: list[str]) -> None:
    try:
        payload = json.loads(sys.stdin.read() or "null")
        if not isinstance(payload, dict) or not argv:
            return
        here = Path(__file__).resolve().parent
        root = here.parent
        check = [str((here / argv[0]).resolve()) if argv[0].startswith(".") else argv[0], *argv[1:]]
        out = decide(payload, check, root)
        if out:
            print(json.dumps(out))
    except Exception:  # noqa: BLE001 - see module docstring
        return


if __name__ == "__main__":
    main(sys.argv[1:])
