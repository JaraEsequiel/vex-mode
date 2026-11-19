# vex-mode M2 (Evals) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure whether a skill change makes agy agents better. Each eval runs blinded candidates on three arms (base, variant, base on a better model), scores compliance with a cross-family judge, outcome with a hidden check and cost from transcripts, and stores a result tied to the skill's tree hash. CI requires such a result for every changed skill.

**Architecture:**
- pstack's `eval.md` playbook and `principle-explain-the-number` are vendored verbatim, then adapted.
- The mechanics of arena Phases B and C run in a deterministic Python harness (`evals/run.py` plus `evals/harness/`) that drives `agy -p --output-format stream-json`.
- Each arm installs a clean build of the plugin (`scripts/build_plugin.py`), because agy plugins are global and `agy plugin install` copies the whole folder, `evals/` included. The harness restores the user's installed plugin afterwards.
- `checks/check_evals.py` enforces blinding of case files, the result format, and the CI policy: changed skill ⇒ result for its current tree hash.

**Tech Stack:**
- Python 3 standard library only, tested with `unittest`.
- agy 1.5.11 (`agy -p`, `--model`, `--output-format stream-json|json`, `--json-schema`, `agy plugin install|uninstall`).
- GitHub Actions.

**Spec:** `docs/specs/2026-11-18-vex-mode-design.md` §8.2, §10b, §11 (revised 2026-11-18 after the source review).

## Global Constraints

- Python stdlib only. Tests use `unittest`. No network or model calls in unit tests; agy is replaced by a fake via the `VEX_AGY` env var.
- Vendoring follows `AGENTS.md` "How to bring in something that already exists": a `vendor:` commit byte-identical to pstack@`35a90942a7f02e1ebbc2443643179815f2147954`, then a separate `adapt:` commit.
- Banned words for anything a candidate sees, from `[P-eval:7]`: `eval`, `test`, `judge`, `experiment`, `rubric`, `score`, `compare`, `benchmark`, `candidate`, `arena`.
- The judge's model family differs from every candidate's family `[P-eval:21]`. Families: `claude-*` → claude, `gemini-*` → gemini, `gpt-*` → gpt, anything else → text before the first `-`.
- Three arms, fixed: `A` = base plugin + `candidate_model`; `B` = variant plugin + `candidate_model`; `C` = base plugin + `upgrade_model` `[I-1178]`.
- Default `runs` per arm: 3 `[P-explain]`.
- Text the agent reads is in English; human docs are in Spanish.
- Plugin parts exported by the build: `plugin.json`, `skills/`, `agents/`, `rules/`, `hooks.json`, `hooks/` (without `hooks/tests/`), `LICENSES/`. Never `__pycache__`.

## Review Focus

1. **The harness fails mid-arm** (agy crash, Ctrl-C, timeout). The user's original plugin must still be reinstalled. Covered: `test_restores_plugin_when_a_run_fails` (Task 5).
2. **A candidate reads outside its sandbox**: the run dir with the judge's files, the vex-mode repo, or a skill copy other than the arm's install. That run must be invalidated, not graded. Covered: `test_flags_reads_of_run_dir_and_repo` (Task 4).
3. **A run that did not finish** (no `result` event, status not `SUCCESS`, timeout) must count as a failed outcome with zero compliance. It must not be dropped. Covered: `test_unfinished_run_counts_as_failure` (Task 4).
4. **CI's clone has no `origin/main`**: the policy check must fail loudly, never pass by skipping. Covered: `test_unresolvable_base_is_an_error` (Task 3), plus `fetch-depth: 0` in CI (Task 7).
5. **The judge returns malformed JSON or misses a label**: no compliance number may be invented. The result records `judge_error`, and the check rejects a non-waiver result without compliance. Covered: `test_judge_missing_label_sets_error` (Task 5).

---

### Task 1: Clean plugin build

**Files:**
- Create: `scripts/build_plugin.py`, `scripts/tests/test_build_plugin.py`
- Modify: `README.md` (install section), `AGENTS.md` (Map + Rules row)

**Interfaces:**
- Produces: `build(repo_root: Path, out: Path, ref: str | None = None) -> Path`. With `ref`, export from `git archive <ref>`; without it, export the working tree. Copy only `PLUGIN_PARTS`. Return `out`.
- Produces: CLI `python3 scripts/build_plugin.py [--ref REF] [--install] <out>`. `--install` runs `$VEX_AGY plugin uninstall vex-mode` (ignore failure) and then `$VEX_AGY plugin install <out>`. `VEX_AGY` defaults to `agy`.

- [ ] **Step 1: Write the failing tests** in `scripts/tests/test_build_plugin.py`, using a temp git repo:
  - `test_exports_only_plugin_parts`: a repo with `plugin.json`, `skills/x/SKILL.md`, `hooks/a.py`, `hooks/tests/t.py`, `hooks/__pycache__/a.pyc`, `evals/x/rubric.md`, `docs/d.md`, `AGENTS.md`. Assert the output set of relative files equals `{plugin.json, skills/x/SKILL.md, hooks/a.py}`.
  - `test_ref_exports_committed_content`: commit `SKILL.md` = "v1", then edit the working tree to "v2". `build(..., ref="HEAD")` gives "v1"; `build(...)` gives "v2".
  - `test_out_is_replaced`: a stale file in `out` is gone after a build.
- [ ] **Step 2: Run** `python3 -m unittest discover -s scripts/tests -p 'test_build_plugin.py' -v`. Expected: FAIL, module missing.
- [ ] **Step 3: Implement `build`**: `git archive <ref> | tar -x` into a temp dir, then copy the filtered parts.
- [ ] **Step 4: Run the tests.** Expected: 3 PASS. Then run the full M1 verify command. Expected: all green.
- [ ] **Step 5: Reinstall the user's plugin clean:** `python3 scripts/build_plugin.py --install <scratch>/vex-mode-build`. Then `ls ~/.gemini/config/plugins/vex-mode`. Expected: no `.git`, `docs`, `checks`, `scripts` or `AGENTS.md`. `agy plugin list` shows 10 skills, 1 agent, 1 rule, 3 hooks.
- [ ] **Step 6: Docs and rule.** README install becomes the `--install` command. AGENTS.md gets the Rules row: "The plugin is installed only from a clean build (no repo files in the installed copy)" | `scripts/build_plugin.py` `scripts/tests/test_build_plugin.py`.
- [ ] **Step 7: Commit** `feat(scripts): build the plugin from its parts only`.

### Task 2: Vendor and adapt eval + explain-the-number

**Files:**
- Vendor: `pstack/skills/poteto-mode/playbooks/eval.md` → `skills/vex-mode/playbooks/eval.md`; `pstack/skills/principle-explain-the-number/SKILL.md` → `skills/principle-explain-the-number/SKILL.md`
- Modify (adapt): those two files, `skills/vex-mode/SKILL.md`, `vendor.lock`

**Interfaces:**
- Consumes: `scripts/vendor.py` (M1). Upstream checkout at pstack@`35a9094`, re-cloned to the scratchpad if missing.
- Produces: the playbook path `skills/vex-mode/playbooks/eval.md`, read by Task 6's case and by the router.

- [ ] **Step 1: Vendor** both files with `scripts/vendor.py`. Run `python3 checks/run.py`. Expected: `check_skills` reports the dangling refs `arena` (eval.md) and `../benchmark-checklist/SKILL.md` (explain-the-number). Record them as `pending_refs` so the vendor commit is green. Commit `vendor: copy eval playbook and explain-the-number from pstack@35a9094`.
- [ ] **Step 2: Adapt `eval.md`.** Keep lines 1-17 and 23-25 verbatim except where noted.
  - Step 4 becomes: run the candidates with `python3 evals/run.py <skill> <case>` from the vex-mode source repo. It builds the three arms, installs each arm's plugin build, runs one `agy -p` per candidate in its own sanitized dir, and restores the installed plugin.
  - Step 5 becomes: the same command runs one blinded judge from `judge_model`, of a different model family than every candidate; the judge sees outputs by sanitized label and the rubric, never a model name.
  - Step 6: replace the Cursor transcript path with "each candidate's `stream-json` transcript in the run directory the harness prints", and drop the `~/.cursor/projects` sentence. Keep the rest verbatim.
  - Step 1 Frame gets one sentence `[I-1178]`: "Pair the rubric with the case's outcome check and report cost; change one lever per comparison." Step 7 gets one sentence: "Record the decision with `python3 evals/run.py verdict <result> <promote|reject|inconclusive> "<synthesis>"`, per the **principle-explain-the-number** skill."
- [ ] **Step 3: Adapt the other two files.**
  - `principle-explain-the-number`: drop the benchmark-checklist sentence.
  - `skills/vex-mode/SKILL.md`: restore the upstream `- **Explain the Number.** …` bullet verbatim at the end of **Verification** (upstream line 63), and change the playbook list to `Bug fix, Feature, Opening a PR, Eval.`
  - `vendor.lock`: set `adapted: true` on all three files. Move `arena` and `benchmark-checklist` to `removed_refs`. Remove `playbooks/eval.md` and `principle-explain-the-number` from the router's `removed_refs`.
- [ ] **Step 4: Verify.** Run the full verify command. Expected: green, with `check_vendor` ok and no stale pending refs.
- [ ] **Step 5: Commit** `adapt: eval playbook and explain-the-number for antigravity`. The body lists the #1178 sentence as a deliberate deviation (design §11).

### Task 3: `checks/check_evals.py`

**Files:**
- Create: `checks/check_evals.py`, `checks/tests/test_check_evals.py`
- Modify: `checks/_util.py`

**Interfaces:**
- Produces in `_util.py`: `skill_tree_sha256(skill_dir: Path) -> str`. It is sha256 over the sorted lines `f"{relpath}\0{sha256(bytes)}\n"` of every file, skipping `__pycache__`.
- Produces: `BANNED = ("eval","test","judge","experiment","rubric","score","compare","benchmark","candidate","arena")`, and `banned_hits(text: str) -> list[str]`. To compute hits, split on non-letters and camelCase boundaries, lowercase, and report each token that starts with a banned word.
- Produces: `changed_skills(root: Path, base: str) -> set[str]` (via `git diff --name-only <base>...HEAD -- skills/`), and `run(root: Path) -> list[str]`. The base comes from env `VEX_BASE_REF`, default `origin/main`.
- Result JSON (written by Task 5):
  - Common fields: `{"kind": "eval"|"waiver", "skill": str, "tree_sha256": hex64, "date": "YYYY-MM-DD"}`.
  - Waiver adds `"reason": str` (non-empty).
  - Eval adds:
    - `"case": str` and `"run_dir": str`.
    - `"arms"`: for each of `A`, `B` and `C`, `{"model", "plugin_ref", "tree_sha256", "runs": [...]}`.
    - `"judge"`: `{"model", "error": str|null}`.
    - `"metrics"`: for each arm, `{"compliance", "outcome", "tokens", "duration_s"}`, each holding `{"mean","min","max","spread"}`.
    - `"signals"`: for `B_vs_A` and `C_vs_A`, a map from metric to `"better"|"worse"|"noise"`.
    - `"verdict": "promote"|"reject"|"inconclusive"|null` and `"synthesis": str|null`.

- [ ] **Step 1: Write the failing tests** (temp repos via `_helpers.make_repo`, plus `git init` where the policy needs it):
  - `test_tree_hash_changes_with_any_file`: editing a playbook changes the hash; adding `__pycache__/x.pyc` does not.
  - `test_banned_hits_catch_inflections_and_camel`: hits for `"tests/"`, `"evaluation"`, `"myJudge"`, `"foo_test"`; none for `"latest"` or `"contest"`.
  - `test_case_layout_required`: a case missing `check.py` gives an error naming the path.
  - `test_banned_word_in_prompt_project_or_workdir`: one error each for `prompt.md` containing "evaluate", a file `project/test_x.py`, and a `case.json` `workdir` of `"rubric-app"`.
  - `test_case_json_fields`: requires `runs >= 1`, `candidate_model`, `upgrade_model`, `judge_model`, `workdir` matching `^[a-z0-9-]+$`, and `timeout_s`.
  - `test_judge_same_family_rejected`: `judge_model` `gemini-4-neon-high` with candidate `gemini-…` is an error.
  - `test_result_schema`: a waiver without a reason is an error; an eval with a judge error and no compliance is an error; an eval with `verdict: null` is an error.
  - `test_changed_skill_requires_matching_result`: on a branch that edits `skills/x/SKILL.md`, there is an error until `evals/x/results/r.json` carries the new tree hash, and none after.
  - `test_unchanged_skills_need_nothing`: base == HEAD gives no policy errors.
  - `test_unresolvable_base_is_an_error`: `VEX_BASE_REF=nope` gives exactly one error that names `VEX_BASE_REF`.
  - `test_evals_dir_without_skill`: `evals/ghost/` with no `skills/ghost/` is an error.
- [ ] **Step 2: Run.** Expected: FAIL, module missing.
- [ ] **Step 3: Implement** `check_evals.run`, using the shared helpers from `_util.py`. The family rule lives in `_util.model_family(model: str) -> str`, which Task 4 reuses.
- [ ] **Step 4: Run** the new tests (all PASS), then the full verify command. On `m2`, `check_evals` must now report the changed skills `vex-mode` and `principle-explain-the-number` as missing results. That is expected until Task 6. Rule: the full verify command may be red only with those two errors until Task 6.
- [ ] **Step 5: Commit** `feat(checks): eval case blinding, result format and changed-skill policy`.

### Task 4: Harness core (pure functions)

**Files:**
- Create: `evals/harness/__init__.py`, `evals/harness/transcript.py`, `evals/harness/arms.py`, `evals/harness/isolation.py`, `evals/harness/stats.py`, `evals/tests/test_harness.py`, `evals/tests/fixtures/run_ok.ndjson`, `evals/tests/fixtures/run_unfinished.ndjson`

**Interfaces:**
- `transcript.parse(text: str) -> Transcript`. The dataclass fields are `conversation_id: str|None`, `model: str|None`, `reads: list[str]` (`read_file` `Path` params), `commands: list[str]` (`run_command` `CommandLine`), `status: str` (`"SUCCESS"`, the result status, or `"UNFINISHED"` without a result event), `total_tokens: int`, `duration_s: float` and `response: str`. Use the probed event shapes: `init`, `step_update` with `tool_info.parameters`, and `result` with `usage.total_tokens`.
- `arms.build_arms(case: dict, base_ref: str, variant_ref: str) -> list[Arm]`. `Arm(label: str, plugin_ref: str, model: str)`, in A, B, C order per Global Constraints. Raises `ValueError` if the judge's family equals any arm model's family (uses `checks/_util.model_family`).
- `isolation.violations(t: Transcript, *, plugin_root: Path, forbidden: list[Path]) -> list[str]`. Flags any read under a `forbidden` root (run dir, repo root), and any read of a `skills/` path that is not under `plugin_root`.
- `stats.summarize(xs: list[float]) -> dict` returns `{"mean","min","max","spread"}`, where spread = max - min. `stats.signal(a: dict, b: dict) -> str` returns `"noise"` when `abs(b.mean - a.mean) <= max(a.spread, b.spread)`, otherwise `"better"` or `"worse"` (higher is better). The caller passes negated values for tokens and duration.

- [ ] **Step 1: Write the failing tests:**
  - `test_parse_reads_commands_usage`: on `run_ok.ndjson`, a trimmed copy of the 2026-11-18 probe output, expect reads `[".../notes.txt"]`, commands `['find . -name "notes.txt"']`, status `SUCCESS`, tokens `15184`.
  - `test_unfinished_run_counts_as_failure`: `run_unfinished.ndjson` has no result event, so the status is `UNFINISHED`.
  - `test_arms_fixed_order_and_levers`: A and B differ only in `plugin_ref`; A and C differ only in `model`.
  - `test_judge_family_must_differ`.
  - `test_flags_reads_of_run_dir_and_repo`: reads of `/run/x/rubric.md` and of the repo root are flagged; a read under `plugin_root/skills/` is not; a read of `/elsewhere/skills/vex-mode/SKILL.md` is flagged.
  - `test_signal_noise_and_direction`.
- [ ] **Step 2: Run** `python3 -m unittest discover -s evals/tests -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the four modules.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(evals): transcript parsing, arms, isolation and stats`.

### Task 5: `evals/run.py` orchestration

**Files:**
- Create: `evals/run.py`, `evals/harness/judge.py`, `evals/tests/test_run.py`, `evals/tests/fake_agy.py`

**Interfaces:**
- CLI `python3 evals/run.py <skill> <case> [--base REF] [--variant REF] [--runs N]`. `--base` defaults to `git merge-base origin/main HEAD`, and `--variant` defaults to `HEAD`. The variant must be a commit; refuse a dirty `skills/` tree. Prints the run dir and the result path.
- CLI `python3 evals/run.py verdict <result.json> <promote|reject|inconclusive> "<synthesis>"` sets the `verdict` and `synthesis` fields.
- `judge.build_prompt(rubric: str, items: list[tuple[str, str]]) -> str`, where each item is a label and that run's material: the final response, `git diff` against the initial commit, and the list of files read. Labels are `R1…Rn`, shuffled with `random.Random(seed)`; the label→arm map stays only in the run dir.
- `judge.SCHEMA` is `{"runs":[{"label":str,"criteria":[{"name":str,"pass":bool,"note":str}]}]}`.
- `judge.compliance(verdict: dict, label: str) -> float | None`. Returns `None` when the label is missing.
- Flow:
  1. Lock `~/.cache/vex-mode/eval.lock`.
  2. Back up `~/.gemini/config/plugins/vex-mode` to the run dir.
  3. For each arm: `build_plugin.build(ref)`, then uninstall and install via `$VEX_AGY`, then check that the installed `skills/<skill>` tree hash equals the build's hash.
  4. For each run: copy `project/` into `~/.cache/vex-work/<workdir>-<k>` (k is 1..9 across all arms, shuffled so the arm doesn't show), then `git init` and commit. Run `$VEX_AGY -p <prompt> --model <m> --output-format stream-json --print-timeout <timeout_s>s` with cwd=workdir and save the ndjson to the run dir. Then run `python3 -I <case>/check.py <workdir>`, where exit 0 means outcome 1.
  5. In a `finally` block, reinstall the backup.
  6. Run the judge in an empty dir: `$VEX_AGY -p <prompt> --model <judge> --output-format json --json-schema <schema file>`.
  7. Compute the metrics and write `evals/<skill>/results/<date>-<tree12>.json`.
  - Invalidated or unfinished runs count as outcome 0, compliance 0 and `"invalid": reason`.
  - The run dir is `~/.cache/vex-mode/runs/<stamp>/`, and it is in `forbidden` for isolation.

- [ ] **Step 1: Write `fake_agy.py`.** It is driven by env `FAKE_AGY_MODE`:
  - `plugin install` copies the source to `$FAKE_HOME/plugins/vex-mode`.
  - `-p` with stream-json writes an ndjson file that reads the installed SKILL.md, edits a file, and emits a result; or, in mode `crash`, exits 1 with no result.
  - `-p` with `--json-schema` prints a judge verdict for the labels it finds in the prompt; in mode `badjudge`, it omits one label.
  
  The harness reads the plugin root from `VEX_PLUGIN_HOME`, default `~/.gemini/config/plugins`, so tests point it at `$FAKE_HOME/plugins`.
- [ ] **Step 2: Write the failing tests** in `test_run.py`, using a temp git repo with one skill, one case and a `check.py` that passes when a file was edited:
  - `test_end_to_end_with_fake_agy`: the result file exists, has three arms with N runs each, every metric is present, `verdict` is null, and the installed plugin equals the backup afterwards.
  - `test_restores_plugin_when_a_run_fails`: mode `crash` on the second run. The installed plugin is restored, and that run is recorded as `UNFINISHED` with outcome 0.
  - `test_judge_missing_label_sets_error`: mode `badjudge` leads to `judge.error` being set and compliance `null` for the missing label, with no invented number.
  - `test_labels_hide_arms`: the judge prompt contains no model name, arm letter, or banned word except in the rubric section.
  - `test_refuses_dirty_variant`.
  - `test_verdict_subcommand_sets_fields`.
- [ ] **Step 3: Run.** Expected: FAIL.
- [ ] **Step 4: Implement** `judge.py` and `run.py`.
- [ ] **Step 5: Run** the evals tests (PASS), then the full verify command. The only expected red is the two policy errors from Task 3.
- [ ] **Step 6: Commit** `feat(evals): harness that runs arms, judge and writes results`.

### Task 6: First real case and the M2 results

**Files:**
- Create: `evals/vex-mode/cases/<slug>/{prompt.md,rubric.md,check.py,case.json,project/…}`, `evals/vex-mode/results/<date>-<tree12>.json`, `evals/principle-explain-the-number/results/<date>-<tree12>.json` (waiver), `docs/decisions/2026-11-18-m2-first-eval.md`

**Interfaces:**
- Consumes: Tasks 3-5.
- The case is a bug fix in a tiny stdlib Python project. Pick a project-shaped slug with no banned words.
  - Planted bug: a money total off by one cent from float rounding.
  - `prompt.md`: a user's organic report that starts with `/vex-mode`.
  - `check.py`: hidden assertions that import the fixed module from the given workdir.
  - `rubric.md`, 4 criteria:
    1. The reply opens with the goal.
    2. The bug was reproduced by a run that fails before the edit. The judge reads this from the command order in the material.
    3. The fix is at the root cause (decimal money), not a rounding guard at the output.
    4. The reply shows verification output from a real run.
  - `case.json`: `runs` 3, `candidate_model` `gemini-4-neon-medium`, `upgrade_model` `gemini-4-neon-high`, `judge_model` `claude-opus-5-5-high`, `timeout_s` 900.

- [ ] **Step 1: Write the case.** `python3 checks/run.py`: `check_evals` shows no blinding errors for the case.
- [ ] **Step 2: Prove the outcome check can fail** (#1271's lesson). `python3 -I check.py <fresh copy of project/>` exits non-zero on the unfixed project. After a hand-applied correct fix in a scratch copy, it exits 0.
- [ ] **Step 3: Commit the case** (`feat(evals): vex-mode bug-fix case`). Then run the real eval: `python3 evals/run.py vex-mode <slug>`. Expected: a result with 9 runs, no `invalid` runs (if any exist, read why and fix the harness before rerunning), and the installed plugin restored (`agy plugin list` unchanged).
- [ ] **Step 4: Read every candidate output yourself** (eval.md step 7) and compare it with the judge. Then run `python3 evals/run.py verdict <result> <…> "<synthesis>"`. The expected signal for `B_vs_A` is noise, because M2 only adds the Eval playbook and the explain-the-number line. Write the evidence, the numbers with their spread, and any disagreement with the judge in `docs/decisions/2026-11-18-m2-first-eval.md`.
- [ ] **Step 5: Waiver** for `principle-explain-the-number`. Reason: it is vendored, read only from the eval playbook, and has no behavior to measure on its own. Record it with the current tree hash.
- [ ] **Step 6: Run the full verify command.** Expected: all green, `check_evals` ok.
- [ ] **Step 7: Commit** `feat(evals): first vex-mode eval result and explain-the-number waiver`.

### Task 7: CI, rules and docs

**Files:**
- Modify: `.github/workflows/ci.yml`, `AGENTS.md`, `README.md`

- [ ] **Step 1: CI.** In `actions/checkout@v4`, set `fetch-depth: 0`. Add `python3 -m unittest discover -s evals/tests -v` to Unit tests. `checks/run.py` already runs `check_evals`.
- [ ] **Step 2: AGENTS.md.**
  - The verify command gains the evals tests.
  - The Map gains `evals/` and `scripts/build_plugin.py`.
  - A new section, "How to change a skill": run `python3 evals/run.py <skill> <case>`, read the outputs, record the verdict; or add a waiver with a reason. A PR without either fails CI.
  - Rules rows, each with its enforcer:
    - "A PR that changes a skill carries an eval result or waiver for that skill's tree hash" | `checks/check_evals.py` `checks/tests/test_check_evals.py`.
    - "Nothing a candidate sees contains a banned word" | `checks/check_evals.py`.
    - "The judge is from another model family" | `checks/check_evals.py` `evals/harness/arms.py`.
    - "Every eval measures compliance, outcome and cost on three fixed arms" | `evals/harness/arms.py` `evals/tests/test_run.py`.
    - "An eval never leaves a variant installed" | `evals/run.py` `evals/tests/test_run.py`.
- [ ] **Step 3: README** in Spanish: how to run an eval and where the results are.
- [ ] **Step 4: Run the full verify command.** Expected: green. Push `m2`, open a ready PR, and wait for CI to be green.
- [ ] **Step 5: Commit** `ci: run eval tests and enforce the eval policy` (before the push in step 4).
