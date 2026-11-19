# vex-mode M5: code quality in evals — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every eval of a case with `"quality": true` records a fourth measure, code quality, computed only on runs that pass the outcome check, and `promote` is refused (by `run.py verdict` and by CI) when outcome or a blocking quality measure gets worse or errors.

**Architecture:**
- `evals/harness/quality.py`: deterministic measures computed from a before dir (the case `project/`) and an after dir (the project with the run's saved diff applied). Uses only `ast`, `tokenize` and `difflib`, plus the hidden `check.py` as the oracle for `removable_lines`.
- `evals/harness/quality_judge.py`: three dimensions (`reuse`, `simplicity`, `contract`). Each dimension gets 3 separate calls through the existing `judges.judge`, and a run's result needs at least 2 matching votes.
- `run.py`: wires both into `run_eval` and `rejudge`. It scores them with `stats` and gates `verdict`.
- `checks/_util.py`: holds the gate (`promote_blockers`) so that `run.py` and `checks/check_evals.py` apply the same rule.

**Tech Stack:** Python 3 stdlib only (`ast`, `tokenize`, `difflib`, `subprocess`, `unittest`). Fake judge through the existing `test_judges.FakeAPI`.

**Spec:** `docs/specs/2026-11-18-vex-mode-design.md` §8.2.1 (approved 2026-11-19).

## Sources read for this plan (2026-11-19)

| Source | What it settles here |
|---|---|
| R-anthropic, R-ruver, R-slopcode, R-trim, R-l2c, R-milestone, R-patchbench, R-metr (re-read 2026-11-19, rows in design §13) | The measures, one dimension per judge call, 3 votes, `unknown`, CC·√SLOC, TRIM-NG passes |
| `evals/run.py`, `evals/harness/{judge,judges,stats}.py`, `checks/check_evals.py` | `judges._verdict` and `judge.parse_output` hardwire the compliance shape; `_diff` truncates at 20 000 chars before saving; `_score` handles only `METRICS`; `check_evals` requires `{mean,min,max,spread}` for every metric |
| Run `20261119-145054-789891` | Saved diffs use `c/` and `i/` prefixes (apply with `-p1`). The 4 passing runs touched `invoices.py` and `test_invoices.py` |

## Global Constraints

- Python stdlib only. No `bandit`, `ruff` or `ast-grep`. Unit tests never touch the network.
- Quality runs only for cases whose `case.json` has `"quality": true`. Set it on `evals/vex-mode/cases/tax-rounding`, not on `habit-tracker`.
- A run gets quality only if it is valid and `outcome == 1`.
- Test files: basename `test_*.py` or `*_test.py`, or any path segment `tests`. Every other file is production, including leftover scripts.
- Blocking measures: `prod_lines`, `removable_lines`, `complexity_delta`, `verbosity`, `comments_added`, `security_findings`, `judge_reuse`, `judge_simplicity`, `judge_contract`. Informative: `test_lines`, `docstrings_added`.
- Lower is better for every deterministic measure; higher is better for `judge_*` (1.0 pass, 0.0 fail).
- Signal values: `better` / `worse` / `noise` (from `stats.signal`), `few` (fewer than 2 non-null values in either arm), `error` (any passing run of either arm has an error for that measure).
- Quality judge: the configured judge (`evals/judge.json`). 3 calls per dimension. A run gets `pass`/`fail` only when at least 2 votes match; otherwise `None`. `unknown` is a vote that counts for nothing.
- The gate refuses `promote` when `signals.B_vs_A.outcome == "worse"`, or when any blocking quality signal in `B_vs_A` is `worse` or `error`.
- CI requires quality metrics for results of quality cases dated `>= 2026-11-20`. Older results are exempt.
- Text an agent reads (code, prompts, commits) is in English. Docs for humans are in Spanish.
- The other session owns `skills/`, `vendor.lock` and `evals/*/results/`. This plan touches none of them. Do not run `evals/run.py` against the real plugin.

## Review Focus

1. **A saved diff that does not apply** (truncated by the old 20 000-char limit, or a binary file): quality for that run must be an error that names the run, not a crash that loses the eval. Tested in Task 2 (`test_unappliable_diff_is_an_error`).
2. **A `check.py` that hangs or fails on the unmodified after dir** during `removable_lines`: the measure becomes an error, with each check call limited to 30 s. Tested in Task 2 (`test_removable_check_timeout_is_error`, `test_removable_requires_passing_baseline`).
3. **An after file with a syntax error** (for example, a broken test file next to working production code): the AST measures skip that file and record an error for it. They do not crash. Tested in Task 2 (`test_syntax_error_file_is_reported`).
4. **A judge reply with missing, duplicated or unknown labels on one vote:** that vote is discarded and an error is recorded, and the other votes still count. Tested in Task 3 (`test_bad_vote_is_discarded_and_reported`).
5. **A hand-edited `promote` on a committed result with a `worse` signal:** CI fails. Tested in Task 5 (`test_promote_with_worse_quality_fails`).

---

### Task 1: Design renderer understands `[R-…]`, `[RUN]` and `### 8.2.1`

**Files:**
- Modify: `scripts/render_design.py` (`TAG`, `CLASSES`, `H3`)
- Modify: `scripts/design_template.html` (styles for `a.s.r`, `a.s.run`)
- Test: `scripts/tests/test_render_design.py`
- Regenerate: `docs/specs/2026-11-18-vex-mode-design.html`

**Interfaces:** none consumed or produced outside the renderer.

- [ ] **Step 1: Write the failing tests** in `RenderTest`:
  - `test_research_and_run_tags_link`: rendering a doc whose table has rows `R-trim` and `RUN`, with body text `` `[R-trim]` `` and `` `[RUN]` ``, gives `class="s r"` and `class="s run"` links whose `href` points to the anchors of those rows.
  - `test_h3_with_three_part_number`: a `### 8.2.1 Calidad` line renders as an `<h3>` with an id, and the text includes `8.2.1`.
- [ ] **Step 2: Run** `python3 -m unittest scripts.tests.test_render_design -v`. Expected: the 2 new tests FAIL.
- [ ] **Step 3: Implement.**
  - `TAG` also accepts `R-[\w-]+` and `RUN`.
  - `CLASSES` gains `"R": "r"` and `"RUN": "run"`.
  - `H3` accepts an optional third number. Its id joins every number with `-`.
  - The template gives `.r` and `.run` a distinct color, following the existing pattern at `design_template.html:54-55`.
- [ ] **Step 4: Run** `python3 scripts/render_design.py && python3 -m unittest scripts.tests.test_render_design -v`. Expected: all pass, `test_committed_html_is_current` included.
- [ ] **Step 5: Commit** the renderer, template, test, design `.md` and `.html` as `docs: design M5 code quality in evals (§8.2.1)`.

### Task 2: `evals/harness/quality.py`, the deterministic measures

**Files:**
- Create: `evals/harness/quality.py`
- Create: `evals/tests/test_quality.py`
- Create: `evals/tests/fixtures/quality/good_invoices.py` (production file from slot 9 of run `20261119-145054-789891`, test file excluded)

**Interfaces:**
- Produces:
  - `DETERMINISTIC: tuple[str, ...]` = `("prod_lines", "test_lines", "removable_lines", "complexity_delta", "verbosity", "comments_added", "docstrings_added", "security_findings")`.
  - `is_test(rel: str) -> bool`.
  - `apply_diff(project: Path, diff: str, dest: Path) -> str | None`: copies `project` to `dest` and applies `diff` with `git apply -p1`. Returns an error string or `None`.
  - `measure_dirs(before: Path, after: Path, check: Path | None) -> tuple[dict[str, float | None], dict[str, str]]`: returns (values per measure, error per measure). `check=None` makes `removable_lines` `None` without an error.
  - `measure(project: Path, diff: str, check: Path) -> tuple[dict, dict]`: `apply_diff` into a temp dir, then `measure_dirs`. If the diff does not apply, every measure is `None` and every error is set.
  - `cc(node: ast.AST) -> int` and `mass(source: str) -> float`.

- [ ] **Step 1: Write the failing tests** in `evals/tests/test_quality.py`. `before` = `evals/vex-mode/cases/tax-rounding/project`, `good` = before with `invoices.py` replaced by the fixture, `check` = the case's `check.py`. Each `worse_*` is `good` plus one planted change:
  - `test_is_test`: `test_x.py`, `x_test.py` and `tests/a.py` are tests; `invoices.py` and `repro.py` are not.
  - `test_good_patch_baseline`: on `good`, `comments_added == 0`, `security_findings == 0`, `removable_lines == 0`, and `prod_lines` equals the `+`/`-` line count of slot 9's production hunk (count it from the fixture with `difflib`; it is between 10 and 16).
  - `test_comment_is_worse`: a `# explain` line added inside `invoice_total` makes `comments_added == 1`.
  - `test_dead_code_is_removable`: an unused function `def _unused(x):\n    return x * 2` added gives `removable_lines >= 2`, and `prod_lines` is greater than in `good`.
  - `test_leftover_script_is_removable`: a new `repro.py` with 3 lines counts in `prod_lines` and `removable_lines == 3`.
  - `test_shell_true_is_insecure`: `import subprocess` and `subprocess.run("ls", shell=True)` inside a new function give `security_findings == 1`. Each other rule from §8.2.1 gets its own one-line case in a `subTest` loop: `eval`, `exec`, `os.system`, `os.popen`, `pickle.loads`, `marshal.loads`, `yaml.load(x)` (while `yaml.load(x, Loader=yaml.SafeLoader)` gives 0), `requests.get(u, verify=False)`, `ssl.CERT_NONE`, `ssl._create_unverified_context()`, `tempfile.mktemp()`, `hashlib.md5()`, `hashlib.sha1()`, `api_key = "abc123"`.
  - `test_needless_abstraction_raises_complexity`: replacing the rounding with a function that branches 3 ways on a `mode` argument gives `complexity_delta` greater than in `good`.
  - `test_cc_counts_branches`: `cc` of `def f(x):\n if x and y: pass\n for i in x: pass` is 4 (1 + if + `and` + for).
  - `test_verbosity_rules`: each of the following, added to `good` as a new function, makes `verbosity` greater than in `good`, one `subTest` each:
    - a loop with `append` into a list that is then returned;
    - `if len(x) == 0:`;
    - `== True`;
    - an intermediate name returned on the next line;
    - an `else` after `return`;
    - `except Exception:\n    pass`;
    - a 3-line block that appears twice (clone).
  - `test_docstring_is_informative`: a new docstring gives `docstrings_added == 1` and leaves `comments_added == 0`.
  - `test_test_lines_counted_apart`: a new `test_invoices.py` with 5 lines gives `test_lines == 5`, and `prod_lines` stays the same as in `good`.
  - `test_unappliable_diff_is_an_error`: `measure(before, "garbage\n[diff truncated]", check)` returns all values `None` and an error for each measure that mentions `apply`.
  - `test_removable_check_timeout_is_error`: with a `check.py` that sleeps, `removable_lines` is `None` and its error mentions `timed out`. The test passes `timeout_s=1` through `measure_dirs(..., timeout_s=1)`; the default is 30.
  - `test_removable_requires_passing_baseline`: a check that always exits 1 makes `removable_lines` `None`, with the error `check fails on the patch itself`.
  - `test_syntax_error_file_is_reported`: a broken `test_x.py` next to `good` records an error naming `test_x.py` under `comments_added`, and `prod_lines` is still a number.
  - `test_measure_applies_saved_diff`: the real `diffs/9.diff` text, copied into `fixtures/quality/slot9.diff`, gives the same values through `measure` as `good` plus its test file through `measure_dirs`.
- [ ] **Step 2: Run** `python3 -m unittest discover -s evals/tests -p 'test_quality.py' -v`. Expected: FAIL, `No module named 'harness.quality'`.
- [ ] **Step 3: Implement** `evals/harness/quality.py`.
  - **Changed files:** every file that differs between `before` and `after`, `__pycache__` excluded.
  - **Line ops:** `difflib.SequenceMatcher(None, a_lines, b_lines, autojunk=False).get_opcodes()` per file. Every deleted line and every inserted line is one op. `prod_lines` / `test_lines` = the op count of production / test files.
  - **Added lines:** the 1-based after-line numbers of inserted ops. Rules, clones, comments and docstrings count only nodes or tokens that start on an added line.
  - **`removable_lines`:** run `check` on `after` first, with each call limited to `timeout_s`. If it does not exit 0, record the error. Then two passes over the production ops: whole opcodes first, last to first, then single ops in what remains, last to first. Revert a unit (restore its deleted lines, drop its inserted lines) in a scratch copy, run the check, and keep the revert only if the check exits 0. The value is the number of reverted ops. The check runs as `[sys.executable, "-I", check, scratch_dir]`, the same way as `run._outcome`.
  - **`cc`:** 1 plus the count of `If`, `For`, `AsyncFor`, `While`, `IfExp`, `ExceptHandler`, `With`, `AsyncWith`, `Assert`, `comprehension` (plus its `ifs`) and `match_case`, plus `len(values) - 1` for each `BoolOp`. Nested functions are counted on their own and not in their parent.
  - **`mass`:** Σ over functions of `cc(f) * sqrt(sloc(f))`. SLOC = non-blank, non-comment lines in the function's span.
  - **`complexity_delta`:** `mass(after) - mass(before)`, summed over the changed production `.py` files.
  - **`verbosity`:** |flagged added prod lines ∪ clone lines| ÷ added prod lines, or 0.0 when there are none. A clone line is part of a window of 3 consecutive normalized (stripped, non-blank) added lines that occurs again anywhere in the same file.
  - **`security_findings`:** per `.py` file, `max(0, hits(after) - hits(before))`, summed. `hits` are the AST rules in the global list above. The secret rule matches an `Assign` of a `str` constant to a `Name` whose id contains `key`, `secret`, `token` or `password` (case-insensitive).
  - **Errors:** a file that `ast.parse` or `tokenize` rejects is skipped for the AST and token measures, and its error is recorded as `"<rel>: SyntaxError …"`.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(evals): deterministic code-quality measures (stdlib)`.

### Task 3: `evals/harness/quality_judge.py` and a schema-driven judge reply check

**Files:**
- Create: `evals/harness/quality_judge.py`
- Modify: `evals/harness/judges.py` (`_verdict`), `evals/harness/judge.py` (`parse_output`)
- Test: `evals/tests/test_quality_judge.py`, `evals/tests/test_judges.py`

**Interfaces:**
- Consumes: `judges.judge(prompt, schema, cfg, cwd) -> (dict | None, str | None, dict)`.
- Produces:
  - `judges.conforms(data, schema) -> bool`: walks `object` (`required` keys, `properties`), `array` (`items`), `string` (with `enum`), `boolean` and `number`.
  - `_verdict(text, schema)` and `parse_output(stdout, schema)`, both using `conforms` in place of their hardwired checks.
  - `quality_judge.DIMENSIONS: dict[str, str]`, with keys `reuse`, `simplicity`, `contract` and the English questions taken from §8.2.1.
  - `quality_judge.SCHEMA`: `{"runs": [{"label": str, "vote": enum["pass","fail","unknown"], "note": str}]}`.
  - `quality_judge.VOTES = 3`.
  - `quality_judge.tally(votes: list[str | None]) -> float | None`: returns `1.0` if `pass` gets at least 2 votes, `0.0` if `fail` does, and `None` otherwise.
  - `quality_judge.grade(patches: dict[int, str], originals: str, cfg: dict, run_dir: Path, rng: random.Random) -> tuple[dict[int, dict[str, float | None]], list[str], dict]`: returns (per slot, `judge_<dim>` → value; errors; summed usage).

- [ ] **Step 1: Write the failing tests:**
  - `test_tally`:
    - `["pass","pass","unknown"]` gives `1.0`;
    - `["fail","fail","pass"]` gives `0.0`;
    - `["pass","unknown","unknown"]`, `["pass","fail","unknown"]` and `[None,None,None]` give `None`.
  - `test_grade_one_call_per_vote_and_dimension`: against `FakeAPI` with an all-`pass` reply, 2 patches give `1.0` for each slot and each dimension. There are exactly 9 requests, and each prompt contains exactly one dimension's question.
  - `test_labels_are_blind_and_reshuffled`: the prompts contain no slot numbers or arm letters. Labels are `Q1…Qn`, and at least one of the 9 prompts orders the patches differently (seeded `rng`).
  - `test_bad_vote_is_discarded_and_reported`:
    - one vote's reply omits a label;
    - for the run whose label is missing, that vote counts as `None`, so `pass, pass, None` still gives `1.0`;
    - the errors list has one entry naming the dimension and the vote.
  - `test_failed_call_is_an_error_not_a_crash`: an HTTP 500 on every call gives values of `None` and 9 errors.
  - `test_conforms` (in `test_judges.py`):
    - the compliance `SCHEMA` accepts a good verdict;
    - it rejects `{"runs": [{"label": "R1", "criteria": "x"}]}`.
  - Every existing `test_judges.py` and `test_run.py` judge test keeps passing unchanged.
- [ ] **Step 2: Run** `python3 -m unittest discover -s evals/tests -v`. Expected: the new tests FAIL. The old ones still pass.
- [ ] **Step 3: Implement.**
  - The prompt header is in English: grade each anonymous patch on this one question only, with `pass`, `fail`, or `unknown` when the material is not enough, plus a one-sentence note. After the header come the original files the patches touched, then each patch.
  - Each vote writes `quality-judge/<dim>-<n>/prompt.md` and `verdict.json` under `run_dir`.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(evals): quality judge per dimension with 3 votes`.

### Task 4: Wire quality into `run.py` (`run_eval`, `rejudge`, `_score`, `verdict`) and the gate

**Files:**
- Modify: `evals/run.py`, `checks/_util.py`
- Modify: `evals/vex-mode/cases/tax-rounding/case.json` (add `"quality": true`)
- Test: `evals/tests/test_run.py`

**Interfaces:**
- Consumes: `quality.measure`, `quality.DETERMINISTIC`, `quality_judge.grade`, `quality_judge.DIMENSIONS`.
- Produces:
  - In `checks/_util.py`:
    - `QUALITY_BLOCKING: tuple[str, ...]` (the 9 blocking names);
    - `QUALITY_ALL: tuple[str, ...]` (all 11);
    - `promote_blockers(result: dict) -> list[str]`, which gives one line per reason, such as `"outcome worse"` or `"verbosity error"`.
  - In the result JSON:
    - `arms.<X>.runs[i].quality: {name: value}`, present only for valid passing runs of a quality case;
    - `metrics.<X>.<name>`: a `stats.summarize` dict, or `None` when there are no values;
    - `signals.<pair>.<name>`: one of the values in Global Constraints;
    - `quality: {"enabled": bool, "errors": [str], "judge_usage": dict}`.

- [ ] **Step 1: Write the failing tests** in `RunTest`. The fake case gains `"quality": true`, and the fake check stays the one that accepts `fixed`:
  - `test_quality_only_on_passing_runs`:
    - set `FAKE_AGY_MODE` so that arm B's runs fail the check (add a `fakeagy` mode `failB` that writes `broken` for arm B);
    - B's runs have no `quality` key;
    - `signals.B_vs_A.prod_lines == "few"`, and the result still writes.
  - `test_quality_measures_recorded`: in mode `ok`, every passing run has all 11 quality names, and `metrics.A.prod_lines.mean` is a number.
  - `test_quality_judge_error_blocks_promote`:
    - a FakeAPI that fails the quality calls but answers compliance;
    - `result["quality"]["errors"]` is non-empty, `result["judge"]["error"]` is `None`, and the judge signals are `"error"`;
    - `run.set_verdict(path, "promote", "x")` raises `EvalError` mentioning `judge_reuse error`.
  - `test_promote_refused_when_outcome_worse`: a result with `signals.B_vs_A.outcome = "worse"` makes `set_verdict(..., "promote", ...)` raise `EvalError`, while `reject` passes.
  - `test_case_without_quality_has_none`: with `"quality"` absent, no run has `quality` and `result["quality"]["enabled"] is False`.
  - `test_saved_diff_is_never_truncated`: a fake run that writes a 30 000-char file gets its full diff saved under `diffs/`, while the judge material is still cut at `DIFF_LIMIT`.
  - `test_rejudge_recomputes_quality`: after `rejudge`, every passing run has `quality`. The values match the first run's, and the judge values come from the fake API again.
- [ ] **Step 2: Run** `python3 -m unittest discover -s evals/tests -v`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement.**
  - **`_diff`:** returns the full text. `_material` truncates to `DIFF_LIMIT`.
  - **After `_outcome`:** when `cfg.get("quality")` is set and the run is valid and passing, compute `quality.measure(case_dir/"project", diff, case_dir/"check.py")`. Store values on the run and collect errors as `"slot <n> <measure>: <why>"`.
  - **After the compliance judge:** `quality_judge.grade` runs over the passing runs' diffs. `originals` = the touched files from `project/`, each one fenced. Merge its values into each run's `quality`.
  - **`_score`:** gains the quality names.
    - `error` when any passing run in either arm of the pair has an error for that name. The error is carried as a set of `(slot, name)` that `_score` receives.
    - Otherwise `few` when either arm has fewer than 2 values.
    - Otherwise `stats.signal`, with values negated for lower-is-better names.
  - **`set_verdict`:** if `verdict == "promote"` and `promote_blockers(result)` is non-empty, raise `EvalError("promote refused: " + "; ".join(...))`.
  - **`rejudge`:** recomputes quality for runs with `outcome == 1` from `diffs/<slot>.diff`.
- [ ] **Step 4: Run** the full evals suite. Expected: PASS, including all old tests.
- [ ] **Step 5: Commit** `feat(evals): quality measure in run, rejudge and the promote gate`.

### Task 5: CI (`check_evals`) enforces the gate and the presence of quality; rules table

**Files:**
- Modify: `checks/check_evals.py`, `AGENTS.md` (map line for `quality.py` and `quality_judge.py`, plus 2 rule rows)
- Test: `checks/tests/test_check_evals.py`

**Interfaces:** consumes `promote_blockers`, `QUALITY_ALL`.

- [ ] **Step 1: Write the failing tests:**
  - `test_promote_with_worse_quality_fails`: a valid eval result with `verdict: promote` and `signals.B_vs_A.verbosity = "worse"` gives an error mentioning `promote refused`.
  - `test_quality_case_result_needs_quality_from_2026_11_20`:
    - a result dated `2026-11-20` for a case with `"quality": true` but no `quality` key gives an error;
    - the same result dated `2026-11-19` gives none.
  - `test_quality_metric_may_be_null`: `metrics.A.prod_lines = None` in a quality result is accepted.
  - `test_case_quality_must_be_bool`: `"quality": "yes"` in `case.json` gives an error.
- [ ] **Step 2: Run** `python3 -m unittest discover -s checks/tests -v`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement.**
  - `_result_errors` reads the case's `case.json` (the result's `skill` and `case`) to decide whether quality is required.
  - The cutoff is `QUALITY_SINCE = "2026-11-20"`.
  - Rows added to the `AGENTS.md` table:
    - `Quality is measured only on runs that pass; promote is refused when outcome or a blocking quality measure is worse or errored` | `evals/run.py` `checks/check_evals.py` `evals/tests/test_run.py` `checks/tests/test_check_evals.py`
    - `Every blocking deterministic quality measure scores a planted worse patch worse than the good fix` | `evals/harness/quality.py` `evals/tests/test_quality.py`
- [ ] **Step 4: Run** the full verification from `AGENTS.md` (4 unittest suites, `checks/run.py`, `scripts/validate_plugin.py`). Expected: all pass.
- [ ] **Step 5: Commit** `feat(checks): CI applies the promote gate and requires quality`.

### Task 6: Evidence on real data and the decision log

**Files:**
- Create: `docs/decisions/2026-11-19-m5-quality.md` (in Spanish: the ledger of rulings, in the form "Ruling: … — por qué — costo si me equivoco", and the evidence)
- Modify: `docs/specs/2026-11-18-vex-mode-design.md` (status line: M5 implemented, with its PR), then re-render

- [ ] **Step 1:** Run `quality.measure` read-only on each slot of run `20261119-145054-789891`. Use a scratch script under the session scratchpad, not in the repo. Record the table in the decision log: slot, arm, outcome, then each measure for passing slots. Expected: the 4 passing slots have `removable_lines == 0` and `security_findings == 0`, and their `test_lines` range is 38–113.
- [ ] **Step 2:** Run one live `quality_judge.grade` on those 4 passing patches with the configured judge: 9 calls to `gpt-6.2-sol`, nothing from Claude. Write the output to the scratchpad and record the votes in the log. Do not write any result file.
- [ ] **Step 3:** Run the full verification again. Then commit `docs: M5 evidence and rulings`.
- [ ] **Step 4:** Do an independent review of the whole branch (fresh reviewer), then one pass of fixes. Open a ready-for-review PR. The user merges.
