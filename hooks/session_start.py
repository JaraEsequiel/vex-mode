"""SessionStart (Claude Code only): load the always-on core, rules/AGENTS.md.

Claude Code has no plugin rules and ignores a plugin CLAUDE.md, so the core arrives as context on
startup, resume, clear and compact. It does not reach subagents; they get worker.md from their brief
(docs/decisions/2026-11-19-claude-code-probes.md, finding 1).
"""
from pathlib import Path

from vexio import is_claude_code, plugin_root, read_payload, safe_main

ADAPTER = "adapters/claude-code.md"


def core(root: Path) -> str:
    text = (root / "rules/AGENTS.md").read_text()
    if text.startswith("---\n"):
        text = text.split("\n---\n", 1)[1]
    return text.strip()


def handle(payload: dict, root: Path) -> dict | None:
    if not is_claude_code(payload) or payload.get("hook_event_name") != "SessionStart":
        return None
    text = (
        core(root) + "\n\n## In Claude Code\n\n"
        f"Full mode is `/vex-mode:vex-mode`. vex-mode skills use agy names: read {root / ADAPTER} "
        "once per session and map them with it."
    )
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}


if __name__ == "__main__":
    safe_main(lambda: handle(read_payload(), plugin_root()), None)
