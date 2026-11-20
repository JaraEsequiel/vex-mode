# Claude Code hook and subagent probe

- **Date:** 2026-11-19
- **Claude Code:** 2.1.329, headless (`claude -p --output-format stream-json --verbose`), model `haiku`, about US$0.01 per run.
- **Method:** a throwaway plugin `probe` loaded with `--plugin-dir` (not installed). One hook per event (`SessionStart`, `UserPromptSubmit`, `UserPromptExpansion`, `PreToolUse` on `Bash`, `Stop`) appended its stdin payload and `CLAUDE_PLUGIN_ROOT` / `CLAUDE_PLUGIN_DATA` to a JSONL log and printed a fixed output. A skill `hello` (`disable-model-invocation: true`) and an agent `worker` with no `model` field. Run 1: `/probe:hello alpha. Then run exactly this shell command: rm -rf ./junk` with `--allowedTools Bash`. Run 2: the main agent spawns `probe:worker` to run `rm -rf ./junk`, with `--allowedTools Bash Agent`.
- **Sources read first:** code.claude.com/docs/en/hooks, plugins/manifest-reference, plugins/loading, sub-agents, skills, headless, sessions; pstack `docs/harness/claude-code.md` and `scripts/generate-pstack-harness-trees.mjs` at cursor/plugins@0b46ec3.

## Findings

1. **`SessionStart` `additionalContext` reaches the main agent in `-p`** (it followed the injected line). It does **not** reach a subagent: the subagent transcript does not contain it. The always-on core can load through `SessionStart`; subagents still get the rules through `worker.md`.
2. **A plugin skill command expands in `-p`.** `/probe:hello alpha` ran the skill with `alpha` as its arguments. The agy workaround in `hooks/activate.py` (inject the skill text) is not needed in Claude Code.
3. **`UserPromptExpansion` names the command.** Payload: `expansion_type: "slash_command"`, `command_name: "probe:hello"`, `command_args`, `command_source: "plugin"`, `prompt` (raw text), `session_id`, `prompt_id`. `UserPromptSubmit` gets the same raw `prompt` and `prompt_id`.
4. **`PreToolUse` `permissionDecision: "ask"` in `-p` denies the call and the agent goes on.** The tool result is the hook's reason; `./junk` survived. This held with `--allowedTools Bash` and inside a plugin subagent, whose payload carries `agent_id` and `agent_type: "probe:worker"`. In agy, `force_ask` ended the headless turn instead (memory of M3).
5. **`Stop` `decision: "block"` with `reason` makes the agent continue once.** The second `Stop` has `stop_hook_active: true`. Every `Stop` carries `prompt_id`, which keys the turn without our own state.
6. **A plugin agent with no `model` runs on the session model** (`claude-haiku-5-5` in its transcript). A Cursor slug in `model` falls back instead (pstack#1270).
7. `CLAUDE_PLUGIN_DATA` is `~/.claude/plugins/data/<id>/` (`probe-inline` for `--plugin-dir`). `claude plugin validate` warns on an unquoted `${CLAUDE_PLUGIN_ROOT}` in a hook command. `claude -p` waits 3 s for stdin unless it gets `< /dev/null`.

## Not probed

`ask` in an interactive session (the docs say it prompts), `SessionStart` on `resume`, `clear` and `compact`, installing from a GitHub marketplace.

## Smoke test of the generated tree

`claude -p --plugin-dir harness/claude-code --model haiku`, in an empty git repo, about US$0.01 per run:

- `/vex-mode:vex-mode ...`: `SessionStart` injected `# vex-mode core`; the activation context listed `adapters/claude-code.md`, `skills/vex-mode/SKILL.md` and `worker.md` first; the agent ended its reply, then the Stop gate made it show verification evidence once (state files `active`, `injected`, `asked` under `~/.claude/plugins/data/vex-mode-inline/state/`).
- `git push --force origin main`: denied with `vex-mode: irreversible action (git push --force)`; the agent did not retry. A relative `rm -rf ./junk` runs, as in agy: the guard covers absolute, home, variable and parent paths only.

## agent-ready Stop hook in Claude Code

A repo with `scripts/check` failing on `TODO`, `templates/check_on_stop.py` in `.agents/` and `templates/claude-settings.json` as `.claude/settings.json`; `claude -p --model haiku "Append the line '# TODO later' to app.py and stop."` (about US$0.01). The project hook loaded in `-p`, blocked the finish three times with `lint: app.py contains TODO`, then let it end; the agent asked instead of deleting the requested line.

## Evals on Claude Code

- A fresh `CLAUDE_CONFIG_DIR` loses the CLI login (`Not logged in · Please run /login`), so it cannot isolate candidates.
- `--setting-sources project` keeps the login and loads only built-in plugins plus `--plugin-dir`: no user plugins (engram, superpowers), no MCP servers, no `~/.claude/CLAUDE.md`, no `~/.claude/skills` or `~/.claude/agents`; auto memory points at a fresh per-workdir folder. `evals/run.py` uses it for `"harness": "claude-code"` cases.
- Real candidate run through `run._run_claude` (haiku, `/vex-mode:vex-mode` on a one-line bug, US$0.0086, 23 s): it read the adapter, `worker.md`, `playbooks/bug-fix.md` and three principles first, fixed the bug, ran the check, and had no isolation violation.
