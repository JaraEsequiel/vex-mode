# agy hook probe (M1, Task 7)

- **Date:** 2026-11-18
- **agy:** 1.5.11, headless (`agy -p`), logged in.
- **Method:** a throwaway plugin `vex-probe` with one hook per event. Each hook appended its stdin payload and the `PLUGIN_ROOT` / `PLUGIN_DATA` env vars to a JSONL log. The `PreToolUse` hook printed an output read from a file, so each candidate could be tried. The plugin was installed with `agy plugin install <dir>` and uninstalled afterwards.

## Findings

### 1. The slash command is visible in `lastUserInput` (gate for Task 8: passed)

`agy -p "/hello"` produced `lastUserInput = '/hello'` in `SessionStart`, `PreInvocation`, `PreToolUse` and `Stop`. agy does not expand the skill text into it.

**Consequence:** `hooks/activate.py` can detect `/vex-mode` by checking `lastUserInput.startswith("/vex-mode")`.

### 2. The neutral `PreToolUse` output is "exit 0, no stdout"

| Hook output | `echo` in default headless mode | `rm -f <file outside workspace>`, default mode | Same, `--mode accept-edits` |
|---|---|---|---|
| hook disabled (baseline) | — | executed | auto-denied (needs `command` permission) |
| no stdout | executed | executed | auto-denied |
| `{}` | **denied by hook** | — | — |
| `{"decision":""}` | **denied by hook** | — | — |
| `{"decision":"ask"}` | executed | — | — |
| `{"decision":"allow"}` | — | executed | auto-denied |
| `{"decision":"force_ask","reason":"probe"}` | — | **not executed** (no human in headless mode) | — |

- **No stdout behaves like the baseline in both modes.** This is `NEUTRAL` for `hooks/irreversible.py`.
- **`{}` and an empty decision are treated as deny.** Never emit them from `PreToolUse`.
- **`force_ask` stops the command headless**, and is the intended prompt interactively.
- **Not verified:** whether `allow` bypasses the interactive permission prompt. We never emit `allow`, so it does not matter.

### 3. `PLUGIN_DATA` is set for a locally installed plugin

- `PLUGIN_ROOT=/home/vex/.gemini/config/plugins/<name>` (the installed copy).
- `PLUGIN_DATA=/home/vex/.gemini/antigravity-cli/plugin_data/<name>`.
- The hook's cwd is `PLUGIN_ROOT`.

**Consequence:** `agy plugin install <dir>` **copies** the plugin. After editing the repo, reinstall to test.

### 4. Subagents run as separate conversations with their own hooks

A delegated run produced two `conversationId`s. Each had its own `SessionStart`, `PreInvocation`, `PreToolUse` and `Stop`. The parent called `invoke_subagent`, and the subagent called `run_command`.

**Consequences:**
- The activation mark (keyed by the parent `conversationId`) does not activate subagents. Subagents get the worker rules from `agents/vex-agent.md`. The spec §6.4 fallback is required, not optional.
- `hooks/irreversible.py` also guards subagent commands, which is good.
- The stop gate does not fire inside subagents, because they have no mark.

## Raw evidence

Log excerpts were inspected in session. The probe and its logs lived in a scratch directory and were deleted with the probe.
