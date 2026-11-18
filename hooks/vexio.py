"""stdin/stdout plumbing shared by the vex-mode hooks (agy hook contract: JSON in, JSON out)."""
import json
import os
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


def is_active(state: Path, conversation_id: str) -> bool:
    return bool(conversation_id) and (state / "active" / conversation_id).exists()


def safe_main(handler, fallback) -> None:
    try:
        emit(handler())
    except Exception:
        emit(fallback)
