"""Parse `agy -p --output-format stream-json` output (shapes probed on agy 1.5.11, design §8.2) and
`claude -p --output-format stream-json --verbose` output (Claude Code 2.1.329,
docs/decisions/2026-11-19-claude-code-probes.md)."""
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
    step_tokens: int = 0
    duration_s: float = 0.0
    response: str = ""
    cost_usd: float = 0.0
    error: str = ""
    gate_reply: str = ""  # Claude Code: the reply the Stop hook interrupted to ask for evidence


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
            t.step_tokens += int((step.get("usage") or {}).get("total_tokens") or 0)
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
            t.error = str(result.get("error") or "")
            t.conversation_id = result.get("conversation_id", t.conversation_id)
    return t


def _claude_tokens(usage: dict) -> int:
    keys = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    return sum(int(usage.get(k) or 0) for k in keys)


def _claude_step(name: str, params: dict, is_error: bool, subagent: bool) -> str:
    if name == "Read" and "file_path" in params:
        text = f"Read: {params['file_path']}"
    elif name == "Bash" and "command" in params:
        text = f"Bash: {params['command']}" + (" (error)" if is_error else "")
    else:
        text = f"{name}: {json.dumps(params)[:300]}"
    return text + (" [subagent]" if subagent else "")


def parse_claude(text: str) -> Transcript:
    """Claude Code stream-json. Subagent tool calls carry `parent_tool_use_id` and count like the parent's."""
    t = Transcript()
    calls: list[tuple[str, str, dict, bool]] = []
    errors: set[str] = set()
    counted: set[str] = set()
    last_text, gated = "", False
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        content = (event.get("message") or {}).get("content")
        if kind == "system" and event.get("subtype") == "init":
            t.model = event.get("model")
            t.conversation_id = event.get("session_id")
        elif kind == "assistant" and isinstance(content, list):
            message = event.get("message") or {}
            if message.get("id") not in counted and isinstance(message.get("usage"), dict):
                counted.add(message.get("id"))
                t.step_tokens += _claude_tokens(message["usage"])
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text" and not event.get("parent_tool_use_id") and not gated:
                    last_text = c.get("text") or ""
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    params = c.get("input") if isinstance(c.get("input"), dict) else {}
                    calls.append((c.get("id") or "", c.get("name") or "?", params, bool(event.get("parent_tool_use_id"))))
        elif kind == "user" and isinstance(content, list):
            if not gated and any(isinstance(c, dict) and c.get("type") == "text"
                                 and str(c.get("text", "")).startswith("Stop hook feedback") for c in content):
                gated, t.gate_reply = True, last_text
            errors |= {c.get("tool_use_id") for c in content
                       if isinstance(c, dict) and c.get("type") == "tool_result" and c.get("is_error")}
        elif kind == "result":
            t.status = "SUCCESS" if event.get("subtype") == "success" and not event.get("is_error") \
                else ("ERROR" if event.get("subtype") == "success" else str(event.get("subtype") or "error").upper())
            per_model = event.get("modelUsage") or {}
            if per_model:
                t.total_tokens = sum(int(m.get(k) or 0) for m in per_model.values() for k in
                                     ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens"))
            else:
                t.total_tokens = _claude_tokens(event.get("usage") or {})
            t.duration_s = float(event.get("duration_ms") or 0) / 1000
            t.cost_usd = float(event.get("total_cost_usd") or 0.0)
            t.response = event.get("result") or ""
            if event.get("is_error"):
                t.error = f"{t.response} {event.get('api_error_status') or ''}".strip()
            t.conversation_id = event.get("session_id", t.conversation_id)
    for call_id, name, params, subagent in calls:
        t.steps.append(_claude_step(name, params, call_id in errors, subagent))
        if name == "Read" and "file_path" in params:
            t.reads.append(params["file_path"])
        elif name in ("Grep", "Glob") and isinstance(params.get("path"), str):
            t.reads.append(params["path"])  # a search under a forbidden root is a read of it
        elif name == "Bash" and "command" in params:
            t.commands.append(params["command"])
    return t
