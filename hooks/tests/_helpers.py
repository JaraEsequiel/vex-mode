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


def stop(conv="c1", reason="NO_TOOL_CALL", continuation=False):
    return {"hookEventName": "Stop", "conversationId": conv, "terminationReason": reason, "continuationActive": continuation, "executionNum": 1}
