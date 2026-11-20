"""Stop: in an active /vex-mode conversation, ask once per user turn for verification evidence.

The "already asked" state is kept on disk, keyed by conversation and by the user's message,
so the gate does not depend on agy's continuationActive/executionNum (agy 1.5.11 keeps
continuationActive false; see docs/decisions/2026-11-18-m1-verification.md).
"""
import hashlib
from pathlib import Path

from vexio import is_active, is_claude_code, read_payload, safe_id, safe_main, session_of, state_dir

REASON = (
    "vex-mode: before finishing, show verification evidence from the real artifact "
    "(command + output), or state why none applies."
)


def _turn_key(payload: dict) -> str:
    return hashlib.sha256(str(payload.get("lastUserInput") or "").encode()).hexdigest()


def claude_code(payload: dict, state: Path) -> dict | None:
    """Block once per user prompt; `prompt_id` keys the turn and `stop_hook_active` marks a continuation."""
    conv = session_of(payload)
    key = payload.get("prompt_id")
    if conv is None or not is_active(state, conv) or payload.get("stop_hook_active") or not isinstance(key, str) or not key:
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
