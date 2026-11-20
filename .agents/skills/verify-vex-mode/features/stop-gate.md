# Gate stopping on verification evidence

When an agent is about to finish a turn in an active `/vex-mode` conversation, the `Stop` gate asks once per user message for verification evidence from the real artifact before letting the agent stop.

## Sub-features

- `stop-inactive` lets inactive conversations stop immediately (`{}` in `agy`, empty output in Claude Code).
- `stop-agy-once` returns `{"decision": "continue", ...}` on the first `NO_TOOL_CALL` stop for a user message in an active `agy` conversation, and `{}` on subsequent stops for the same message.
- `stop-agy-next-turn` asks again when `lastUserInput` changes on the next user turn.
- `stop-cc-once` returns `{"decision": "block", ...}` on the first stop for a `prompt_id` in an active Claude Code session, and empty output when `stop_hook_active` is true or the same `prompt_id` repeats.

## How to get to it (user POV)

- Finish an agent turn in `agy` (`Stop` event with `terminationReason: "NO_TOOL_CALL"`).
- Finish an agent turn in Claude Code (`Stop` event with `prompt_id`).

## Driving it with control-vex-mode

Preconditions:

- `control-vex-mode launch` and `control-vex-mode doctor` have succeeded for `$VEX_VERIFY_DIR`.

- **Inactive conversation stops cleanly.** Run `control-vex-mode hook stop_gate --harness agy --payload '{"hookEventName":"Stop","conversationId":"idle-conv","terminationReason":"NO_TOOL_CALL","lastUserInput":"hello"}' --artifact "$VEX_PROOF_DIR/stop-inactive.json"`. Exit code `0` and stdout is `{}`.
- **Activate conversation.** Run `control-vex-mode hook activate --harness agy --payload '{"hookEventName":"PreInvocation","conversationId":"active-conv","lastUserInput":"/vex-mode fix bug"}' --artifact "$VEX_PROOF_DIR/stop-activate.json"`. Exit code `0` and `$VEX_VERIFY_DIR/data/state/active/active-conv` exists.
- **First stop continues for evidence.** Run `control-vex-mode hook stop_gate --harness agy --payload '{"hookEventName":"Stop","conversationId":"active-conv","terminationReason":"NO_TOOL_CALL","lastUserInput":"/vex-mode fix bug"}' --artifact "$VEX_PROOF_DIR/stop-first.json"`. Exit code `0`, stdout JSON has `"decision": "continue"`, and `"reason"` contains `show verification evidence from the real artifact`.
- **Second stop in same turn allows finish.** Run the exact same `stop_gate` command with `--artifact "$VEX_PROOF_DIR/stop-second.json"`. Exit code `0` and stdout is `{}`.
- **New user turn gates again.** Run `control-vex-mode hook stop_gate --harness agy --payload '{"hookEventName":"Stop","conversationId":"active-conv","terminationReason":"NO_TOOL_CALL","lastUserInput":"now add tests"}' --artifact "$VEX_PROOF_DIR/stop-next-turn.json"`. Exit code `0` and stdout JSON has `"decision": "continue"`.
- **Claude Code active session blocks once per prompt.** Activate `sess-1` with `control-vex-mode hook activate --harness claude-code --payload '{"hook_event_name":"UserPromptSubmit","session_id":"sess-1","prompt":"/vex-mode:vex-mode fix bug"}'`, then run `control-vex-mode hook stop_gate --harness claude-code --payload '{"hook_event_name":"Stop","session_id":"sess-1","prompt_id":"p1","stop_hook_active":false}' --artifact "$VEX_PROOF_DIR/stop-cc-first.json"`. Exit code `0` and stdout JSON has `"decision": "block"`. Running the same command again with `--artifact "$VEX_PROOF_DIR/stop-cc-second.json"` exits `0` with empty stdout (`""`).

## Gotchas

- Non-normal termination reasons in `agy` (`USER_CANCELED`, `ERROR`, `MAX_INVOCATIONS`) never trigger the gate.
- In Claude Code the gate reads the session file at `transcript_path` and stays silent when the turn's last main-agent tool call was `Bash` (the agent already checked after its last change). A payload without `transcript_path`, as above, is always asked.
- `agy` 1.5.11 keeps `continuationActive: false` across hook continuations, so `stop_gate.py` keys its on-disk marker in `$VEX_VERIFY_DIR/data/state/asked/<conv>` by the SHA-256 of `lastUserInput`.

## Breaks

- Comment out `asked.write_text(key)` in `hooks/stop_gate.py`. **Second stop in same turn allows finish** must fail: the hook returns `"decision": "continue"` instead of `{}` and traps the agent in a loop.
