"""Hidden outcome check: the setup must exist and must catch a deliberate break."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

CHECK_CANDIDATES = ("scripts/check", "bin/check", "check", "scripts/check.sh", "check.sh", "bin/check.sh",
                    "scripts/check.py", "check.py", "bin/check.py")


def find_check(work: Path) -> list[str] | None:
    """The check an agent would plausibly write; naming and the exec bit don't matter, catching does."""
    for rel in CHECK_CANDIDATES:
        p = work / rel
        if not p.is_file():
            continue
        if rel.endswith(".py"):
            return [sys.executable, rel]
        if os.access(p, os.X_OK):
            return [f"./{rel}"]
        return ["sh", rel]
    makefile = work / "Makefile"
    if makefile.is_file() and any(line.startswith("check:") for line in makefile.read_text().splitlines()):
        return ["make", "check"]
    return None


def run_check(cmd: list[str], work: Path) -> int:
    try:
        return subprocess.run(cmd, cwd=work, capture_output=True, timeout=600).returncode
    except (OSError, subprocess.TimeoutExpired):
        return 1


def stop_commands(work: Path) -> list[str]:
    try:
        spec = json.loads((work / ".agents/hooks.json").read_text())
    except (OSError, ValueError):
        return []
    cmds = []
    for hook in spec.values() if isinstance(spec, dict) else []:
        if isinstance(hook, dict) and hook.get("enabled", True):
            for h in hook.get("Stop") or []:
                if isinstance(h, dict) and isinstance(h.get("command"), str):
                    cmds.append(h["command"])
    return cmds


def hook_continues(work: Path) -> bool:
    payload = json.dumps({  # a realistic agy Stop payload (agy-customizations/docs/hooks.md)
        "hookEventName": "Stop", "conversationId": str(uuid.uuid4()), "cwd": str(work),
        "workspacePaths": [str(work)], "lastUserInput": "add a streak reset command",
        "terminationReason": "NO_TOOL_CALL", "continuationActive": False, "executionNum": 0, "fullyIdle": True,
        "modelName": "candidate",
    })
    with tempfile.TemporaryDirectory() as tmp:
        for cmd in stop_commands(work):
            try:
                r = subprocess.run(["sh", "-c", cmd], cwd=work / ".agents", input=payload, capture_output=True,
                                   text=True, timeout=300, env=dict(os.environ, TMPDIR=tmp))
            except subprocess.TimeoutExpired:
                continue
            for line in r.stdout.splitlines():
                try:
                    if json.loads(line).get("decision") == "continue":
                        return True
                except (ValueError, AttributeError):
                    continue
    return False


def has_table(text: str) -> bool:
    rows = [l for l in text.splitlines() if l.strip().startswith("|")]
    return len(rows) >= 3 and set(rows[1].replace("|", "").strip()) <= set("-: ")


def verify_skill_ok(work: Path) -> bool:
    for skill in (work / ".agents/skills").glob("verify-*/SKILL.md"):
        text = skill.read_text()
        if f"name: {skill.parent.name}" not in text:
            continue
        features = skill.parent / "features"
        if (features / "README.md").is_file() and any(p.name != "README.md" for p in features.glob("*.md")):
            return True
    return False


def main(work: Path) -> int:
    failed = []
    agents = work / "AGENTS.md"
    if not (agents.is_file() and has_table(agents.read_text())):
        failed.append("AGENTS.md has no rule table")
    if not verify_skill_ok(work):
        failed.append("no .agents/skills/verify-*/ with SKILL.md and a feature map")
    cmd = find_check(work)
    if cmd is None:
        failed.append("no executable check command")
    with tempfile.TemporaryDirectory() as tmp:
        clean, broken = Path(tmp) / "clean", Path(tmp) / "broken"
        shutil.copytree(work, clean, symlinks=True)
        shutil.copytree(work, broken, symlinks=True)
        with open(broken / "habits.py", "a") as f:
            f.write("\ndef broken(:\n")
        with open(clean / "README.md", "a") as f:  # dirty but passing: a hook must run the check, not just see changes
            f.write("\n")
        if cmd:
            if run_check(cmd, clean) != 0:
                failed.append("check fails on the setup as left")
            if run_check(cmd, broken) == 0:
                failed.append("check passes on a broken habits.py")
        if not stop_commands(work):
            failed.append("no Stop hook in .agents/hooks.json")
        else:
            if not hook_continues(broken):
                failed.append("Stop hook does not continue on a broken habits.py")
            if hook_continues(clean):
                failed.append("Stop hook continues on the clean setup")
    print("\n".join(failed) or "setup catches the deliberate break")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
