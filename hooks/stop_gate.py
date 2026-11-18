"""Stop: in an active /vex-mode conversation, ask once for verification evidence before finishing."""
from pathlib import Path

from vexio import is_active, read_payload, safe_main, state_dir

REASON = (
    "vex-mode: before finishing, show verification evidence from the real artifact "
    "(command + output), or state why none applies."
)


def handle(payload: dict, state: Path) -> dict:
    if not is_active(state, payload.get("conversationId") or ""):
        return {}
    already_continued = payload.get("continuationActive") or (payload.get("executionNum") or 0) > 0
    if already_continued or payload.get("terminationReason") != "NO_TOOL_CALL":
        return {}
    return {"decision": "continue", "reason": REASON}


if __name__ == "__main__":
    safe_main(lambda: handle(read_payload(), state_dir()), {})
