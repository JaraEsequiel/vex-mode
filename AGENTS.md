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
- `scripts/vendor.py`: copies pstack files verbatim and records provenance.
- `vendor.lock`: provenance for every file under `skills/`, `rules/`, `agents/`.
- `docs/specs/`, `docs/plans/`, `docs/decisions/`: design, plans, decision log.

## How to verify a change

```bash
python3 -m unittest discover -s checks/tests \
  && python3 -m unittest discover -s scripts/tests \
  && python3 checks/run.py \
  && agy plugin validate . --strict
```

Once `hooks/tests/` exists, also run `python3 -m unittest discover -s hooks/tests`.

## How to bring in something that already exists

Never rewrite what pstack (or another source) already has.

1. `python3 scripts/vendor.py <upstream_root> <upstream_path> <dest>` for each file. Commit only that, as `vendor: copy <thing> from pstack@<sha>`.
2. In a separate commit `adapt: <thing> for antigravity`, make only the edits Antigravity needs: paths, model slugs, tool names, renames, removing references to skills not vendored yet (list each in that file's `pending_refs` in `vendor.lock`).

A new file that has no upstream goes under `original` in `vendor.lock`.

## Rules

| Rule | Enforced by |
|---|---|
| Files from pstack are copied verbatim and recorded | `checks/check_vendor.py` `scripts/vendor.py` |
| Skill name matches folder, description present | `checks/check_skills.py` |
| No dangling skill, playbook or link references | `checks/check_skills.py` |
| Size budgets (SKILL ≤ 16 KB, rule ≤ 24 KB) | `checks/check_skills.py` |
| Every rule has an enforcer | `checks/check_rules.py` |

When you are corrected for a mistake, add a row here together with its enforcer in the same change. A rule that nothing enforces is a repeat waiting to happen.
