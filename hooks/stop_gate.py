"""Stop: in an active /vex-mode conversation, ask once per user turn for verification evidence.

The "already asked" state is kept on disk, keyed by conversation and by the user's message,
so the gate does not depend on agy's continuationActive/executionNum (agy 1.5.11 keeps
continuationActive false; see docs/decisions/2026-11-18-m1-verification.md).
"""
import hashlib
from pathlib import Path

from vexio import is_active, read_payload, safe_id, safe_main, state_dir

REASON = (
    "vex-mode: before finishing, show verification evidence from the real artifact "
    "(command + output), or state why none applies."
)


def _turn_key(payload: dict) -> str:
    return hashlib.sha256(str(payload.get("lastUserInput") or "").encode()).hexdigest()


def handle(payload: dict, state: Path) -> dict:
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
