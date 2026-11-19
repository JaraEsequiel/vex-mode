"""Parse `agy -p --output-format stream-json` output (shapes probed on agy 1.5.11, design §8.2)."""
import json
import re
from dataclasses import dataclass, field


@dataclass
class Transcript:
    conversation_id: str | None = None
    model: str | None = None
    reads: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    status: str = "UNFINISHED"
    total_tokens: int = 0
    duration_s: float = 0.0
    response: str = ""


def parse(text: str) -> Transcript:
    t = Transcript()
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("event")
        if kind == "init":
            t.model = event["init"].get("model")
            t.conversation_id = event.get("conversation_id")
        elif kind == "step_update":
            step = event["step_update"]
            if step.get("step_type") != "tool" or step.get("state") != "DONE":
                continue
            info = step.get("tool_info") or {}
            params = info.get("parameters") or {}
            name = info.get("name") or "?"
            if name == "read_file" and "Path" in params:
                t.steps.append(f"read_file: {params['Path']}")
            elif name == "run_command" and "CommandLine" in params:
                code = re.search(r"exited with code (-?\d+)", str(info.get("output") or ""))
                suffix = f" (exit {code.group(1)})" if code else ""
                t.steps.append(f"run_command: {params['CommandLine']}{suffix}")
            else:
                t.steps.append(f"{name}: {json.dumps(params)[:300]}")
            if name == "read_file" and "Path" in params:
                t.reads.append(params["Path"])
            elif name == "run_command" and "CommandLine" in params:
                t.commands.append(params["CommandLine"])
        elif kind == "result":
            result = event["result"]
            t.status = result.get("status") or "UNKNOWN"
            t.total_tokens = int((result.get("usage") or {}).get("total_tokens") or 0)
            t.duration_s = float(result.get("duration_seconds") or 0.0)
            t.response = result.get("response") or ""
            t.conversation_id = result.get("conversation_id", t.conversation_id)
    return t
