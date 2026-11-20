# Build and validate plugin packages

`vex-mode` exports a clean `agy` plugin directory (without repo-only files like `evals/`, `docs/`, or `AGENTS.md`), generates a synced Claude Code plugin tree under `harness/claude-code/`, and validates both strictly with `agy plugin validate` and `claude plugin validate --strict`.

## Sub-features

- `build-clean-agy` exports only `PLUGIN_PARTS` (`plugin.json`, `skills`, `agents`, `rules`, `hooks.json`, `hooks`, `LICENSES`) without `tests/` or `__pycache__/`.
- `build-claude-code` renders `harness/claude-code/` with mapped adapter preamble lines, stripped agent frontmatter, Claude Code hook events, and a content-hashed version string.
- `validate-strict` runs `agy plugin validate --json` and `claude plugin validate --strict` on the repo root and `harness/claude-code` with zero unexpected warnings or errors.

## How to get to it (user POV)

- Run `python3 scripts/build_plugin.py <out>` or `python3 scripts/build_plugin.py --harness claude-code --check`.
- Run `python3 scripts/validate_plugin.py` (or `./scripts/check`).

## Driving it with control-vex-mode

Preconditions:

- `control-vex-mode launch` has built both trees under `$VEX_VERIFY_DIR/build/`.

- **Verify isolated build layout.** Run `control-vex-mode doctor > "$VEX_PROOF_DIR/doctor.json"`. Exit code `0`, output JSON reports `"status": "healthy"`, and neither `$VEX_VERIFY_DIR/build/agy/evals` nor `$VEX_VERIFY_DIR/build/agy/AGENTS.md` exists.
- **Run strict plugin validation.** Run `control-vex-mode validate --artifact "$VEX_PROOF_DIR/validate.json"`. Exit code `0`, stdout prints the component counts JSON (`{"agents": 1, "hooks": 3, ...}`), and no warning or error lines follow.

## Gotchas

- Editing any file under `skills/`, `agents/`, `rules/`, `hooks/`, `adapters/`, or `plugin.json` changes the Claude Code content hash; run `python3 scripts/build_plugin.py --harness claude-code` before `./scripts/check`.
- Every `agy`-specific term used in a skill must match a pattern in `scripts/build_plugin.py` (`TERMS`) and have a corresponding row in `adapters/claude-code.md`.

## Breaks

- Delete `"version"` from `$VEX_VERIFY_DIR/build/agy/plugin.json`. **Run strict plugin validation** must fail: `control-vex-mode validate` exits non-zero reporting `warning: plugin.json: no version specified`.
