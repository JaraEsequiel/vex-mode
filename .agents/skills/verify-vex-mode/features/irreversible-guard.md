# Pause before irreversible commands

The irreversible `PreToolUse` hook inspects every shell command before execution and forces human confirmation on destructive or self-merging commands while printing nothing on ordinary commands.

## Sub-features

- `irreversible-agy-ask` returns `{"decision": "force_ask", ...}` in `agy` when `run_command` contains a force push, destructive `rm -rf`, deploy, destructive SQL, or merge/push to `main`.
- `irreversible-cc-ask` returns `permissionDecision: "ask"` in Claude Code when `Bash` contains an irreversible command.
- `irreversible-neutral` prints nothing (empty stdout) on safe commands so `agy` does not treat `{}` as a denial.

## How to get to it (user POV)

- An agent in `agy` calls `run_command` with a shell command (`PreToolUse`).
- An agent in Claude Code calls `Bash` with a shell command (`PreToolUse`).

## Driving it with control-vex-mode

Preconditions:

- `control-vex-mode launch` and `control-vex-mode doctor` have succeeded for `$VEX_VERIFY_DIR`.

- **Force push in agy.** Run `control-vex-mode hook irreversible --harness agy --payload '{"hookEventName":"PreToolUse","conversationId":"conv-1","toolCall":{"name":"run_command","args":{"CommandLine":"git push --force origin feature"}}}' --artifact "$VEX_PROOF_DIR/irreversible-force-push.json"`. Exit code `0`, stdout JSON has `"decision": "force_ask"`, and `"reason"` contains `git push --force`.
- **Self-merge guard in agy.** Run `control-vex-mode hook irreversible --harness agy --payload '{"hookEventName":"PreToolUse","conversationId":"conv-1","toolCall":{"name":"run_command","args":{"CommandLine":"gh pr merge 12 --squash"}}}' --artifact "$VEX_PROOF_DIR/irreversible-merge.json"`. Exit code `0`, stdout JSON has `"decision": "force_ask"`, and `"reason"` contains `gh pr merge (only the user merges)`.
- **Push to main in Claude Code.** Run `control-vex-mode hook irreversible --harness claude-code --payload '{"hook_event_name":"PreToolUse","session_id":"sess-1","tool_name":"Bash","tool_input":{"command":"git push origin HEAD:main"}}' --artifact "$VEX_PROOF_DIR/irreversible-cc-main.json"`. Exit code `0`, stdout JSON has `hookSpecificOutput.permissionDecision` equal to `"ask"`, and `permissionDecisionReason` contains `git push to main`.
- **Safe command prints nothing.** Run `control-vex-mode hook irreversible --harness agy --payload '{"hookEventName":"PreToolUse","conversationId":"conv-1","toolCall":{"name":"run_command","args":{"CommandLine":"git status -sb && python3 checks/run.py"}}}' --artifact "$VEX_PROOF_DIR/irreversible-safe.json"`. Exit code `0` and stdout is completely empty (`""`).

## Gotchas

- A `PreToolUse` hook in `agy` must print nothing when it has no opinion; printing `{}` denies the tool call.
- Wrapper commands (`env`, `sudo`, `bash -c`, `eval`, subshells) are unwrapped by `_segments`, so wrapped irreversible commands still pause.

## Breaks

- Remove `"merge"` from `_gh()` in `hooks/irreversible.py`. **Self-merge guard in agy** must fail: stdout is empty instead of returning `"decision": "force_ask"` with `gh pr merge`.
