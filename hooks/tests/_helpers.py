import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO = Path(__file__).resolve().parents[2]


def tmpdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="vexhook-"))


def pre_invocation(conv="c1", text="/vex-mode fix x"):
    return {"hookEventName": "PreInvocation", "conversationId": conv, "lastUserInput": text, "invocationNum": 1}


def run_command(cmd, conv="c1"):
    return {"hookEventName": "PreToolUse", "conversationId": conv, "toolCall": {"id": "t1", "name": "run_command", "args": {"CommandLine": cmd}}}


def stop(conv="c1", reason="NO_TOOL_CALL", continuation=False, execution=0, text="/vex-mode fix x"):
    return {"hookEventName": "Stop", "conversationId": conv, "terminationReason": reason, "continuationActive": continuation, "executionNum": execution, "lastUserInput": text}


# Claude Code payloads (docs/decisions/2026-11-19-claude-code-probes.md).
SESSION = "1fd4e2a1-692f-4f21-b4c6-8828c8942d77"


def cc_session_start(session=SESSION, source="startup"):
    return {"session_id": session, "hook_event_name": "SessionStart", "source": source, "cwd": "/tmp"}


def cc_prompt(text="/vex-mode:vex-mode fix x", session=SESSION, prompt_id="p1"):
    return {"session_id": session, "hook_event_name": "UserPromptSubmit", "prompt": text, "prompt_id": prompt_id, "cwd": "/tmp"}


def cc_bash(cmd, session=SESSION):
    return {"session_id": session, "hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": "/tmp"}


def cc_stop(session=SESSION, prompt_id="p1", active=False, transcript=None):
    payload = {"session_id": session, "hook_event_name": "Stop", "prompt_id": prompt_id, "stop_hook_active": active, "cwd": "/tmp"}
    if transcript is not None:
        payload["transcript_path"] = transcript
    return payload
