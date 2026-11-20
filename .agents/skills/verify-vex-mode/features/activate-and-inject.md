# Activate vex-mode and inject skills

Activation turns on `/vex-mode` for a conversation and injects its reading list once per session, injects any other plugin skill's text and folder once per user message in `agy`, and loads the always-on core at `SessionStart` in Claude Code.

## Sub-features

- `activate-agy-once` activates `/vex-mode` in `agy`, writes `active/<conv>` and `injected/<conv>`, and injects the reading list on the first message only.
- `activate-skill-inject` injects another plugin skill's `SKILL.md` and folder path once per distinct user message in `agy` without activating full `/vex-mode`.
- `activate-cc-session-start` loads `rules/AGENTS.md` (without YAML frontmatter) and names the Claude Code adapter on `SessionStart`.
- `activate-cc-prompt` activates `/vex-mode:vex-mode` in Claude Code on `UserPromptSubmit` and injects the adapter plus reading list once.

## How to get to it (user POV)

- Send `/vex-mode <task>` in an `agy` conversation.
- Send `/<skill> <task>` (such as `/agent-ready` or `/correct`) in an `agy` conversation.
- Start or resume a Claude Code session with the plugin enabled (`SessionStart`), then send `/vex-mode:vex-mode <task>` (`UserPromptSubmit`).

## Driving it with control-vex-mode

Preconditions:

- `control-vex-mode launch` has built the isolated plugin trees in `$VEX_VERIFY_DIR`.
- `control-vex-mode doctor` reports `"status": "healthy"`.
- No state files exist yet under `$VEX_VERIFY_DIR/data/state/`.

- **Activate in agy.** Send `/vex-mode ship it` for conversation `conv-1`. Run `control-vex-mode hook activate --harness agy --payload '{"hookEventName":"PreInvocation","conversationId":"conv-1","lastUserInput":"/vex-mode ship it"}' --artifact "$VEX_PROOF_DIR/activate-agy-1.json"`. Exit code `0`, stdout JSON contains `injectSteps[0].systemMessage.systemMessage` naming `skills/vex-mode/SKILL.md` and `skills/vex-mode/worker.md`, and `$VEX_VERIFY_DIR/data/state/active/conv-1` exists.
- **No duplicate reading list.** Send a second message in `conv-1`. Run `control-vex-mode hook activate --harness agy --payload '{"hookEventName":"PreInvocation","conversationId":"conv-1","lastUserInput":"next step"}' --artifact "$VEX_PROOF_DIR/activate-agy-2.json"`. Exit code `0` and stdout is `{}`.
- **Skill injection in agy.** Send `/correct` in a separate conversation `conv-2`. Run `control-vex-mode hook activate --harness agy --payload '{"hookEventName":"PreInvocation","conversationId":"conv-2","lastUserInput":"/correct"}' --artifact "$VEX_PROOF_DIR/activate-skill.json"`. Exit code `0`, stdout contains `# Correct` and `skills/correct`, and `$VEX_VERIFY_DIR/data/state/active/conv-2` does not exist.
- **Claude Code SessionStart.** Trigger `SessionStart` for `sess-1`. Run `control-vex-mode hook session_start --harness claude-code --payload '{"hook_event_name":"SessionStart","session_id":"sess-1","source":"startup"}' --artifact "$VEX_PROOF_DIR/cc-session-start.json"`. Exit code `0` and stdout `hookSpecificOutput.additionalContext` contains `# vex-mode core` and `adapters/claude-code.md`.
- **Claude Code UserPromptSubmit.** Send `/vex-mode:vex-mode fix bug` for `sess-1`. Run `control-vex-mode hook activate --harness claude-code --payload '{"hook_event_name":"UserPromptSubmit","session_id":"sess-1","prompt":"/vex-mode:vex-mode fix bug"}' --artifact "$VEX_PROOF_DIR/cc-activate.json"`. Exit code `0`, stdout `hookSpecificOutput.additionalContext` lists `adapters/claude-code.md` and `skills/vex-mode/SKILL.md`, and `$VEX_VERIFY_DIR/data/state/active/sess-1` exists.

## Gotchas

- `conversationId` and `session_id` values with path separators (`../`, `/`) are rejected by `safe_id` and treated as inactive.
- In `agy`, repeating the exact same `/<skill>` prompt in the same conversation is deduplicated by prompt hash; change the prompt text to test a second injection.
- Claude Code expands plugin skill slash commands itself, so `activate.py` only injects `/vex-mode` (`UserPromptSubmit`) in Claude Code.

## Breaks

- Make `reading_list()` in `hooks/activate.py` return `[]`. **Activate in agy** must fail: `skills/vex-mode/worker.md` is missing from `injectSteps[0].systemMessage.systemMessage`.
