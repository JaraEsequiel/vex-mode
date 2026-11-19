# vex-mode — instructions for agents maintaining this repo

## Mission

This repo is an Antigravity plugin: Vex's working mode for agents, built on pstack (Lauren Tan / poteto). It is maintained by agents. Every lesson ends in structure (a check, a hook, a test), not in more prose. The design is `docs/specs/2026-11-18-vex-mode-design.md`; read it before changing anything structural.

## Map

- `plugin.json`: plugin manifest. `name` must stay `vex-mode`.
- `rules/AGENTS.md`: always-on core loaded in Vex's sessions. Keep it minimal.
- `skills/vex-mode/`: the router (`SKILL.md`), `worker.md` (rules every subagent inherits), `playbooks/`.
- `skills/principle-*/`: one principle per skill.
- `agents/vex-agent.md`: the subagent definition.
- `hooks.json` + `hooks/`: mode hooks (activation, irreversible pause, stop gate).
- `checks/`: deterministic structural checks. `checks/run.py` runs all of them.
- `evals/`: `run.py` (the eval harness), `harness/`, and per skill `evals/<skill>/cases/` and `results/`. Never inside `skills/`: a candidate must not see them.
- `scripts/vendor.py`: copies pstack files verbatim and records provenance.
- `scripts/build_plugin.py`: exports only the plugin's parts; install with `--install`, never `agy plugin install` on the repo.
- `vendor.lock`: provenance for every file under `skills/`, `rules/`, `agents/`.
- `docs/specs/`, `docs/plans/`, `docs/decisions/`: design, plans, decision log.

## How to verify a change

```bash
python3 -m unittest discover -s checks/tests \
  && python3 -m unittest discover -s scripts/tests \
  && python3 -m unittest discover -s hooks/tests \
  && python3 -m unittest discover -s evals/tests \
  && python3 checks/run.py \
  && python3 scripts/validate_plugin.py
```

`scripts/validate_plugin.py` is `agy plugin validate --strict` with one documented exception: agy warns that this root `AGENTS.md` is never loaded by the plugin. That is intended; this file is for agents working in the repo, not for plugin users.

## How to bring in something that already exists

Never rewrite what pstack (or another source) already has.

1. `python3 scripts/vendor.py <upstream_root> <upstream_path> <dest>` for each file. Commit only that, as `vendor: copy <thing> from pstack@<sha>`.
2. In a separate commit `adapt: <thing> for antigravity`, make only the edits Antigravity needs: paths, model slugs, tool names, renames, removing references to skills not vendored yet. In `vendor.lock`, set `"adapted": true` on that file (unadapted files must stay byte-identical to upstream), list removed references in `removed_refs` (what to restore when that skill is vendored), and keep in `pending_refs` only references still in the text that point to skills not vendored yet.

A new file that has no upstream goes under `original` in `vendor.lock`.

## How to change a skill

A skill change ships with evidence for its exact version (its tree hash):

1. Commit the change, then run `python3 evals/run.py <skill> <case>` (playbook: `skills/vex-mode/playbooks/eval.md`). It installs each arm's build and restores the user's plugin.
2. Read every candidate's output and transcript in the printed run dir, compare with the judge, then `python3 evals/run.py verdict <result> <promote|reject|inconclusive> "<synthesis>"`.
3. If no eval can measure the change, add a waiver result with a reason instead. The user accepts or rejects it in the PR.

A PR that changes `skills/<name>/` without a valid result for its current tree hash fails CI.

## Rules

| Rule | Enforced by |
|---|---|
| Files from pstack are copied verbatim and recorded | `checks/check_vendor.py` `scripts/vendor.py` |
| Skill name matches folder, description present | `checks/check_skills.py` |
| No dangling skill, playbook or link references | `checks/check_skills.py` |
| Size budgets (SKILL ≤ 16 KB, rule ≤ 24 KB) | `checks/check_skills.py` |
| Every rule has an enforcer | `checks/check_rules.py` |
| The plugin is installed only from a clean build (no repo files in the installed copy) | `scripts/build_plugin.py` `scripts/tests/test_build_plugin.py` |
| Plugin manifest, skills, agents and rules load in agy | `scripts/validate_plugin.py` `.github/workflows/ci.yml` |
| Every check and test runs on every push and PR | `.github/workflows/ci.yml` |
| Full mode activates only via /vex-mode, reading list injected once | `hooks/activate.py` `hooks/tests/test_activate.py` |
| Pause before irreversible actions (force_ask, never allow) | `hooks/irreversible.py` `hooks/tests/test_irreversible.py` |
| No finishing without evidence in vex-mode | `hooks/stop_gate.py` `hooks/tests/test_stop_gate.py` |
| A PR that changes a skill carries an eval result or waiver for that skill's tree hash | `checks/check_evals.py` `checks/tests/test_check_evals.py` |
| Nothing a candidate sees contains a banned word | `checks/check_evals.py` `checks/tests/test_check_evals.py` |
| The judge is from another model family than every candidate | `checks/check_evals.py` `evals/harness/arms.py` |
| Every eval measures compliance, outcome and cost on three fixed arms | `evals/harness/arms.py` `evals/tests/test_run.py` |
| An eval never leaves a variant installed | `evals/run.py` `evals/tests/test_run.py` |
| A run that read the run dir, the repo or another skill copy is invalid | `evals/harness/isolation.py` `evals/tests/test_run.py` |
| A PreToolUse hook with no opinion prints nothing (`{}` denies the tool) | `hooks/tests/test_irreversible.py` `docs/decisions/2026-11-18-hook-probe.md` |

When you are corrected for a mistake, add a row here together with its enforcer in the same change. A rule that nothing enforces is a repeat waiting to happen.
