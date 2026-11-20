# vex-mode for Claude Code

This folder is generated from `skills/`, `agents/`, `rules/`, `hooks/`, `adapters/`, `LICENSES/` and `plugin.json`
of the vex-mode repo. Do not edit it by hand. After editing those sources, run `python3 scripts/build_plugin.py --harness claude-code` from the repository
root and commit the result. CI fails while this copy is out of date.

Install: `claude plugin marketplace add JaraEsequiel/vex-mode`, then `claude plugin install vex-mode@vex`.
Full mode: `/vex-mode:vex-mode`. The always-on core loads at session start.
