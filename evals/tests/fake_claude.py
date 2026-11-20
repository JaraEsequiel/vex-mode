#!/usr/bin/env python3
"""Stand-in for `claude -p` in harness tests. Logs its argv to $FAKE_HOME/claude-args.log; $FAKE_CLAUDE_MODE sets behavior."""
import json
import os
import sys
from pathlib import Path

HOME = Path(os.environ["FAKE_HOME"])
MODE = os.environ.get("FAKE_CLAUDE_MODE", "ok")


def emit(event: dict) -> None:
    print(json.dumps(event), flush=True)


def tool(call_id: str, name: str, params: dict, parent: str | None = None) -> None:
    emit({"type": "assistant", "parent_tool_use_id": parent,
          "message": {"id": f"m{call_id}", "usage": {"input_tokens": 10, "output_tokens": 5},
                      "content": [{"type": "tool_use", "id": call_id, "name": name, "input": params}]}})


def main(argv: list[str]) -> int:
    with open(HOME / "claude-args.log", "a") as log:
        log.write(json.dumps(argv) + "\n")
    tree = Path(argv[argv.index("--plugin-dir") + 1])
    model = argv[argv.index("--model") + 1]
    emit({"type": "system", "subtype": "init", "session_id": "s1", "model": model, "cwd": os.getcwd()})
    skill = next((tree / "skills").glob("*/SKILL.md"))
    tool("t1", "Read", {"file_path": str(skill)})
    if MODE == "peek":
        tool("t2", "Agent", {"subagent_type": "vex-mode:vex-agent", "prompt": "x"})
        tool("t3", "Grep", {"pattern": "x", "path": os.environ["FAKE_PEEK"]}, parent="t2")
    if MODE == "crash":
        return 1
    if MODE == "quota":
        emit({"type": "result", "subtype": "success", "is_error": True, "result": "Claude usage limit reached",
              "api_error_status": 429, "session_id": "s1"})
        return 1
    if MODE == "crashA" and "/A" in str(tree):
        return 1
    Path("app.py").write_text("fixed\n")
    if MODE == "gate":
        emit({"type": "assistant", "parent_tool_use_id": None, "message": {"content": [{"type": "text", "text": "Fixed it: the reply."}]}})
        emit({"type": "user", "message": {"content": [{"type": "text", "text": "Stop hook feedback:\nvex-mode: evidence"}]}})
    emit({"type": "result", "subtype": "success", "is_error": False, "result": "done", "duration_ms": 1500,
          "total_cost_usd": 0.05, "session_id": "s1",
          "modelUsage": {model: {"inputTokens": 40, "outputTokens": 60, "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0}}})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
