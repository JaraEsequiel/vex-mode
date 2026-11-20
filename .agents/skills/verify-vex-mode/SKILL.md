---
name: verify-vex-mode
description: "Project-local verification skill that builds and drives the vex-mode plugin (agy and Claude Code builds, mode activation, skill injection, irreversible command guard, stop gate, and strict plugin validation) in an isolated state directory. Reach for this whenever changes touch hooks/, skills/, rules/, agents/, adapters/, scripts/build_plugin.py, or plugin.json."
---

# Verify vex-mode

`vex-mode` is an agent plugin for Antigravity (`agy`) and Claude Code. Its user-facing surfaces are its packaged plugin builds (`agy` and `harness/claude-code`), its four mode hooks (`activate.py`, `irreversible.py`, `stop_gate.py`, `session_start.py`), and strict validation via `agy plugin validate` and `claude plugin validate --strict`.

This skill drives those real entry points against an isolated build and state directory (`VEX_VERIFY_DIR`) so verification never overwrites the operator's installed plugin or active conversation state.

## Launch

Start an isolated verification instance by setting a unique `RUN_ID`, exporting `VEX_VERIFY_DIR`, adding `.agents/skills/verify-vex-mode/bin` to `PATH`, and running `control-vex-mode launch`:

```bash
export RUN_ID="run-$(date +%s)-$$"
export VEX_VERIFY_DIR="/tmp/vex-mode-verify-$RUN_ID"
export VEX_PROOF_DIR="/tmp/vex-mode-proof-$RUN_ID"
export PATH="$PWD/.agents/skills/verify-vex-mode/bin:$PATH"
mkdir -p "$VEX_PROOF_DIR"
control-vex-mode launch
```

`control-vex-mode launch` builds both the clean `agy` plugin bundle (`$VEX_VERIFY_DIR/build/agy`) and the Claude Code plugin tree (`$VEX_VERIFY_DIR/build/claude-code`) from the current working tree, initializes `$VEX_VERIFY_DIR/state`, writes `$VEX_VERIFY_DIR/instance.json`, and prints `READY verify_dir=...` when ready.

## Doctor

Before driving any feature (or whenever behavior looks off), run the read-only health check:

```bash
control-vex-mode doctor
```

It verifies that `instance.json`, both plugin manifests (`plugin.json` and `.claude-plugin/plugin.json`), both `hooks.json` files, and `skills/vex-mode/SKILL.md` exist in the isolated build and prints `"status": "healthy"`.

## Drive

Use `control-vex-mode` subcommands with literal JSON payloads matching what `agy` and Claude Code send to plugin hooks, plus `control-vex-mode validate` for strict validator checks:

- **Mode activation and skill injection (`activate`):**
  ```bash
  control-vex-mode hook activate --harness agy \
    --payload '{"hookEventName":"PreInvocation","conversationId":"conv-1","lastUserInput":"/vex-mode ship it"}' \
    --artifact "$VEX_PROOF_DIR/activate.json"
  ```
- **Claude Code SessionStart core loading (`session_start`):**
  ```bash
  control-vex-mode hook session_start --harness claude-code \
    --payload '{"hook_event_name":"SessionStart","session_id":"sess-1","source":"startup"}' \
    --artifact "$VEX_PROOF_DIR/session-start.json"
  ```
- **Irreversible action guard (`irreversible`):**
  ```bash
  control-vex-mode hook irreversible --harness agy \
    --payload '{"hookEventName":"PreToolUse","conversationId":"conv-1","toolCall":{"name":"run_command","args":{"CommandLine":"git push --force origin main"}}}' \
    --artifact "$VEX_PROOF_DIR/irreversible.json"
  ```
- **Stop verification gate (`stop_gate`):**
  ```bash
  control-vex-mode hook stop_gate --harness agy \
    --payload '{"hookEventName":"Stop","conversationId":"conv-1","terminationReason":"NO_TOOL_CALL","lastUserInput":"/vex-mode ship it"}' \
    --artifact "$VEX_PROOF_DIR/stop-gate.json"
  ```
- **Strict plugin validation (`validate`):**
  ```bash
  control-vex-mode validate --artifact "$VEX_PROOF_DIR/validate.json"
  ```

See [`.agents/skills/verify-vex-mode/features/README.md`](./features/README.md) for the complete feature map and step-by-step journeys.

## Isolate

Every run uses its own `VEX_VERIFY_DIR=/tmp/vex-mode-verify-$RUN_ID` and `PLUGIN_DATA=$VEX_VERIFY_DIR/data`. Concurrent verification runs can execute side by side without colliding or touching `~/.gemini/config/plugins/vex-mode`.

## Evidence

- Store every proof artifact under `$VEX_PROOF_DIR` (outside `$VEX_VERIFY_DIR`), or pass `--artifact "$VEX_PROOF_DIR/<name>.json"` to `control-vex-mode`.
- Exercise the real built hook scripts in `$VEX_VERIFY_DIR/build/{agy,claude-code}/hooks/` via subprocess stdin/stdout, never internal Python imports.
- Capture both the input payload and the resulting JSON output, exit code, and side effects on `$VEX_VERIFY_DIR/data/state/` (for example, `active/<conv>`, `injected/<conv>`, `asked/<conv>`).

## Cleanup

Tear down the isolated verification instance with:

```bash
control-vex-mode cleanup
```

`control-vex-mode cleanup` removes only `$VEX_VERIFY_DIR` (the temporary builds and hook state) and leaves `$VEX_PROOF_DIR` intact so proof artifacts survive teardown.

## Helpers

- `.agents/skills/verify-vex-mode/bin/control-vex-mode`: executable CLI wrapper (`launch`, `doctor`, `hook`, `validate`, `cleanup`) shown in the sections above.
- `.agents/skills/verify-vex-mode/bin/verify-all`: deterministic verification script that runs all four feature journeys and all four deliberate-break checks end to end and leaves the 18 proof artifacts in `$VEX_PROOF_DIR`:
  ```bash
  python3 .agents/skills/verify-vex-mode/bin/verify-all
  ```
