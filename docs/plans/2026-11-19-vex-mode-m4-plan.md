# vex-mode M4 (Other repos) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let vex-mode prepare any repo for agents. `/agent-ready` writes the rule table, a `check` that runs the same way locally and in CI, a `Stop` hook that returns the check's error to the agent, and a `verify-<app>` skill. The verify skill drives the app like a user and proves it can fail.

**Architecture:**
- `create-verification-skill` and `maintain-verification-skill` come from pstack, then a separate adapt commit adds:
  - agy paths (`.agents/skills/`);
  - #1271: every driven journey is shown to fail on a deliberate break, and the break is recorded under `## Breaks`.
- `agent-ready` is original. It references `correct` and `create-verification-skill` instead of copying them, and ships one tested template, `templates/check_on_stop.py`, the target repo's `Stop` hook.
- One real eval case (a small CLI repo) measures `/agent-ready` with a hidden check that breaks the target on purpose.

**Tech Stack:** Python 3 stdlib, `unittest`; agy 1.5.12 hooks (`Stop` → `{"decision":"continue","reason":…}`); GitHub Actions for the generated workflow.

**Spec:** `docs/specs/2026-11-18-vex-mode-design.md` §7.2, §8.3, §10, §10b, §11, §13 (corrected 2026-11-19 after the source review).

## Sources read for this plan (2026-11-19)

| Source | What it settles here |
|---|---|
| `pstack/skills/create-verification-skill/SKILL.md` + `references/feature-map-example/{README,create-note,search}.md` @ `e58dd04` (= `35a9094`) | Vendored. Line 9/25/36 name `.cursor/skills/` (→ `.agents/skills/`); line 40 is the step #1271 extends; README's "exactly four H2 sections" becomes five with `Breaks`. |
| `pstack/skills/maintain-verification-skill/SKILL.md` @ `e58dd04` | Vendored; line 25 names `.cursor/skills/verify-*/`; line 33 (live pass) gets the replay of recorded breaks (#1271's second suggestion). |
| `pstack/skills/correct/SKILL.md` lines 19-30 (vendored in M3) | The rule table and the inverted pyramid `agent-ready` points to; "run the same command locally and in CI" (line 26). |
| `pstack/skills/setup-pstack/SKILL.md` line 74, `poteto-help` lines 28, 88-89 | pstack offers `/create-verification-skill` from setup/help, not from the mode router, so the vex-mode router does not change (no vex-mode eval needed). |
| Issues #1271 (closed not planned), #457 (closed, unfixed), #1245 (open) | #1271 adopted (approved 2026-11-19). #457 and #1245 recorded as candidates only. |
| agy hooks doc `builtin/skills/agy-customizations/docs/hooks.md` + probe `A-probe-m4` | `PostToolUse` output is ignored; `Stop` `continue` + `reason` reaches the agent; workspace `.agents/hooks.json` loads in `agy -p`; hook cwd is `.agents/`. |
| T-redreamality, T-teamday (re-read 2026-11-19) | Inverted pyramid; a feature map kept in the repo. Neither covers hooks or local/CI parity. |
| `evals/run.py` `_outcome` (line 102), M2/M3 case layout | The hidden check is `check.py <workdir>`, exit 0 = outcome 1. Banned words apply to the prompt, project and workdir. |

## Global Constraints

- Vendor pin `35a90942a7f02e1ebbc2443643179815f2147954`; `vendor:` commit, then a separate `adapt:` commit, per `AGENTS.md`.
- Agent-facing text in English; human docs in Spanish.
- Generated layout in the target repo:
  - `AGENTS.md` with a `| Rule | Enforced by |` table;
  - an executable `scripts/check`;
  - `.agents/hooks.json` with a `Stop` hook running `python3 check_on_stop.py ../scripts/check` (the hook's cwd is `.agents/`);
  - `.agents/check_on_stop.py`;
  - `.agents/skills/verify-<app>/` with `SKILL.md`, `features/README.md` and at least one feature file;
  - `.github/workflows/check.yml`, only when a GitHub remote exists.
- `check_on_stop.py`: no output when the tree is clean or the check passes; at most 3 `continue`s per conversation; reason = the check's last 60 output lines.
- Eval case: `runs` 3, `candidate_model` `gemini-4-neon-medium`, `upgrade_model` `gemini-4-neon-high`, `judge_model` `claude-opus-5-5-high`, `timeout_s` 1800, workdir `habit-tracker`.

## Review Focus

1. **The `Stop` hook loops forever** when the check keeps failing. The 4th Stop in one conversation must print nothing. Covered: `test_gives_up_after_three` (Task 2).
2. **The hook blocks a clean finish**: a clean tree or a passing check must print nothing (in agy, printed JSON is a decision). Covered: `test_clean_tree_prints_nothing`, `test_passing_check_prints_nothing` (Task 2).
3. **The hook crashes on odd input** (empty stdin, non-JSON, missing check script). It must print nothing and exit 0, so agy is never stuck. Covered: `test_malformed_input_is_silent`, `test_missing_check_is_reported_once` (Task 2).
4. **The hidden check grades a generated setup that cannot fail as a success.** It must break the target and require the check and the hook to catch it. Covered: `test_hidden_check_rejects_a_check_that_never_fails` (Task 3).
5. **Vendored example and contract drift apart**: the README's H2 contract and the example feature files must agree after adding `Breaks`. Covered: Task 1 step 4 grep.

---

### Task 1: Vendor and adapt the verification skills

**Files:** `skills/create-verification-skill/{SKILL.md,references/feature-map-example/*.md}`, `skills/maintain-verification-skill/SKILL.md`, `vendor.lock`.

- [ ] **Step 1: Vendor** the five files from pstack@35a9094 with `scripts/vendor.py`. Run `python3 checks/run.py`. Expected: red only from `check_evals` for the two new skills, which Task 4 resolves. Commit `vendor: copy create- and maintain-verification-skill from pstack@35a9094`.
- [ ] **Step 2: Adapt `create-verification-skill/SKILL.md`:**
  - `.cursor/skills/` → `.agents/skills/` (lines 9, 25, 36).
  - Line 36: the H2 list gains `Breaks` (fifth).
  - Line 40, appended after the existing text, #1271's wording: "Then show it can fail. For the feature you drove, make one small deliberate break of the behaviour (in a scratch copy or reverted afterwards), run the journey, and confirm it fails at the check that names that behaviour. If it passes, the check is too loose: tighten it and try again. Record the break and the failing check under `## Breaks` in the feature file, so `/maintain-verification-skill` can replay it."
- [ ] **Step 3: Adapt `maintain-verification-skill/SKILL.md`:** line 25 path → `.agents/skills/verify-*/`; line 33 adds: "For every journey this pass changes, replay its recorded `Breaks`: each must still fail at its named check; a break that no longer fails is drift in the check, fix it before shipping."
- [ ] **Step 4: Adapt the example:** README contract "exactly four H2 sections" → five, with item 5: `Breaks` lists each deliberate break with the check it must fail at. Add a two-line `## Breaks` to `create-note.md` and `search.md`. Verify: `grep -c '^## ' references/feature-map-example/{create-note,search}.md` → 5 each.
- [ ] **Step 5:** `vendor.lock`: `adapted: true` on the four changed files. Run the unit suites + `validate_plugin`. Expected: green. Commit `adapt: verification skills for antigravity (#1271)`.

### Task 2: `agent-ready` and its Stop-hook template

**Files:**
- Create: `skills/agent-ready/SKILL.md`, `skills/agent-ready/templates/check_on_stop.py`, `skills/agent-ready/templates/hooks.json`, `skills/agent-ready/templates/check.yml`, `scripts/tests/test_check_on_stop.py`
- Modify: `vendor.lock` (`original`), `AGENTS.md` (Map, Rules), `README.md` (Spanish "Preparar otro repo")

**Interfaces:**
- Produces: `check_on_stop.py <check-cmd…>`. It reads the hook payload from stdin; the repo root is the parent of its own directory.
  - Prints nothing if `git status --porcelain` is empty.
  - Otherwise it runs the check from the root. On a non-zero exit, it prints `{"decision": "continue", "reason": "<check> failed:\n<last 60 lines>"}`.
  - It counts `continue`s in `$TMPDIR/agent-ready/<sha1(root)>-<conversationId>` and stops after 3.
  - It never raises: any exception means no output.

- [ ] **Step 1: Write the failing tests** (temp git repo with `.agents/check_on_stop.py` copied in, the check is a shell script toggled by a file):
  - `test_clean_tree_prints_nothing`;
  - `test_failing_check_continues_with_output` (the reason contains the check's stdout);
  - `test_passing_check_prints_nothing`;
  - `test_gives_up_after_three`;
  - `test_counter_is_per_conversation`;
  - `test_malformed_input_is_silent` (empty, non-JSON);
  - `test_missing_check_is_reported_once` (a missing check is a failure with a clear reason, still capped).
- [ ] **Step 2: Run** `python3 -m unittest discover -s scripts/tests -p 'test_check_on_stop.py'`. Expected: FAIL, module missing.
- [ ] **Step 3: Implement** the template, plus `templates/hooks.json` with the Global Constraints command and `timeout` 300, and `templates/check.yml`, which checks out the repo and runs `scripts/check`.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Write `SKILL.md`** (`disable-model-invocation: true`; description names `/agent-ready`). Steps:
  1. Read the repo: language, how it runs, its existing lint/type/test commands, its CI, its remote.
  2. Write `scripts/check`, one command that runs the repo's existing static checks and tests (add none the repo lacks beyond a syntax/compile pass), executable, the same locally and in CI.
  3. Copy `templates/check_on_stop.py` and `templates/hooks.json` into `.agents/`.
  4. Write `AGENTS.md`'s rule table per the **correct** skill's "Keep the rule table": each rule with what enforces it, the highest level first; prose only for judgment calls.
  5. Run `/create-verification-skill` by following the **create-verification-skill** skill, including its proof that each journey can fail.
  6. With a GitHub remote, copy `templates/check.yml` to `.github/workflows/check.yml`.
  7. Prove it: `scripts/check` passes. Break one thing on purpose: `scripts/check` fails, and the hook script fed `{"hookEventName":"Stop","conversationId":"proof"}` prints a `continue`. Restore, and both pass again.
  8. Report each artifact with its proof.
- [ ] **Step 6:** `vendor.lock` `original` entries; AGENTS.md Map line and Rules row "The generated Stop hook never loops and never blocks a clean finish" | `skills/agent-ready/templates/check_on_stop.py` `scripts/tests/test_check_on_stop.py`; README section. Run the unit suites + `checks/run.py` (red only for `check_evals`) + `validate_plugin`. Commit `feat(skills): agent-ready prepares a repo for agents`.

### Task 3: Eval case `agent-ready/habit-tracker`

**Files:** `evals/agent-ready/cases/habit-tracker/{prompt.md,rubric.md,check.py,case.json,project/habits.py,project/README.md}`, `evals/tests/test_agent_ready_case.py`.

- [ ] **Step 1: Project.**
  - `habits.py`: an argparse CLI with `add <name>`, `done <name>` and `list`. It stores JSON in `$HABITS_DATA` (default `~/.habits.json`). `list` prints `name  streak`.
  - `README.md`: how to run it.
  - No test files, and none of the banned words anywhere.
- [ ] **Step 2: Prompt:**

  > /agent-ready This is our habit tracker CLI. More and more changes here come from coding agents. Set the repo up so an agent working here gets stopped by checks instead of by me: one check command that runs the same locally and in CI, a hook that runs it before the agent finishes, rules with what enforces each, and a skill that drives the CLI the way a user does and proves a change works.

  Rubric (4 criteria):
  1. Read the repo before writing.
  2. Saw the check command fail on a deliberate break, then pass after restoring it.
  3. Ran the verify skill end to end and showed one journey failing on a deliberate break.
  4. The final reply lists each artifact with its proof.
- [ ] **Step 3: Write the failing tests** for `check.py` (fixtures built in temp dirs):
  - `test_hidden_check_rejects_bare_project`;
  - `test_hidden_check_accepts_reference_setup`: a hand-built minimal setup (AGENTS.md table, `scripts/check` = `python3 -m py_compile habits.py`, the real template hook, a verify skill skeleton);
  - `test_hidden_check_rejects_a_check_that_never_fails` (`scripts/check` = `true`);
  - `test_hidden_check_rejects_a_hook_that_never_continues`.
- [ ] **Step 4: Implement `check.py <work>`.** Outcome 1 only if all of these hold:
  - (a) `AGENTS.md` has a markdown table with at least one data row;
  - (b) an executable check exists (`scripts/check`, or `check.sh` / `bin/check` / a `check` Makefile target) and exits 0 on a copy of the work;
  - (c) on a copy with a syntax error appended to `habits.py`, that check exits non-zero;
  - (d) on that broken copy, every `Stop` command in `.agents/hooks.json`, run with cwd `.agents/` and the payload on stdin, yields at least one `"decision": "continue"`, and none on the clean copy;
  - (e) `.agents/skills/verify-*/SKILL.md` has frontmatter `name: verify-…`, plus `features/README.md` and at least one other feature file.

  It prints which part failed.
- [ ] **Step 5: Run** the tests + `python3 checks/run.py` (banned words, case layout). Expected: tests PASS; `check_evals` red only for missing results. Commit `evals: agent-ready habit-tracker case`.

### Task 4: Run the eval, record evidence, open the PR

- [ ] **Step 1:** Waivers for `create-verification-skill` and `maintain-verification-skill`. Reason: vendored and adapted (agy paths, #1271); exercised by the agent-ready eval, whose B arm runs `/create-verification-skill` through `agent-ready`.
- [ ] **Step 2:** `python3 evals/run.py agent-ready habit-tracker --base origin/main --variant HEAD` in the background (~90 min). Read every output and transcript per `eval.md`, applying **explain-the-number** to any gap, and record the verdict.
- [ ] **Step 3:** `docs/decisions/2026-11-19-m4-eval.md` (Spanish): the numbers, what explains them, and the limits.
- [ ] **Step 4:** Final whole-branch review by a fresh reviewer; fix pass; full verify; push; PR ready for review. The user merges it.
