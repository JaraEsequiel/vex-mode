#!/usr/bin/env python3
"""Stand-in for agy in harness tests. State lives in $FAKE_HOME; behavior is set by $FAKE_AGY_MODE."""
import json
import os
import re
import shutil
import sys
from pathlib import Path

HOME = Path(os.environ["FAKE_HOME"])
PLUGINS = Path(os.environ["VEX_PLUGIN_HOME"])
MODE = os.environ.get("FAKE_AGY_MODE", "ok")


def bump(name: str) -> int:
    f = HOME / name
    n = int(f.read_text()) + 1 if f.exists() else 1
    f.write_text(str(n))
    return n


def emit(event: dict) -> None:
    print(json.dumps(event), flush=True)


def main(argv: list[str]) -> int:
    with open(HOME / "calls.log", "a") as log:
        log.write(" ".join(argv[:2]) + "\n")
    if argv[:2] == ["plugin", "uninstall"]:
        shutil.rmtree(PLUGINS / "vex-mode", ignore_errors=True)
        return 0
    if argv[:2] == ["plugin", "install"]:
        n = bump("installs")
        if MODE == "badinstall" and n == 2:
            return 3
        shutil.rmtree(PLUGINS / "vex-mode", ignore_errors=True)
        shutil.copytree(argv[2], PLUGINS / "vex-mode")
        return 0
    prompt = argv[argv.index("-p") + 1]
    if "--json-schema" in argv:
        with open(HOME / "judge-args.log", "a") as log:
            log.write(f"{len(prompt)}\n")
        ref = re.match(r"Read the file (\S+) in full", prompt)
        if ref:
            prompt = Path(ref.group(1)).read_text()
        labels = re.findall(r"^## (R\d+)$", prompt, re.M)
        if MODE == "badjudge":
            labels = labels[:-1]
        runs = [{"label": l, "criteria": [{"name": "c1", "pass": True, "note": "ok"}]} for l in labels]
        print(json.dumps({"status": "SUCCESS", "structured_output": {"runs": runs}}))
        return 0
    n = bump("candidates")
    model = argv[argv.index("--model") + 1]
    emit({"event": "init", "conversation_id": f"c{n}", "init": {"model": model, "cwd": os.getcwd()}})
    if MODE == "fail":
        return 1
    if MODE == "crash" and n == 2:
        return 1
    if MODE == "sigterm" and n == 2:
        import signal
        os.kill(int(os.environ["FAKE_PARENT"]), signal.SIGTERM)
        import time
        time.sleep(2)
        return 1
    if MODE == "ls":
        with open(HOME / "ls.log", "a") as f:
            f.write("\n".join(sorted(os.listdir(".."))) + "\n")
    skill = next((PLUGINS / "vex-mode/skills").glob("*/SKILL.md"))
    emit({"event": "step_update", "step_update": {"step_type": "tool", "state": "DONE",
          "tool_info": {"name": "read_file", "parameters": {"Path": str(skill)}}}})
    if MODE == "peek":
        emit({"event": "step_update", "step_update": {"step_type": "tool", "state": "DONE",
              "tool_info": {"name": "read_file", "parameters": {"Path": os.environ["FAKE_PEEK"]}}}})
    if MODE not in ("noop", "trail"):
        Path("app.py").write_text("fixed\n" + ("x = 1\n" * 60000 if MODE == "big" else ""))
    if MODE in ("commit", "commit-trail"):
        import subprocess
        env = dict(os.environ, GIT_AUTHOR_NAME="a", GIT_AUTHOR_EMAIL="a@a", GIT_COMMITTER_NAME="a", GIT_COMMITTER_EMAIL="a@a")
        subprocess.run(["git", "commit", "-qam", "fix"], check=True, env=env)
    if MODE in ("trail", "commit-trail"):
        Path("docs/decisions").mkdir(parents=True, exist_ok=True)
        Path("docs/decisions/2026-01-01-correct.tsv").write_text("ts\tphase\n")
    emit({"event": "result", "result": {"conversation_id": f"c{n}", "status": "SUCCESS", "response": "done",
          "duration_seconds": 1.5, "usage": {"total_tokens": 100 * n}}})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
