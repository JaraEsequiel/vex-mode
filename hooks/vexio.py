"""stdin/stdout plumbing shared by the vex-mode hooks: JSON in, JSON out, for agy and Claude Code.

Each hook tells the two apart by the payload: Claude Code sends `hook_event_name` and `session_id`,
agy sends `hookEventName` and `conversationId` (docs/decisions/2026-11-19-claude-code-probes.md)."""
import json
import os
import re
import sys
from pathlib import Path


def read_payload() -> dict:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def emit(obj: dict | None) -> None:
    """None means 'no opinion': print nothing. For PreToolUse, `{}` would deny the tool."""
    if obj is not None:
        sys.stdout.write(json.dumps(obj))


def is_claude_code(payload: dict) -> bool:
    return "hook_event_name" in payload and "session_id" in payload


def session_of(payload: dict) -> str | None:
    """The conversation id of either harness, if it is safe to use as a file name."""
    return safe_id(payload.get("session_id") if is_claude_code(payload) else payload.get("conversationId"))


def plugin_root() -> Path:
    root = os.environ.get("PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
    return Path(root or Path(__file__).resolve().parents[1])


def state_dir() -> Path:
    data = os.environ.get("PLUGIN_DATA") or os.environ.get("CLAUDE_PLUGIN_DATA")
    return Path(data) / "state" if data else plugin_root() / ".state"


SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")


def safe_id(conversation_id) -> str | None:
    """conversationId is used as a file name; anything but a plain id is treated as inactive."""
    if isinstance(conversation_id, str) and SAFE_ID.fullmatch(conversation_id):
        return conversation_id
    return None


def is_active(state: Path, conversation_id) -> bool:
    conv = safe_id(conversation_id)
    return conv is not None and (state / "active" / conv).exists()


def safe_main(handler, fallback) -> None:
    try:
        emit(handler())
    except Exception:
        emit(fallback)
