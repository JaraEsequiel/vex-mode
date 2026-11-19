# vex-mode upstream drift — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Know, every week and without asking, which files copied from pstack changed upstream. When one did, show the change so it can be re-applied onto our copy or adaptation.

**Architecture:**
- `vendor.lock` records a commit per file.
- `scripts/upstream_drift.py` compares each entry with an upstream checkout and prints a Markdown report. With `--accept`, it records a reconciled file's new upstream hash and commit. With `--gh-issue`, it opens, updates or closes one GitHub issue.
- A weekly workflow runs it.

**Tech Stack:** Python 3 stdlib, `git`, `gh` (in the workflow, with `GITHUB_TOKEN`).

**Spec:** `docs/specs/2026-11-18-vex-mode-design.md` §6.6 ("Cómo se hace cumplir", corrected 2026-11-19).

## Sources read (2026-11-19)

| Source | What it settles |
|---|---|
| `scripts/vendor.py` | Copies bytes and writes `path`, `upstream_path`, `upstream_sha256`, `pending_refs`. It drops `adapted`/`removed_refs` on re-vendor, so the plan keeps them. No per-file commit. |
| `vendor.lock` | One global `upstream.commit` (`35a9094`), 26 files, 13 adapted. |
| `checks/check_vendor.py` | Validates paths, hashes and the unadapted-equals-upstream rule; it must accept `upstream_commit`. |
| `.github/workflows/ci.yml` | CI runs on push/PR with Python 3.12; drift must not join it. |
| Upstream `git diff 35a9094 e58dd04 -- pstack/skills/poteto-mode/SKILL.md` | The only drifted file today. Its changed lines (model slugs carbon → neon in the routing section) are absent from our router, so reconciling is `--accept` with no content change. |

## Global Constraints

- Upstream repo comes from `vendor.lock` `upstream.repo`. The cache checkout is `~/.cache/vex-mode/upstream` (`VEX_UPSTREAM` overrides the path).
- An entry's commit is `upstream_commit`, falling back to `upstream.commit`.
- Exit 0 unless `--fail` is given and drift exists.
- The issue title is exactly `pstack upstream drift`, with label `upstream-drift`; at most one is open.

## Review Focus

1. **An adapted file is re-vendored blindly and loses our adaptation.** For adapted files, the report must say "re-apply the upstream diff", never "re-vendor". Covered: `test_adapted_change_shows_diff_not_revendor` (Task 2).
2. **`--accept` on a file whose content no longer matches.** An unadapted file must equal the new upstream bytes, or `--accept` refuses. Covered: `test_accept_refuses_unadapted_mismatch` (Task 2).
3. **The issue duplicates every week.** The open issue must be updated, never a second one created; no drift closes it. Covered: `test_issue_updated_not_duplicated`, `test_issue_closed_when_clean` (Task 3).
4. **A deleted upstream file** is reported as deleted, not as a crash. Covered: `test_deleted_upstream_file` (Task 2).

---

### Task 1: Per-file upstream commit
- [ ] **Step 1: Failing tests.**
  - `scripts/tests/test_vendor.py::test_records_upstream_commit_and_keeps_adaptation_fields`: vendoring from a git checkout writes `upstream_commit` (its HEAD) and keeps an existing entry's `adapted`/`removed_refs`.
  - `checks/tests/test_check_vendor.py::test_upstream_commit_must_be_a_sha`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** Backfill every `vendor.lock` entry with `upstream_commit: 35a9094…` (full SHA).
- [ ] **Step 4:** full verify; commit `feat(vendor): record the upstream commit of each file`.

### Task 2: `scripts/upstream_drift.py`
**Produces:**
- `report(repo: Path, upstream: Path) -> list[dict]`, one dict per entry: `{path, upstream_path, status: same|changed|deleted, adapted, from_commit, diff}`.
- `render(entries, head) -> str` (Markdown).
- `accept(repo, upstream, path) -> None`.
- CLI: `[--upstream PATH | --fetch] [--fail] [--accept PATH] [--gh-issue]`.

- [ ] **Step 1: Failing tests** with a temp upstream git repo (commit A, vendor from it, commit B that edits one file and deletes another):
  - `test_same_changed_deleted`;
  - `test_adapted_change_shows_diff_not_revendor`;
  - `test_unadapted_change_says_revendor`;
  - `test_deleted_upstream_file`;
  - `test_accept_updates_hash_and_commit`;
  - `test_accept_refuses_unadapted_mismatch`;
  - `test_fail_exit_code`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.**
  - `--fetch` clones or fetches the upstream into the cache.
  - The diff is `git -C upstream diff <from_commit> HEAD -- <upstream_path>`.
- [ ] **Step 4:** PASS; commit `feat(scripts): report pstack upstream drift`.

### Task 3: Weekly issue
- [ ] **Step 1: Failing tests** with a fake `gh` via `VEX_GH` that records calls and answers `issue list`:
  - `test_issue_created_when_drift`;
  - `test_issue_updated_not_duplicated`;
  - `test_issue_closed_when_clean`;
  - `test_no_issue_and_no_drift_does_nothing`.
- [ ] **Step 2: Implement `--gh-issue`.**
  - It lists open issues with the label.
  - Then it edits the first issue's body, or creates one (ensuring the label exists), or closes it with a comment.
- [ ] **Step 3: Add `.github/workflows/upstream-drift.yml`.**
  - Triggers: `schedule` (Mondays 12:00 UTC) and `workflow_dispatch`.
  - `permissions: {contents: read, issues: write}`.
  - It runs `python3 scripts/upstream_drift.py --fetch --gh-issue` with `GH_TOKEN: ${{ github.token }}`.
- [ ] **Step 4:** AGENTS.md Map and Rules row ("Files copied from pstack are compared with upstream every week" | `scripts/upstream_drift.py` `.github/workflows/upstream-drift.yml`); a README paragraph in Spanish; commit.

### Task 4: First real run
- [ ] **Step 1:** `python3 scripts/upstream_drift.py --fetch`. Expected: one changed file, `skills/vex-mode/SKILL.md` (adapted), with the carbon → neon diff.
- [ ] **Step 2:** Confirm the diff's lines are absent from our router (`grep`), then run `--accept skills/vex-mode/SKILL.md`. Re-run: no drift. Record it in `docs/decisions/2026-11-19-upstream-drift.md`.
- [ ] **Step 3:** full verify, push the branch, and open a PR stacked on `m4`, ready for review.
