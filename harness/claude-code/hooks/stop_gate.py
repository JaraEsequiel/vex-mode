"""Stop: in an active /vex-mode conversation, ask once per user turn for verification evidence.

The "already asked" state is kept on disk, keyed by conversation and by the user's message,
so the gate does not depend on agy's continuationActive/executionNum (agy 1.5.11 keeps
continuationActive false; see docs/decisions/2026-11-18-m1-verification.md).
In Claude Code the ask is skipped when the turn's last tool call ran a command.
"""
import hashlib
import json
from pathlib import Path

from vexio import is_active, is_claude_code, read_payload, safe_id, safe_main, session_of, state_dir

REASON = (
    "vex-mode: before finishing, show verification evidence from the real artifact "
    "(command + output), or state why none applies."
)


def _turn_key(payload: dict) -> str:
    return hashlib.sha256(str(payload.get("lastUserInput") or "").encode()).hexdigest()


def _turn_tools(transcript_path, prompt_id: str) -> list[str] | None:
    """The main agent's tool names in this prompt's turn, read from the Claude Code session file; None if unreadable.

    The turn starts at the first entry carrying `promptId` == the Stop payload's `prompt_id`; subagent
    entries (`isSidechain`) do not count."""
    try:
        lines = Path(transcript_path).read_text().splitlines()
        entries = [json.loads(line) for line in lines if line.strip()]
    except (OSError, TypeError, ValueError):
        return None
    start = next((i for i, e in enumerate(entries) if isinstance(e, dict) and e.get("promptId") == prompt_id), None)
    if start is None:
        return None
    names = []
    for e in entries[start:]:
        if not isinstance(e, dict) or e.get("type") != "assistant" or e.get("isSidechain"):
            continue
        content = (e.get("message") or {}).get("content")
        names += [c.get("name") for c in content or [] if isinstance(c, dict) and c.get("type") == "tool_use"]
    return names


def _ran_a_command_last(payload: dict, prompt_id: str) -> bool:
    """The turn's last tool call ran a command, so the agent checked after its last change (2026-11-20 calibration:
    the unconditional ask cost ~80k tokens a run, repeating checks the agent had already shown)."""
    tools = _turn_tools(payload.get("transcript_path"), prompt_id)
    return bool(tools) and tools[-1] == "Bash"


def claude_code(payload: dict, state: Path) -> dict | None:
    """Block once per user prompt, unless the turn's last tool call ran a command; `prompt_id` keys the turn
    and `stop_hook_active` marks a continuation."""
    conv = session_of(payload)
    key = payload.get("prompt_id")
    if conv is None or not is_active(state, conv) or payload.get("stop_hook_active") or not isinstance(key, str) or not key:
        return None
    if _ran_a_command_last(payload, key):
        return None
    asked = state / "asked" / conv
    if asked.exists() and asked.read_text() == key:
        return None
    asked.parent.mkdir(parents=True, exist_ok=True)
    asked.write_text(key)
    return {"decision": "block", "reason": REASON}


def handle(payload: dict, state: Path) -> dict | None:
    if is_claude_code(payload):
        return claude_code(payload, state)
    conv = safe_id(payload.get("conversationId"))
    if conv is None or not is_active(state, conv):
        return {}
    if payload.get("continuationActive") or payload.get("terminationReason") != "NO_TOOL_CALL":
        return {}
    asked = state / "asked" / conv
    key = _turn_key(payload)
    if asked.exists() and asked.read_text() == key:
        return {}
    asked.parent.mkdir(parents=True, exist_ok=True)
    asked.write_text(key)
    return {"decision": "continue", "reason": REASON}


if __name__ == "__main__":
    safe_main(lambda: handle(read_payload(), state_dir()), {})
