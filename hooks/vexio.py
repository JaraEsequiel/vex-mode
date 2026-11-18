"""stdin/stdout plumbing shared by the vex-mode hooks (agy hook contract: JSON in, JSON out)."""
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


def plugin_root() -> Path:
    return Path(os.environ.get("PLUGIN_ROOT") or Path(__file__).resolve().parents[1])


def state_dir() -> Path:
    data = os.environ.get("PLUGIN_DATA")
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
