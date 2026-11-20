# vex-mode verification map

This directory is the maintained source for verifying the user-facing behavior of the `vex-mode` plugin across Antigravity (`agy`) and Claude Code. Read this index before driving the plugin, then follow the matching feature file.

## Baseline preconditions

- Export a unique `RUN_ID`, `VEX_VERIFY_DIR=/tmp/vex-mode-verify-$RUN_ID`, and `VEX_PROOF_DIR=/tmp/vex-mode-proof-$RUN_ID`.
- Put `.agents/skills/verify-vex-mode/bin` on `PATH`.
- Run `control-vex-mode launch` to build the isolated `agy` and Claude Code plugin trees.
- Run `control-vex-mode doctor` and require `"status": "healthy"`.
- Never drive the user's installed plugin copy in `~/.gemini/config/plugins/vex-mode`.

## Driving conventions

- Start every recipe from a fresh `control-vex-mode launch` state unless its preconditions state otherwise.
- Drive hooks through `control-vex-mode hook <hook> --harness <agy|claude-code> --payload <json>`.
- Drive strict validation through `control-vex-mode validate`.
- Pass `--artifact "$VEX_PROOF_DIR/<file>.json"` so proof artifacts live outside `VEX_VERIFY_DIR` and survive `control-vex-mode cleanup`.

## Proof and skip reporting

- Capture the exact command, input payload, stdout, stderr, and exit code for every step.
- For stateful hooks (`activate`, `stop_gate`), also verify the state files written under `$VEX_VERIFY_DIR/data/state/`.
- Record the feature ID and harness used with every artifact.
- Report an unreachable path with the attempted command and the unmet precondition.
- Do not report a skipped harness as verified through the other harness.

## Feature entry contract

Each feature file starts with an H1 title and one paragraph describing the user-visible behavior. It then uses exactly five H2 sections in this order.

1. `Sub-features` lists short IDs with one line for each behavior.
2. `How to get to it (user POV)` lists every user entry point.
3. `Driving it with control-vex-mode` starts with `Preconditions:` and uses labeled bullets that pair each user action with an exact command and observable result.
4. `Gotchas` lists traps that can waste or invalidate a verification run.
5. `Breaks` lists each deliberate break of the behavior with the check it must fail at, so a later pass can replay it.

Keep implementation details out of the map. Name only user paths, stable handles, required state, commands, and observable proof.

## Features

- [Activate vex-mode and inject skills](./activate-and-inject.md) covers `/vex-mode` reading-list injection once per session, per-message plugin skill injection in `agy`, and Claude Code `SessionStart` + `UserPromptSubmit`.
- [Pause before irreversible commands](./irreversible-guard.md) covers `PreToolUse` confirmation (`force_ask` in `agy`, `ask` in Claude Code), merge/push-to-main blocking, and silent pass-through on ordinary commands.
- [Gate stopping on verification evidence](./stop-gate.md) covers `Stop` continuation (`continue` in `agy`, `block` in Claude Code) once per user turn in active sessions and silent exit in inactive or repeated turns.
- [Build and validate plugin packages](./build-and-validate.md) covers clean `agy` and Claude Code plugin packaging and strict validation via `agy plugin validate` and `claude plugin validate --strict`.
