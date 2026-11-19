# vex-mode M3 (Self-improvement) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the self-improvement loop of design §9. `correct`, `reflect` and `show-me-your-work` come from pstack. A weekly unattended `correct` run opens PRs that carry their own eval evidence and can never merge themselves.

**Architecture:**
- The three skills are vendored verbatim from pstack, then adapted in a separate commit: agy paths, the cross-family reviewer through `agy -p`, and `reflect` routing vex-mode edits to a PR.
- The router gets back pstack's `show-me-your-work` trigger, which M1 removed.
- `hooks/irreversible.py` learns that `gh pr merge` and a push to `main` are irreversible. In `agy -p`, `force_ask` never runs the command, so an unattended agent cannot merge.
- `scripts/scheduled_correct.py` is a thin wrapper: a lock, a worktree off `origin/main`, one `agy -p` run, a saved transcript and a desktop notification. It also renders and installs a systemd user timer. The agent does the work itself, following the repo's `AGENTS.md`.

**Tech Stack:**
- Python 3 standard library only, tested with `unittest`. agy is faked through `VEX_AGY`, as in M2.
- agy 1.5.12; systemd user units; `gh`.

**Spec:** `docs/specs/2026-11-18-vex-mode-design.md` §9, §10b, §11, §13 (corrected 2026-11-19 after the source review).

## Sources read for this plan (2026-11-19)

| Source | What it settles here |
|---|---|
| `pstack/skills/correct/SKILL.md` @ `e58dd04` (identical to `35a9094`) | Vendored verbatim. Nothing Cursor-specific, so no adapt commit. |
| `pstack/skills/reflect/SKILL.md` lines 11, 13, 15, 17 | Whole transcript is data; six-month rule; Accepted/Rejected/Backlog then wait for approval; the destination paths that need adapting. |
| `pstack/skills/show-me-your-work/SKILL.md` lines 38, 46-48, 57, 67, 74 + `scripts/log.sh` + `references/decision-log-template.tsv` | Log format and helper; committed only when a reviewer needs it; transcript audit path; cross-vendor reviewer; "Attention" section. |
| `pstack/skills/poteto-mode/SKILL.md` line 29 | "Long or unattended work → **show-me-your-work**." restored verbatim in the router. |
| `pstack/skills/poteto-mode/worker.md`, our `opening-a-pr.md` | PR rules the scheduled run follows (ready, not draft; title and body format). |
| `pstack/skills/automate-me/SKILL.md` line 87 | Don't overfit to one conversation, which matches `correct`'s "a class counts once it has happened twice". |
| Upstream issues #875, #876, #1154, #1159, #1272 | #875 is moot in agy (the transcript is complete). #876 is not adopted (an unmerged proposal). #1154 is obsolete (reflect no longer fans out). #1159 is solved with `agy -p --model`. #1272: a delegate never asks, so the scheduled run's prompt states the bar itself. |
| T-maily, T-talk (re-read 2026-11-19) | Automerge comes only after verification and a trust ladder ("there's really no shortcut"), so the merge guard is required. Neither source describes decision logs. |
| agy 1.5.12 probe (`A-transcript`) | The prompt names `brain/<id>/.system_generated/logs/transcript.jsonl`; global skills live in `~/.gemini/config/skills/`. |
| `docs/decisions/2026-11-18-hook-probe.md` line 25 | `force_ask` is not executed headless, so it is a real block in `agy -p`. |
| `scripts/vendor.py` line 16 | `shutil.copyfile` drops the exec bit, so `log.sh` needs `chmod +x` in the adapt commit. |

## Global Constraints

- Vendor pin stays `35a90942a7f02e1ebbc2443643179815f2147954`. The three skills are byte-identical at upstream `e58dd04`, and `vendor.lock` holds one upstream commit.
- Vendoring follows `AGENTS.md` "How to bring in something that already exists": a `vendor:` commit, then a separate `adapt:` commit with `adapted`, `removed_refs` and `pending_refs` set.
- Text the agent reads is in English; human docs are in Spanish.
- Python stdlib only; no network or model calls in unit tests.
- Scheduled run defaults: `OnCalendar=Sun *-*-* 03:00:00`, `Persistent=true`; window 7 days; model `VEX_CORRECT_MODEL`, default `gemini-4-neon-high`; `--print-timeout 14400s`; state under `~/.cache/vex-mode/correct/`.
- No AI PR merges itself (§9.5). The enforcer is `hooks/irreversible.py`.

## Review Focus

1. **The unattended agent tries to merge** with `gh pr merge`, `gh api …/merge`, `git push origin main` or `git push origin HEAD:main`. Each must be classified irreversible, while a push of `correct/<date>` must stay allowed. Covered: `test_merge_and_push_to_main_are_irreversible`, `test_push_of_feature_branch_is_ordinary` (Task 3).
2. **Two scheduled runs overlap** (a manual start while the timer fires). The second must exit non-zero without touching the worktree. Covered: `test_second_run_is_refused` (Task 4).
3. **The agent run fails or times out.** The worktree and transcript must be kept for inspection, the exit must be non-zero so systemd marks the unit failed, and the notification must say it failed. Covered: `test_agy_failure_keeps_worktree_and_fails` (Task 4).
4. **A run finds nothing (no commits).** The worktree and its branch are removed, so they don't pile up week after week. Covered: `test_no_commits_cleans_up` (Task 4).
5. **`log.sh` loses its exec bit** in the install, so the skill's helper fails on first use. Covered: Task 1 step 5 checks the installed copy with `test -x`.

---

### Task 1: show-me-your-work + the router trigger

**Files:**
- Create (vendor): `skills/show-me-your-work/SKILL.md`, `skills/show-me-your-work/scripts/log.sh`, `skills/show-me-your-work/references/decision-log-template.tsv`
- Modify: `vendor.lock`, `skills/vex-mode/SKILL.md`

- [ ] **Step 1: Vendor** the three files with `scripts/vendor.py` from the pstack clone checked out at `35a9094`, and vendor `skills/vex-mode/SKILL.md`'s source line as is. Run `python3 checks/run.py`. Expected: green, or failures only for dangling refs (`unslop`, `poteto-mode`). Commit `vendor: copy show-me-your-work from pstack@35a9094` (commit even if red: the adapt commit fixes it; record the red state in the ledger).
- [ ] **Step 2: Adapt `SKILL.md`**, changing only these:
  - line 36: drop "(the **unslop** skill applies to log text too)". `removed_refs: ["unslop"]`.
  - line 57: the transcript is `.system_generated/logs/transcript.jsonl` in this conversation's artifact directory (the system prompt names it). Never glob `~/.gemini/antigravity-cli/brain/*/`.
  - line 67: "spawn a subagent on another vendor's model" becomes running `agy -p --model <a model of another family from agy models>` from the shell with the trail and transcript paths. **poteto-mode** becomes **vex-mode**.
  - `chmod +x scripts/log.sh`. `vendor.lock`: `"adapted": true` on `SKILL.md` only.
- [ ] **Step 3: Router.** Add `- Long or unattended work → **show-me-your-work**.` as the last Non-negotiables bullet, verbatim from poteto-mode line 29. Remove `show-me-your-work` from the router's `removed_refs`.
- [ ] **Step 4: Verify.** Run the full verify command from `AGENTS.md`. Expected: green. Run `bash skills/show-me-your-work/scripts/log.sh <scratch>/d.tsv start "x" "y" "=z" open` twice. Expected: one header, two rows, and the `=z` cell written as `'=z`.
- [ ] **Step 5: Install check.** `python3 scripts/build_plugin.py --install <scratch>/build`, then `test -x ~/.gemini/config/plugins/vex-mode/skills/show-me-your-work/scripts/log.sh`. Expected: exit 0. If agy drops the bit, rule: the SKILL text calls `bash scripts/log.sh`, and ledger it.
- [ ] **Step 6: Commit** `adapt: show-me-your-work for antigravity`.

### Task 2: correct (verbatim) + reflect (adapted)

**Files:**
- Create (vendor): `skills/correct/SKILL.md`, `skills/reflect/SKILL.md`
- Modify: `vendor.lock`, `plugin.json` (only if Step 3 needs it)

- [ ] **Step 1: Vendor** both files. Commit `vendor: copy correct and reflect from pstack@35a9094`. `correct` stays unadapted (byte-identical).
- [ ] **Step 2: Adapt `reflect` line 17** to the design's §9.2 destinations:
  - Never edit a skill under `~/.gemini/config/plugins/`.
  - For a vex-mode skill, the destination is a branch in a worktree of the vex-mode repo (Step 3). After approval, edit it there, follow the repo's `AGENTS.md` "How to change a skill", and open a PR with the `opening-a-pr` playbook.
  - For any other skill, the destination is `.agents/skills/<skill>/` or `~/.gemini/config/skills/<skill>/`. Copy the folder there and edit the copy. Never open a PR or push.
  - Line 11 also names the transcript path, worded as in Task 1 step 2.
- [ ] **Step 3: Repo pointer.** The installed copy has no `.git`, so `reflect` needs the repo's location. Add `"repository": "https://github.com/JaraEsequiel/vex-mode"` to `plugin.json` and run `python3 scripts/validate_plugin.py`. Expected: green. If strict validation rejects the field, rule: put the URL in `reflect`'s text instead, and ledger it.
- [ ] **Step 4: Verify** with the full verify command. Expected: green. Commit `adapt: reflect for antigravity`.

### Task 3: Merge guard in the pause hook

**Files:**
- Modify: `hooks/irreversible.py`, `hooks/tests/test_irreversible.py`, `AGENTS.md` (Rules)

**Interfaces:**
- Produces: `classify(command) -> str | None` returns a reason for `gh pr merge …`, `gh api … /merge` (any method), and `git push` whose refspec destination is `main` or `master` (`main`, `HEAD:main`, `refs/heads/main`, `x:main`).

- [ ] **Step 1: Write the failing tests:**
  - `test_merge_and_push_to_main_are_irreversible`: `gh pr merge 3 --squash`, `gh api -X PUT repos/o/r/pulls/3/merge`, `git push origin main`, `git push origin HEAD:main`, `git push origin refs/heads/master`, `cd x && git push origin main` each yield a non-None reason.
  - `test_push_of_feature_branch_is_ordinary`: `git push -u origin correct/2026-11-22`, `git push origin HEAD`, `gh pr create --fill`, `gh pr view 3` yield None.
- [ ] **Step 2: Run** `python3 -m unittest discover -s hooks/tests -p 'test_irreversible.py' -v`. Expected: the first test FAILs and the second passes.
- [ ] **Step 3: Implement** in `_segment`/`_git_push`; add a `gh` branch.
- [ ] **Step 4: Run** the hook tests, then the full verify command. Expected: green.
- [ ] **Step 5: Rules row:** "No AI PR merges itself: merging and pushing to main pause (headless: blocked)" | `hooks/irreversible.py` `hooks/tests/test_irreversible.py`. Commit `feat(hooks): treat merging and pushing to main as irreversible`.

### Task 4: `scripts/scheduled_correct.py` + systemd timer

**Files:**
- Create: `scripts/scheduled_correct.py`, `scripts/tests/test_scheduled_correct.py`
- Modify: `AGENTS.md` (Map, Rules), `README.md` (Spanish section "Auto-mejora programada")

**Interfaces:**
- Produces: `run(repo: Path, *, state: Path, model: str, days: int = 7, timeout_s: int = 14400, open_pr: bool = True, base: str = "origin/main") -> int`. It:
  1. Takes `state/run.lock` with `flock`; if held, return 2.
  2. `git fetch origin`; `git worktree add -b correct/<YYYY-MM-DD> <state>/wt-<date> <base>`. "Commits ahead" below are counted against `<base>`.
  3. Runs `[*agy_command(), "--model", model, "--print-timeout", f"{timeout_s}s", "--output-format", "stream-json", "-p", prompt]` with cwd set to the worktree. Stdout goes to `state/<date>.ndjson`.
  4. On a non-zero agy exit or a missing `result` event, keeps the worktree, notifies "failed" and returns 1.
  5. If the branch has no commits ahead of `origin/main`, runs `git worktree remove` and `git branch -D`, then returns 0. Otherwise keeps both and returns 0.
  6. `notify-send "vex-mode correct" <summary>` when `notify-send` exists. A missing `notify-send` is not an error.
- Produces: `build_prompt(since: str, open_pr: bool) -> str`. It starts with `/correct`, then names: the window (`git log --since=<since>`, and PRs and review comments via `gh` updated since then), reading `AGENTS.md` first, and keeping a committed trail at `docs/decisions/<date>-correct.tsv` with the **show-me-your-work** skill. For a change to a skill, hook, rule or manifest, it follows `AGENTS.md` "How to change a skill", including the eval run and verdict. With `open_pr`, it pushes `correct/<date>` and opens a PR per `skills/vex-mode/playbooks/opening-a-pr.md`; without it, it commits only. It never merges. It never asks a question: no class found twice means a final report and no commits (#1272).
- Produces: `render_units(script: Path, repo: Path) -> dict[str, str]`, which returns `vex-correct.service` (`Type=oneshot`, `ExecStart=/usr/bin/python3 <script> run --repo <repo>`) and `vex-correct.timer` (the Global Constraints calendar, `Persistent=true`).
- Produces: CLI `run [--repo] [--no-pr] [--base REF]`, `install` (writes the units to `~/.config/systemd/user/`, then `systemctl --user daemon-reload` and `enable --now vex-correct.timer`), and `uninstall`.

- [ ] **Step 1: Write the failing tests**, using a temp bare origin + clone and `evals/tests/fake_agy.py` via `VEX_AGY` (add a `commit` mode that commits a file in cwd, if the existing one doesn't fit):
  - `test_prompt_shape`: starts with `/correct`; contains the since date, `AGENTS.md`, `show-me-your-work`, `How to change a skill`, `never merge`. `open_pr=False` drops `gh pr create` and says commit only.
  - `test_no_commits_cleans_up`: fake agy ok → returns 0; no `wt-*` dir, no `correct/*` branch; transcript saved.
  - `test_commits_keep_worktree`: fake agy commits → returns 0; worktree and branch exist.
  - `test_agy_failure_keeps_worktree_and_fails`: fake agy crash → returns 1; worktree kept.
  - `test_base_ref_is_used`: with `base="origin/other"`, the worktree's HEAD starts at that ref.
  - `test_second_run_is_refused`: hold the lock in the test → returns 2; no worktree created.
  - `test_units`: the service `ExecStart` has absolute paths; the timer has `OnCalendar=Sun *-*-* 03:00:00` and `Persistent=true`.
- [ ] **Step 2: Run** `python3 -m unittest discover -s scripts/tests -p 'test_scheduled_correct.py' -v`. Expected: FAIL, module missing.
- [ ] **Step 3: Implement.** Reuse `build_plugin.agy_command()`.
- [ ] **Step 4: Run** the tests, then the full verify command. Expected: green.
- [ ] **Step 5: Docs.** AGENTS.md Map line for the script. Rules row: "Scheduled runs never overlap and never leave an empty worktree" | `scripts/scheduled_correct.py` `scripts/tests/test_scheduled_correct.py`. README in Spanish: what runs, when, how to install or uninstall, where transcripts are, and the plugin-swap cost from §9.5. Commit `feat(scripts): weekly unattended correct run`.

### Task 5: Real dry run, then install the timer

The installed plugin is still M2's, which has no `/correct`. This task proves the whole flow on this branch before merge, without pushing or opening a PR.

- [ ] **Step 1:** `git push -u origin m3`, then `python3 scripts/build_plugin.py --ref HEAD --install <scratch>/build`.
- [ ] **Step 2:** run `run(repo, state=<scratch>/correct-state, model="gemini-4-neon-high", open_pr=False)` against a worktree based on `origin/m3`. It runs with `--no-pr --base origin/m3`. Run it in the background. Expected: exit 0; a transcript; and either commits with `docs/decisions/<date>-correct.tsv` plus an eval result for any changed skill, or a report that no class happened twice.
- [ ] **Step 3: Read** the transcript and the trail, per show-me-your-work's audit. Check that every class cites two real occurrences, that no `gh pr merge` or `push … main` was attempted, and that the hook blocked any attempt. Write `docs/decisions/2026-11-19-m3-dry-run.md` (Spanish) with the numbers and findings. Do not keep the dry run's commits; its findings go to the user.
- [ ] **Step 4:** reinstall the user's plugin from `main` (`build_plugin.py --ref origin/main --install`), then `python3 scripts/scheduled_correct.py install`. Expected: `systemctl --user list-timers vex-correct.timer` shows the next Sunday 03:00. The first real run happens after merge, from `origin/main`.
- [ ] **Step 5: Commit** the decision doc: `docs(decisions): M3 dry run of the scheduled correct`.

### Task 6: Evidence for the PR

- [ ] **Step 1: Waivers** (`kind: waiver`) for `correct`, `reflect` and `show-me-your-work` at their current tree hashes. Reason: manual-only (`disable-model-invocation`) skills vendored from pstack with path adaptations only; `reflect` waits for approval and cannot run headless; the dry run in `docs/decisions/2026-11-19-m3-dry-run.md` exercised `correct` and `show-me-your-work` end to end.
- [ ] **Step 2: vex-mode eval.** The router trigger (Task 1) and the hook (Task 3) change `vex-mode`. Run `python3 evals/run.py vex-mode tax-rounding` with base `origin/main`, in the background (~70 min). Read every output and transcript per `eval.md`, then record the verdict. Expected: B vs A noise or better on all three measures; otherwise report and do not promote.
- [ ] **Step 3: Verify:** full verify command + `VEX_BASE_REF=origin/main python3 checks/check_evals.py`. Expected: green. Commit `evals: M3 evidence`, push, and open the PR per `opening-a-pr.md` (ready, not draft). The user merges it.
