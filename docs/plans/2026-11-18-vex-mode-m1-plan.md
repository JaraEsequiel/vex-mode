# vex-mode M1 (Base) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the private `vex-mode` repo as a valid Antigravity plugin that contains the router (`/vex-mode`), 3 playbooks, `worker.md`, `vex-agent`, the vendored principles and the mode hooks. Every vendored file comes verbatim from pstack, and the repo's structural checks run in CI.

**Architecture:**
- The repo root is the plugin, with `plugin.json`, `skills/`, `agents/`, `rules/` and `hooks.json`.
- Content from pstack enters in two steps. First a byte-identical `vendor:` commit, recorded in `vendor.lock`. Then a separate `adapt:` commit with only the Antigravity-required edits.
- Rules are enforced in two places:
  - Python stdlib scripts in `checks/`, which run locally and in CI.
  - Python hook scripts in `hooks/`, run by agy with JSON on stdin and stdout.

**Tech Stack:**
- Python 3 standard library only, tested with `unittest`.
- agy 1.5.11 (`agy plugin validate --strict`).
- GitHub Actions and `gh`.

**Spec:** `docs/specs/2026-11-18-vex-mode-design.md` (source: `~/Projects/VexOs/PRDs/2026-11-18-vex-mode-design.md`)

## Global Constraints

- Repo path: `~/Projects/VexOs/Code/Repos/vex-mode`. GitHub: `JaraEsequiel/vex-mode`, **private**.
- Upstream: `https://github.com/cursor/plugins`, commit `35a90942a7f02e1ebbc2443643179815f2147954`, subtree `pstack/`.
- **Reuse, never rewrite.**
  - Any file that exists in pstack is copied byte-identical in a `vendor:` commit.
  - Edits go only in a following `adapt:` commit, and they are limited to:
    - paths
    - model slugs and model-routing sections
    - tool names (`Task` → agy subagent tool)
    - names (`poteto-mode` → `vex-mode`, `poteto-agent` → `vex-agent`)
    - removing references to skills not vendored yet
    - removing the "cite principles" rule (spec §6.5)
    - adding the explicit reading list (spec §6.3)
- Keep the MIT notice "Copyright (c) 2026 Lauren Tan" in `LICENSES/pstack-MIT.txt`.
- Agent-facing text is in English. Human docs (`README.md`) are in Spanish.
- No third-party Python packages. Target `python3` ≥ 3.11 (local is 3.14).
- Limits:
  - `rules/*.md` ≤ 24 KB, which is agy's hard cap per rule file.
  - Every `SKILL.md` ≤ 16 KB.
- agy facts this plan relies on (from agy 1.5.11's embedded docs):
  - The hook payload is camelCase JSON on stdin and the result is JSON on stdout.
  - Hook commands run with cwd = the plugin folder, with the env vars `PLUGIN_ROOT` and `PLUGIN_DATA`.
  - `PreToolUse` decisions are `allow|deny|ask|force_ask`.
  - `Stop` output `{"decision":"continue","reason":...}` blocks the stop. The input has `continuationActive` and `terminationReason`.
  - `PreInvocation` input has `lastUserInput` and `conversationId`, and its output can carry `injectSteps:[{"systemMessage":{"systemMessage":"..."}}]`.
  - `SessionStart` fires once **before** the first user message.
  - Shell tool name: `run_command`.
  - Agent frontmatter: `name`, `description`, `subagent: true`, `mainAgent: false`, `tools: [...]`. `model` must be a valid tier or the agent is skipped.
  - Rule files start with `---\ntrigger: always_on\n---`.
- Merge policy: everything after Task 1 lands through PR branch `m1`. Vex merges.

## Design adjustment found while planning (needs Vex's OK before Task 8)

Spec §7.1 injects the reading list in `SessionStart`. But `SessionStart` fires before the user types `/vex-mode`, so the activation mark cannot exist yet. M1 therefore uses `PreInvocation` instead:
- When `lastUserInput` starts with `/vex-mode`, the hook writes the mark for that `conversationId`.
- Then it injects the reading list once.

This also removes the need for a separate mark-writing step.

## Review Focus

1. **The `PreToolUse` hook must not auto-approve everything.** On a non-matching command the hook must not answer `"allow"`, because that bypasses agy's normal permission prompts. Task 7 finds the neutral output and Task 8 pins it with a test.
2. **The `Stop` hook must not loop.** When `continuationActive` is true, or the mark is absent, it must let the agent stop.
3. **Force-push detection must cover all spellings:** `git push -f`, `--force`, `--force-with-lease`, `+refspec` and `--mirror` must all be caught. `git push` alone and `git push --follow-tags` must not.
4. **Hooks must not leak state between conversations.** The mark is keyed by `conversationId`, and a second conversation is unaffected.
5. **Hooks must fail open on malformed stdin.** Empty or invalid JSON produces a neutral output and exit 0, never a crash. A crashing `PostToolUse` marks the tool call as failed, and the same risk is assumed for the other hooks.

---

## File Structure

```
vex-mode/
├── plugin.json                    manifest (name, version, description)
├── README.md                      Spanish, human install/usage
├── AGENTS.md                      maintainer instructions + rule table
├── LICENSES/pstack-MIT.txt        vendored verbatim
├── vendor.lock                    JSON provenance for every file under skills/, rules/, agents/
├── rules/AGENTS.md                always-on core (excerpts vendored from poteto-mode)
├── agents/vex-agent.md            subagent; body = worker.md rules
├── skills/
│   ├── vex-mode/SKILL.md          ← pstack skills/poteto-mode/SKILL.md
│   ├── vex-mode/worker.md         ← pstack skills/poteto-mode/worker.md
│   ├── vex-mode/playbooks/{bug-fix,feature,opening-a-pr}.md
│   └── principle-{prove-it-works,fix-root-causes,laziness-protocol,subtract-before-you-add,
│        sequence-verifiable-units,encode-lessons-in-structure,never-block-on-the-human,
│        model-the-domain,separate-before-serializing-shared-state}/SKILL.md
├── hooks.json
├── hooks/_io.py                   read_payload(), emit()
├── hooks/activate.py              PreInvocation
├── hooks/irreversible.py          PreToolUse (run_command)
├── hooks/stop_gate.py             Stop
├── hooks/tests/test_*.py
├── checks/_util.py                frontmatter parser, file walker
├── checks/check_vendor.py
├── checks/check_skills.py         frontmatter + size + references
├── checks/check_rules.py          AGENTS.md rule table → enforcer exists
├── checks/run.py                  runs all checks, exit 1 on any error
├── checks/tests/test_*.py (+ fixtures/)
├── scripts/vendor.py              copy upstream file verbatim + write lock entry
├── docs/specs/, docs/plans/, docs/decisions/
└── .github/workflows/ci.yml
```

**Deferred from M1:** the upstream-drift script from spec §6.6 goes to M3, together with `correct`, because nothing consumes it before then.

The playbooks `bug-fix` and `feature` both end with "Run **Opening a PR**", so M1 vendors `opening-a-pr` too: 3 playbooks, not 2. The 2 extra principles are named by `feature.md`.

---

### Task 1: Repo bootstrap

**Files:**
- Create: `plugin.json`, `README.md`, `LICENSES/pstack-MIT.txt`, `.gitignore`, `docs/specs/2026-11-18-vex-mode-design.{md,html}`, `docs/plans/2026-11-18-vex-mode-m1-plan.md`

**Interfaces:**
- Produces: `plugin.json` = `{"name":"vex-mode","version":"0.1.0","description":"<one line>"}`. The `name` must equal the folder name `vex-mode`.

- [ ] **Step 1:** `mkdir -p ~/Projects/VexOs/Code/Repos/vex-mode && cd` into it, then `git init -b main`.
- [ ] **Step 2:** Clone upstream to a scratch dir at the pinned commit:
  ```bash
  git clone https://github.com/cursor/plugins /tmp/pstack-up
  git -C /tmp/pstack-up checkout 35a90942a7f02e1ebbc2443643179815f2147954
  ```
- [ ] **Step 3:** `cp /tmp/pstack-up/pstack/LICENSE LICENSES/pstack-MIT.txt`. Copy the spec (md + html) and this plan into `docs/`. Write `plugin.json`, a Spanish `README.md` (what it is, install with `agy plugin install <path>`, credit to pstack), and `.gitignore` (`__pycache__/`, `.state/`).
- [ ] **Step 4:** Run `agy plugin validate . --strict`.
  Expected: `✔ Validation passed`. The only allowed note is "no logo".
- [ ] **Step 5:** Commit `chore: bootstrap vex-mode plugin`, then create the remote:
  ```bash
  gh repo create JaraEsequiel/vex-mode --private --source . --push
  gh repo view JaraEsequiel/vex-mode --json visibility -q .visibility
  ```
  Expected: `PRIVATE`.
- [ ] **Step 6:** `git switch -c m1`. All remaining tasks commit on `m1`.

### Task 2: Check harness + vendor provenance check

**Files:**
- Create: `checks/_util.py`, `checks/check_vendor.py`, `checks/run.py`, `checks/tests/test_check_vendor.py`, `checks/tests/fixtures/vendor_*/`, `vendor.lock`, `scripts/vendor.py`, `scripts/tests/test_vendor.py`

**Interfaces:**
- Produces:
  - Every check exposes `run(root: pathlib.Path) -> list[str]`, which returns human-readable error strings and an empty list when the check passes.
  - `checks/run.py` imports every `checks/check_*.py`, prints the errors and exits 1 if any exist.
  - `vendor.lock` schema:
    ```json
    {"upstream": {"repo": "https://github.com/cursor/plugins", "commit": "35a90942a7f02e1ebbc2443643179815f2147954"},
     "files": [{"path": "skills/vex-mode/worker.md", "upstream_path": "pstack/skills/poteto-mode/worker.md",
                "upstream_sha256": "<hex>", "pending_refs": []}],
     "original": ["rules/AGENTS.md", "agents/vex-agent.md"]}
    ```
  - `scripts/vendor.py`:
    - `vendor(upstream_root: Path, upstream_path: str, dest: Path, repo_root: Path) -> dict` copies the bytes and upserts the lock entry.
    - CLI: `python3 scripts/vendor.py <upstream_root> <upstream_path> <dest>`.

- [ ] **Step 1: Write failing tests** in `checks/tests/test_check_vendor.py`:
  - `test_unlisted_file_is_error`: a fixture with `skills/x/SKILL.md` that is in neither `files` nor `original` → errors contain `"skills/x/SKILL.md"`.
  - `test_listed_file_passes`: the same file listed in `files` → `[]`.
  - `test_original_file_passes`: the file listed in `original` → `[]`.
  - `test_missing_listed_path_is_error`: a lock entry whose `path` does not exist → error.
  - `test_bad_sha_format_is_error`: `upstream_sha256` is not 64 hex characters → error.
  - Scope: `skills/**`, `rules/**`, `agents/**`.
- [ ] **Step 2:** Run `python3 -m unittest discover -s checks/tests -v`.
  Expected: FAIL (`ModuleNotFoundError: check_vendor`).
- [ ] **Step 3:** Implement `check_vendor.run` and `_util.iter_files(root, globs) -> list[Path]`.
- [ ] **Step 4:** Write failing tests in `scripts/tests/test_vendor.py`:
  - `test_copies_bytes_identically`: the destination bytes equal the source bytes.
  - `test_upserts_lock_entry`: calling twice leaves one entry, with `upstream_sha256 == sha256(source)`.
- [ ] **Step 5:** Implement `scripts/vendor.py`. Run both test suites. Expected: PASS.
- [ ] **Step 6:** Create `vendor.lock` with an empty `files` list and an empty `original` list. Run `python3 checks/run.py`. Expected: exit 0.
- [ ] **Step 7:** Commit `feat(checks): vendor provenance check and vendor script`.

### Task 3: Skill structure checks

**Files:**
- Create: `checks/check_skills.py`, `checks/tests/test_check_skills.py` (+ fixtures)

**Interfaces:**
- Consumes: `_util.iter_files`, plus `_util.parse_frontmatter(text: str) -> dict[str, str]` (added here; it handles only flat `key: value` YAML).
- Produces: `check_skills.run(root) -> list[str]`.

- [ ] **Step 1: Failing tests:**
  - `test_name_must_match_folder`: `skills/foo/SKILL.md` with `name: bar` → error mentioning `foo`.
  - `test_description_required`: an empty description → error.
  - `test_skill_size_cap`: a 16 385-byte `SKILL.md` → error. A 16 384-byte file → no error.
  - `test_rule_size_cap`: a 24 577-byte `rules/x.md` → error.
  - `test_missing_playbook_ref`: `playbooks/nope.md` referenced in a SKILL.md, with no file → error.
  - `test_missing_skill_ref`: the text "the **ghost** skill" or `principle-ghost` with no `skills/ghost` or `skills/principle-ghost` → error.
  - `test_pending_ref_is_allowed`: a reference listed in that file's `vendor.lock` `pending_refs` → no error.
  - `test_relative_link_must_resolve`: `[x](../missing/SKILL.md)` → error.
  - Reference regexes, pinned:
    - `\*\*([a-z0-9-]+)\*\* (?:skill|principle)`
    - `\bprinciple-[a-z0-9-]+\b`
    - `playbooks/[a-z0-9-]+\.md`
    - markdown links `\]\((\.\.?/[^)]+)\)`
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. Run. Expected: PASS.
- [ ] **Step 4:** Commit `feat(checks): skill frontmatter, size and reference checks`.

### Task 4: Rule table check + maintainer AGENTS.md

**Files:**
- Create: `checks/check_rules.py`, `checks/tests/test_check_rules.py`, `AGENTS.md`

**Interfaces:**
- Produces:
  - `check_rules.run(root) -> list[str]`.
  - Table contract inside `AGENTS.md`: the first markdown table under the heading `## Rules` has the columns `| Rule | Enforced by |`.
    - Each "Enforced by" cell holds one or more backticked repo-relative paths.
    - The literal `judgment` is allowed only together with a backticked doc path.

- [ ] **Step 1: Failing tests:**
  - `test_missing_rules_heading_is_error`.
  - `test_enforcer_path_must_exist`: a row whose `` `checks/nope.py` `` does not exist → error naming the rule.
  - `test_row_without_enforcer_is_error`: an empty cell → error.
  - `test_valid_table_passes`.
- [ ] **Step 2:** Run. Expected: FAIL. Then implement and run. Expected: PASS.
- [ ] **Step 3:** Write `AGENTS.md`:
  - Mission (1 paragraph).
  - Repo map, which mirrors File Structure.
  - "How to verify a change": `python3 -m unittest discover -s checks/tests && python3 -m unittest discover -s hooks/tests && python3 -m unittest discover -s scripts/tests && python3 checks/run.py && agy plugin validate . --strict`.
  - "How to vendor": `scripts/vendor.py`, then a separate `adapt:` commit.
  - `## Rules` table with these rows:

  | Rule | Enforced by |
  |---|---|
  | Files from pstack are copied verbatim and recorded | `checks/check_vendor.py` `scripts/vendor.py` |
  | Skill name matches folder, description present | `checks/check_skills.py` |
  | No dangling skill, playbook or link references | `checks/check_skills.py` |
  | Size budgets (SKILL ≤ 16 KB, rule ≤ 24 KB) | `checks/check_skills.py` |
  | Every rule has an enforcer | `checks/check_rules.py` |
  | Plugin manifest and agents load in agy | `.github/workflows/ci.yml` |

- [ ] **Step 4:** Run `python3 checks/run.py`. Expected: exit 0. Commit `feat(checks): rule table check and maintainer AGENTS.md`.

### Task 5: Vendor pstack files (byte-identical)

**Files:**
- Create via `scripts/vendor.py` only. Each upstream file (under `pstack/skills/`) maps to a destination:

| upstream (`pstack/skills/…`) | dest |
|---|---|
| `poteto-mode/SKILL.md` | `skills/vex-mode/SKILL.md` |
| `poteto-mode/worker.md` | `skills/vex-mode/worker.md` |
| `poteto-mode/playbooks/bug-fix.md` | `skills/vex-mode/playbooks/bug-fix.md` |
| `poteto-mode/playbooks/feature.md` | `skills/vex-mode/playbooks/feature.md` |
| `poteto-mode/playbooks/opening-a-pr.md` | `skills/vex-mode/playbooks/opening-a-pr.md` |
| `principle-<n>/SKILL.md` for the 9 principles in File Structure | `skills/principle-<n>/SKILL.md` |

- [ ] **Step 1:** Run `scripts/vendor.py` for each of the 14 rows.
- [ ] **Step 2:** Verify byte identity:
  ```bash
  for each row: cmp /tmp/pstack-up/pstack/skills/<up> <dest>
  ```
  Expected: no output.
- [ ] **Step 3:** Run `python3 checks/run.py`.
  Expected: **FAIL**, with only `check_skills` errors (name `poteto-mode` ≠ folder `vex-mode`, dangling refs). This proves the checks bite on real upstream content.
- [ ] **Step 4:** Commit only the vendored files and `vendor.lock`, with message `vendor: copy poteto-mode core and 9 principles from pstack@35a9094`.

### Task 6: Adapt vendored files for Antigravity

**Files:**
- Modify: the 14 vendored files, `vendor.lock` (`pending_refs`)
- Create: `rules/AGENTS.md`, `agents/vex-agent.md` (both listed in `original`)

**Interfaces:**
- Consumes: vendored files from Task 5.
- Produces:
  - Agent `vex-agent`, referenced by `skills/vex-mode/SKILL.md`.
  - The reading list block in `SKILL.md` under the heading `## Read first`, with the exact repo-relative paths of `worker.md`, the 3 playbooks and the 9 principle `SKILL.md` files. Task 8 parses this block.

- [ ] **Step 1:** Make only the edits allowed by Global Constraints:
  - `name: poteto-mode` → `name: vex-mode`; `poteto-agent` → `vex-agent`; `/poteto-mode` → `/vex-mode`.
  - Delete the "Cite only principles…" sentence (spec §6.5).
  - Delete model slugs and the `/setup-pstack` model-routing paragraphs. Subagents inherit the parent model.
  - `Task` → "the subagent tool". Remove `cursor-team-kit`, `/deslop`, `control-ui`/`control-cli` and Cursor `/loop` lines.
  - Remove each reference to a not-yet-vendored skill (`architect`, `arena`, `swarm`, `interrogate`, `unslop`, `technical-writing`, `no-comments`, `benchmark-checklist`, `show-me-your-work`, `figure-it-out`, `tdd`, `why`), and list each one in that file's `pending_refs`.
  - Add `## Read first` (spec §6.3).
- [ ] **Step 2:** Create `rules/AGENTS.md`:
  - Starts with `---\ntrigger: always_on\n---`.
  - Body = the verbatim poteto-mode lines for First message (L19), Autonomy (L76–82) and Writing the reply (L104), plus the `principle-prove-it-works` body.
  - Add one line: "Full mode: type `/vex-mode`."
- [ ] **Step 3:** Create `agents/vex-agent.md`:
  - Frontmatter: `name: vex-agent`, a `description`, `subagent: true`, `mainAgent: false`, `tools: [read_file, edit_file, write_file, run_command, manage_task, search_web]`, and **no `model`**.
  - Body = the `worker.md` rules verbatim (the fallback from spec §6.4).
- [ ] **Step 4:** Run `python3 checks/run.py && agy plugin validate . --strict`.
  Expected: exit 0 and `✔ Validation passed` with `skills 10 · agents 1 · rules 1`.
- [ ] **Step 5:** Review: `git diff HEAD~1 --stat`, then read the full diff. Every hunk must fall into an allowed edit class.
- [ ] **Step 6:** Commit `adapt: vex-mode core for antigravity`. The body lists the removed refs.

### Task 7: Probe agy hook semantics (spike, needs Vex logged in to agy)

**Files:**
- Create: `docs/decisions/2026-11-18-hook-probe.md` (findings with evidence)

This task produces facts, not code. A throwaway probe plugin lives in `/tmp/vex-probe`. Each of its hooks appends its stdin to `/tmp/vex-probe/log.jsonl` and prints a candidate output.

- [ ] **Step 1:** Install the probe with `agy plugin install /tmp/vex-probe`, then run `agy plugin list`. Expected: the probe is listed.
- [ ] **Step 2:** Run `agy -p "/hello say hi"`, where `hello` is the probe skill. Record the exact `lastUserInput` string seen by `PreInvocation`. Specifically: does it start with `/hello`, or does agy expand it to the skill text?
- [ ] **Step 3:** Find the neutral `PreToolUse` output. Try each, ask the agent to run `ls`, and record whether agy still applies its normal permission policy:
  - `{}`
  - `{"decision":""}`
  - exit 0 with no stdout
- [ ] **Step 4:** Record whether `PLUGIN_DATA` is set for a locally installed plugin, and whether `PreInvocation` fires inside subagent conversations.
- [ ] **Step 5:** Write the findings, with log excerpts, into `docs/decisions/2026-11-18-hook-probe.md`. Uninstall the probe. Commit `docs(decisions): agy hook probe findings`.
- **Gate:** if Step 2 shows that the slash command is not visible in `lastUserInput`, stop and bring it to Vex before Task 8. The activation design depends on it.

### Task 8: Mode hooks

**Files:**
- Create: `hooks/_io.py`, `hooks/activate.py`, `hooks/irreversible.py`, `hooks/stop_gate.py`, `hooks.json`, `hooks/tests/test_activate.py`, `hooks/tests/test_irreversible.py`, `hooks/tests/test_stop_gate.py`
- Modify: `AGENTS.md` (Rules table rows for the hooks)

**Interfaces:**
- Consumes: the `## Read first` block in `skills/vex-mode/SKILL.md` (Task 6), and the neutral output from `docs/decisions/2026-11-18-hook-probe.md` (Task 7). Call it `NEUTRAL`.
- Produces:
  - `_io.read_payload() -> dict`: `{}` on empty or invalid stdin.
  - `_io.emit(obj: dict) -> None`: JSON to stdout, exit 0.
  - `_io.state_dir() -> Path`: `$PLUGIN_DATA/state`, falling back to `$PLUGIN_ROOT/.state`.
  - `activate.handle(payload: dict, root: Path, state: Path) -> dict`.
  - `irreversible.classify(command: str) -> str | None`: returns a reason or `None`.
  - `irreversible.handle(payload) -> dict`.
  - `stop_gate.handle(payload, state) -> dict`.
  - Each script's `main()` = `emit(handle(read_payload(), ...))`, wrapped so that any exception emits the hook's neutral output.

- [ ] **Step 1: Failing tests for `activate`:**
  - `test_activates_on_slash_command`: `lastUserInput` = `"/vex-mode fix x"`, `conversationId` = `"c1"` → creates `state/active/c1`. Output `injectSteps[0].systemMessage.systemMessage` contains `skills/vex-mode/worker.md` as an absolute path under `root`.
  - `test_injects_once`: a second call for `c1` → `{}`.
  - `test_inactive_conversation_untouched`: `conversationId` `c2` with ordinary input → `{}` and no file.
  - `test_malformed_payload`: `{}` → `{}`.
- [ ] **Step 2: Failing tests for `irreversible.classify`:**
  - Returns a reason for:
    - `git push -f origin main`
    - `git push --force`
    - `git push --force-with-lease origin x`
    - `git push origin +main`
    - `git push --mirror`
    - `rm -rf /srv/data`
    - `psql -c 'DROP TABLE users'`
    - `terraform destroy`
    - `kubectl delete ns prod`
  - Returns `None` for:
    - `git push`
    - `git push --follow-tags`
    - `ls -la`
    - `rm -rf ./build`
    - `rm -rf node_modules`
  - The `rm -rf` rule: flag only absolute paths or `~`, never relative workspace paths.
  - `test_handle_force_asks`: a matching `run_command` → `{"decision":"force_ask","reason":...}`.
  - `test_handle_neutral`: a non-matching command → `NEUTRAL`, and **never** `"allow"`.
  - `test_handle_malformed` → `NEUTRAL`.
- [ ] **Step 3: Failing tests for `stop_gate`:**
  - `test_inactive_allows_stop`: no mark → `{}`.
  - `test_active_asks_for_evidence_once`: mark present, `terminationReason` `NO_TOOL_CALL`, `continuationActive` false → `{"decision":"continue","reason": <contains "verification evidence">}`.
  - `test_no_loop`: `continuationActive` true → `{}`.
  - `test_other_termination_allows`: `USER_CANCELED` → `{}`.
- [ ] **Step 4:** Run `python3 -m unittest discover -s hooks/tests -v`. Expected: FAIL.
- [ ] **Step 5:** Implement the 4 modules. The `stop_gate` reason text:
  > "vex-mode: before finishing, show verification evidence from the real artifact (command + output), or state why none applies."

  It comes from `principle-prove-it-works`.
- [ ] **Step 6:** Write `hooks.json` with named hooks:
  - `vex-activate`: `PreInvocation` `python3 ./hooks/activate.py`.
  - `vex-irreversible`: `PreToolUse` with matcher `run_command`, running `python3 ./hooks/irreversible.py`.
  - `vex-stop-gate`: `Stop` `python3 ./hooks/stop_gate.py`.
  - All with `timeout` 10.
- [ ] **Step 7:** Run tests (expected: PASS), then `python3 checks/run.py && agy plugin validate . --strict` (expected: pass, `hooks 1`).
- [ ] **Step 8:** Add these Rules rows to `AGENTS.md`:
  - "Full mode activates only via /vex-mode" → `hooks/activate.py`
  - "Pause before irreversible actions" → `hooks/irreversible.py`
  - "No finishing without evidence in vex-mode" → `hooks/stop_gate.py`
- [ ] **Step 9:** Commit `feat(hooks): activation, irreversible pause and stop gate`.

### Task 9: CI

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1:** Workflow on `push` and `pull_request`, `ubuntu-latest`:
  - checkout
  - `actions/setup-python@v5` with `3.12`
  - the 3 `unittest discover` runs
  - `python3 checks/run.py`
  - `jdx/mise-action@v2` with `install_args: antigravity-cli`, then `agy plugin validate . --strict`
- [ ] **Step 2:** Push `m1`, then `gh run watch`.
  Expected: green. If the agy step fails only because agy needs a login in CI:
  - Remove that step from CI.
  - Add `agy plugin validate . --strict` to the "How to verify" line in `AGENTS.md`.
  - Record the reason in `docs/decisions/`, and tell Vex.

  Never silently drop it.
- [ ] **Step 3:** Commit `ci: checks, hook tests and plugin validation`.

### Task 10: End-to-end verification and PR

**Files:**
- Create: `docs/decisions/2026-11-18-m1-verification.md`

- [ ] **Step 1:** Run `agy plugin install .`, then `agy plugin list`. Expected: `vex-mode` is enabled.
- [ ] **Step 2:** In a scratch git repo, run `agy -p "/vex-mode list the files here"`. Capture the transcript. Expected: the injected system message with the reading list appears, and the final answer carries a verification section, because the stop gate fired once.
- [ ] **Step 3:** Run `agy -p "hello"` without `/vex-mode`. Expected: no injection and no stop-gate continuation.
- [ ] **Step 4:** In the scratch repo with a dummy remote, ask the agent to `git push --force`. Expected: agy shows a forced confirmation prompt.
- [ ] **Step 5:** Write the evidence (commands + excerpts) into the decisions file. Commit, then open the PR:
  ```bash
  gh pr create --title "feat(m1): vex-mode base" --body <worker.md template: Why, What changed, Scope, Tradeoffs, Blast Radius, Verification>
  ```
  The PR is ready, not a draft. Vex merges.
