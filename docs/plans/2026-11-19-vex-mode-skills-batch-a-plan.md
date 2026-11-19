# vex-mode skills batch A — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the bug-fix and feature playbooks and the router back the five pstack skills their steps already name: `tdd`, `why`, `architect`, `unslop` and `technical-writing`. Then measure the change.

**Architecture:**
- The five `SKILL.md` files are vendored verbatim from pstack@e58dd04.
- A separate adapt commit:
  - removes `architect`'s one `arena` sentence;
  - restores, verbatim from upstream, the router and playbook lines that name them. Only Cursor-only parts are left out: the default delegate model, `/loop`, `interrogate`, `swarm` and `arena`.

**Spec:** `docs/specs/2026-11-18-vex-mode-design.md` §6.3, §6.5, §6.6.

## Sources read (2026-11-19)

| Source | What it settles |
|---|---|
| pstack@e58dd04 `skills/{tdd,why,architect,unslop,technical-writing}/SKILL.md` | 42/9/11/40/70 lines. `technical-writing` names **unslop** (vendored here); `architect` line 11 names **arena** (not vendored → `removed_refs`). All are `disable-model-invocation: true`. |
| `poteto-mode/SKILL.md` lines 22-23 vs our router | Upstream: "Across a function boundary → **architect**" and "Prose, your reply included → **unslop**. Docs, PR descriptions, commit messages → **technical-writing**." |
| `poteto-mode/playbooks/bug-fix.md` lines 8, 9, 11 vs ours | Steps 2, 3 and 5 name **why**, `architect` and **tdd**. |
| `poteto-mode/playbooks/feature.md` line 6 vs ours | Step 2 "`architect` for the shape." |
| Upstream issues | Only #1272 (`interrogate`), which is out of this batch. |

## Global Constraints

- Vendor from the upstream checkout at `e58dd04` (`scripts/vendor.py` records `upstream_commit`).
- Restored lines are copied verbatim, minus the Cursor-only parts listed above; every removed skill name stays in `removed_refs`.
- Router and playbook changes are a `vex-mode` change, so they need a `tax-rounding` eval. The five new skills get waivers.

## Review Focus

1. **A restored line names a skill we don't have.** Covered by `checks/check_skills.py` (dangling references) in the verify command.
2. **`removed_refs` drift:** `vendor.lock` must stop listing what is now restored and keep what is still removed. Covered by Task 2 step 3 (diff check).
3. **The activation hook must inject the new skills on `/<name>`** (e.g. `/tdd`). Covered by `hooks/tests/test_activate.py`, which takes any plugin skill folder; Task 2 step 4 checks it on the built plugin.

### Task 1: Vendor
- [ ] Copy the five files with `scripts/vendor.py` from the upstream checkout. Run `checks/run.py`: expected red only for the `arena` dangling ref and for `check_evals`. Commit `vendor: copy tdd, why, architect, unslop, technical-writing from pstack@e58dd04`.

### Task 2: Adapt and restore the references
- [ ] **Step 1:** `architect`: remove line 11 (the `arena` sentence); set `adapted: true` and `removed_refs: ["arena"]`.
- [ ] **Step 2:** Restore the references:
  - Router: append to the "Code" trigger and add the prose trigger.
  - `bug-fix.md` steps 2, 3 and 5.
  - `feature.md` step 2.
- [ ] **Step 3:** `vendor.lock`:
  - drop `why`, `tdd` and `architect` from bug-fix's `removed_refs`;
  - drop `architect` from feature's;
  - drop `architect`, `unslop` and `technical-writing` from the router's.
- [ ] **Step 4:** Full verify, plus a build that shows 22 skills. Commit `adapt: restore tdd, why, architect, unslop, technical-writing in vex-mode`.

### Task 3: Evidence
- [ ] **Step 1:** Waivers for the five skills.
- [ ] **Step 2:** `python3 evals/run.py vex-mode tax-rounding` in the background. Read every output and record the verdict (judge `gpt-6.2-sol`).
- [ ] **Step 3:** Decision doc, full verify, push, PR.
