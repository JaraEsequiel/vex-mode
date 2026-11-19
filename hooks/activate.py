"""PreInvocation: `/vex-mode` activates the full mode for this conversation and injects the reading list once.
Any other `/<skill>` of this plugin gets that skill's text and folder injected once per user message: in
`agy -p` a plugin skill's slash command does not expand, and the model may read another skill instead
(docs/decisions/2026-11-19-m4-eval.md).
"""
import hashlib
import re
from pathlib import Path

from vexio import plugin_root, read_payload, safe_id, safe_main, state_dir

COMMAND = re.compile(r"^/vex-mode(\s|$)")
PATH = re.compile(r"^- `([^`]+)`\s*$")
SKILL_COMMAND = re.compile(r"^/([a-z0-9][a-z0-9-]*)(\s|$)")


def reading_list(root: Path) -> list[Path]:
    lines = (root / "skills/vex-mode/SKILL.md").read_text().splitlines()
    start = lines.index("## Read first")
    paths = []
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        m = PATH.match(line)
        if m:
            paths.append(root / m.group(1))
    return paths


def skill_injection(conv: str, prompt: str, root: Path, state: Path) -> dict:
    m = SKILL_COMMAND.match(prompt)
    if not m or m.group(1) == "vex-mode":
        return {}
    folder = root / "skills" / m.group(1)
    if not (folder / "SKILL.md").is_file():
        return {}
    marker = state / "skill" / f"{conv}-{hashlib.sha1(prompt.encode()).hexdigest()[:16]}"
    if marker.exists():
        return {}
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    text = (f"The user invoked /{m.group(1)}. Follow this skill, whose folder is {folder} "
            f"(paths in it are relative to that folder):\n\n" + (folder / "SKILL.md").read_text())
    return {"injectSteps": [{"systemMessage": {"systemMessage": text}}]}


def handle(payload: dict, root: Path, state: Path) -> dict:
    conv = safe_id(payload.get("conversationId"))
    if conv is None:
        return {}
    skill = skill_injection(conv, payload.get("lastUserInput") or "", root, state)
    if skill:
        return skill
    active = state / "active" / conv
    injected = state / "injected" / conv
    if COMMAND.match(payload.get("lastUserInput") or ""):
        active.parent.mkdir(parents=True, exist_ok=True)
        active.touch()
    if not active.exists() or injected.exists():
        return {}
    injected.parent.mkdir(parents=True, exist_ok=True)
    injected.touch()
    files = "\n".join(f"- {p}" for p in [root / "skills/vex-mode/SKILL.md", *reading_list(root)])
    text = (
        "vex-mode is active for this conversation. Before anything else, read these files in full, "
        "then follow skills/vex-mode/SKILL.md:\n" + files
    )
    return {"injectSteps": [{"systemMessage": {"systemMessage": text}}]}


if __name__ == "__main__":
    safe_main(lambda: handle(read_payload(), plugin_root(), state_dir()), {})
