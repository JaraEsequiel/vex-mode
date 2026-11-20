# vex-mode in Claude Code

vex-mode skills use Antigravity (agy) names. In Claude Code, read this file once per session, then map each agy name in a skill with the tables below. `<vex-mode>` means the plugin folder that holds `skills/`. If an agy field has no row, drop it and say so. Never pass a field or value the tool schema rejects.

## Tools

| agy | Claude Code |
| --- | --- |
| A tool that shows a person a question | `AskUserQuestion`. In `-p` mode it is absent, so ask in plain text. |
| Open a todolist, or copy steps into the todolist tool | Use `TodoWrite` if the session offers it. Otherwise keep the list in your reply and update it at each phase. |
| Run another vex-mode skill (`/name` or "the **name** skill") | `Read` `<vex-mode>/skills/<name>/SKILL.md` and follow it. The `Skill` tool refuses most vex-mode skills. When you tell the user to type it, write `/vex-mode:<name>`. |
| `/vex-mode` | `/vex-mode:vex-mode`. |
| `Grep`, `Glob` | `Bash` with `rg` when the session has no `Grep` or `Glob`. |

## Subagent fields

| agy | Claude Code |
| --- | --- |
| The `vex-agent` agent | `subagent_type: "vex-mode:vex-agent"`. Its file names no model, so it runs on the session model. |
| A general subagent | `subagent_type: "general-purpose"`. It keeps the session's MCP servers. |
| Run it in the background | Omit. Subagents run in the background by default and notify you when they finish. |

## Models

| agy | Claude Code |
| --- | --- |
| `claude-<family>-<version>-<effort>`, such as `claude-opus-5-5-xhigh` | `model: "opus"` and `effort: "xhigh"`. `model` takes only `opus`, `sonnet`, `haiku`, `fable`. |
| A `gemini-*` or other non-Claude slug | Omit `model` so the agent runs on the session model, and say so. |
| A reviewer on another vendor's model: `agy --model <model> -p "<prompt>"` from the shell | The same command when `command -v agy` finds it, with a non-Claude model from `agy models`. Otherwise write `Skipped in Claude Code: cross-model review. agy is not installed.` A Claude subagent is not another vendor's model. |

## Paths

| agy | Claude Code |
| --- | --- |
| `.agents/skills/`, `~/.gemini/config/skills/` | `.claude/skills/`, `~/.claude/skills/` |
| `~/.gemini/config/plugins/`, the vex-mode `plugin.json` | `~/.claude/plugins/`, `<vex-mode>/.claude-plugin/plugin.json` |
| This conversation's transcript, `.system_generated/logs/transcript.jsonl`, or `~/.gemini/antigravity-cli/brain/` | `~/.claude/projects/<slug>/<session>.jsonl`. The slug is the workspace path with each character other than an ASCII letter or digit changed to `-`, so `/Users/you/proj` is `-Users-you-proj`. The newest `.jsonl` directly in that folder is the current session. Its `<session>/subagents/` folder holds subagent transcripts. Read only this workspace's folder. |
| Workspace hooks in `.agents/hooks.json` | The `hooks` key of `.claude/settings.json`. Its format differs, so an agy hook template does not work there. |

## Antigravity-only features

Claude Code has no agy brain artifacts, agy plugin commands, or agy hook format. When a step needs one, put one line in your reply, `Skipped in Claude Code: <step>. <reason>.`, then go on to the next step. Do not stop, ask, or retry. When a later step needs what the skipped step made, such as a file or a path, leave a placeholder and name it in the line.

| agy | Claude Code |
| --- | --- |
| A step that installs an agy hook template, such as `agent-ready`'s Stop hook | Skip with the line. |
| A script that runs `agy` itself, such as `evals/run.py` | Run it as written. It calls agy whatever harness you are in. That is not a skip, so write no line. |
