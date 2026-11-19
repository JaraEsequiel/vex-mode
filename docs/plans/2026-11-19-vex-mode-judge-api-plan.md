# vex-mode eval judge over API — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The eval judge calls a provider's API directly (default OpenAI `gpt-6.2-sol`), configurable by provider, model and API key, so judging no longer depends on agy's argv limit, workspace permissions or Claude quota.

**Architecture:**
- `evals/harness/judges.py` holds one small adapter per provider:
  - `openai`: Responses API;
  - `anthropic`: Messages API;
  - `agy`: today's path, kept.

  Each takes `(prompt, schema, model, effort)` and returns `(verdict_dict | None, error | None, usage)`.
- `evals/judge.json` (versioned) picks the provider, model and effort, and env vars override it. Keys come from env or `~/.config/vex-mode/secrets.env`.
- `run.py` and `rejudge` call the configured adapter. `case.json` loses `judge_model`.

**Tech Stack:** Python 3 stdlib (`urllib.request`, `json`, `http.server` for tests). No SDKs, per the repo's stdlib-only rule (see Rulings below).

**Spec:** `docs/specs/2026-11-18-vex-mode-design.md` §8.2 (corrected 2026-11-19).

## Sources read for this plan (2026-11-19)

| Source | What it settles here |
|---|---|
| OpenAI model page `gpt-6.2-sol` | It exists; 1.05M context, 128k output; Responses API and structured outputs; effort `minimal`–`max` (`none` rejected). |
| OpenAI structured outputs guide + Responses create reference | `POST https://api.openai.com/v1/responses`, `Authorization: Bearer`, `text.format = {"type":"json_schema","name","schema","strict":true}`. Strict: every object `additionalProperties:false` and every property required. The text is in `output[].content[]` (`type:"output_text"`). Refusal is a `{"type":"refusal"}` part; `status:"incomplete"` comes with `incomplete_details.reason`. Usage is in `usage.input_tokens/output_tokens/output_tokens_details.reasoning_tokens`. Not documented there: HTTP error table and 429 retry headers, so the adapter treats any non-2xx as an error that carries its body. |
| skill `claude-api` (cached 2026-11-03) | Anthropic Messages: `output_config.format` for JSON schema, `claude-opus-5-5`, effort inside `output_config`, adaptive thinking; never an OpenAI-compatible shim for Claude. |
| `evals/harness/judge.py` `SCHEMA`, `parse_output`, `check_verdict` | `SCHEMA` lacks `additionalProperties:false`, so `strict` needs it added. `parse_output` reads agy's `structured_output`; the API adapters return the parsed object directly. |
| `docs/decisions/2026-11-19-m4-eval.md` | Why the judge leaves agy: `E2BIG`, read denied, quota. |

## Global Constraints

- Python stdlib only; no network in unit tests: the adapters take a base URL, and tests run a local `http.server`.
- Defaults: `evals/judge.json` = `{"provider": "openai", "model": "gpt-6.2-sol", "effort": "medium"}`.
- Env overrides: `VEX_JUDGE_PROVIDER`, `VEX_JUDGE_MODEL`, `VEX_JUDGE_EFFORT`; base URLs `VEX_OPENAI_BASE_URL` (default `https://api.openai.com/v1`) and `VEX_ANTHROPIC_BASE_URL` (default `https://api.anthropic.com/v1`).
- Keys: `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` from env, else `~/.config/vex-mode/secrets.env` (`KEY=value` lines). The loader refuses a secrets file readable by group or others. No key is ever written to a result, log or prompt file.
- Request timeout 600 s; one retry on 429/5xx after `retry-after` seconds or 30 s.
- The judge family must differ from both candidate models (existing rule), now checked against `evals/judge.json`.

## Review Focus

1. **A key leaks into a committed result or the run dir.** Covered: `test_key_never_written` (Task 2) greps the result and run dir.
2. **The provider returns a refusal, an incomplete status or a non-JSON body.** That must be a judge error (compliance None), never a crash or an invented verdict. Covered: `test_refusal_incomplete_and_garbage_are_errors` (Task 1).
3. **A missing key.** The eval must fail before any candidate runs, not after 40 minutes. Covered: `test_missing_key_fails_before_runs` (Task 2).
4. **A world-readable secrets file.** It is refused with a clear message. Covered: `test_secrets_file_permissions` (Task 1).
5. **Strict-schema drift.** The schema sent to OpenAI must satisfy strict rules recursively. Covered: `test_openai_schema_is_strict` (Task 1).

---

### Task 1: `evals/harness/judges.py`

**Interfaces — produces:**
- `load_config(repo: Path) -> dict` (provider, model, effort, after env overrides).
- `api_key(provider: str) -> str | None`.
- `judge(prompt: str, schema: dict, cfg: dict, cwd: Path) -> tuple[dict | None, str | None, dict]`: verdict, error and usage `{input, output, reasoning}`.
- `strict_schema(schema) -> dict`.

- [ ] **Step 1: Write the failing tests** in `evals/tests/test_judges.py`, against a local `http.server` that records requests and replies with canned bodies:
  - `test_openai_request_shape`: URL `/responses`; Bearer header; `model`, `reasoning.effort`, `text.format.type == "json_schema"`, `strict` true; the prompt in `input`.
  - `test_openai_parses_output_text`.
  - `test_anthropic_request_shape_and_parse`: `/messages`, `x-api-key`, `anthropic-version`, `output_config.format`.
  - `test_refusal_incomplete_and_garbage_are_errors`.
  - `test_retry_once_on_429`.
  - `test_openai_schema_is_strict`: recursive check of `additionalProperties` and `required`.
  - `test_env_overrides_config`.
  - `test_secrets_file_permissions`: 0644 → error; 0600 → key read.
  - `test_agy_provider_uses_existing_path` (fake agy).
- [ ] **Step 2: Run them.** Expected: FAIL, module missing.
- [ ] **Step 3: Implement** with `urllib.request`. The agy adapter wraps today's subprocess call and `parse_output`.
- [ ] **Step 4: Run them.** Expected: PASS. Commit `feat(evals): judge adapters for OpenAI, Anthropic and agy`.

### Task 2: Wire the judge into the harness, checks and timer

**Files:** `evals/run.py`, `evals/harness/arms.py`, `checks/check_evals.py`, `evals/judge.json`, both `case.json`, tests, `scripts/scheduled_correct.py` (unit `EnvironmentFile=-%h/.config/vex-mode/secrets.env`), `AGENTS.md`, `README.md`.

- [ ] **Step 1: Write the failing tests:**
  - `test_run.py`: `test_missing_key_fails_before_runs` (no candidate call was made); `test_result_records_judge_provider_and_usage`; `test_key_never_written`; and the existing judge tests passing through a fake OpenAI server.
  - `test_check_evals.py`: the judge family check reads `evals/judge.json`; a case with a leftover `judge_model` is an error.
  - `test_scheduled_correct.py`: the unit has the `EnvironmentFile` line.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.**
  - `_judge` calls `judges.judge`.
  - The result's `judge` becomes `{provider, model, effort, error, usage}`.
  - `rejudge` uses the current config, so old results can be re-graded.
  - `arms.build_arms` takes the judge model from the config.
- [ ] **Step 4:** run the full verify command. Expected: green, except that `check_evals` still wants the agent-ready verdict. Commit `feat(evals): the judge is configured globally and called over API`.

### Task 3: Calibrate, then grade the pending result

Needs `OPENAI_API_KEY` in `~/.config/vex-mode/secrets.env` (the user creates it; chmod 600).

- [ ] **Step 1: Calibration.** `rejudge` a copy of the Opus-graded run `20261119-112048-870168` (its result is in git history at `8626075`'s follow-up commit) with `gpt-6.2-sol`. Compare per criterion against Opus's verdict (B 4/4; A 1/4; C 2/4). Write the agreement into `docs/decisions/2026-11-19-judge-api.md`. If agreement is below 30 of 36 criteria, stop and report before using it.
- [ ] **Step 2: Grade.** `rejudge evals/agent-ready/results/2026-11-19-habit-tracker-42bf4660d570.json`. Read the outputs and record the verdict.
- [ ] **Step 3:** full verify; push `m4`; update PR #4's body.

## Rulings

- Stdlib `urllib` instead of the official SDKs: the repo is stdlib-only (Global Constraints since M2), and the judge makes one request per eval. Cost if wrong: the adapters must track API changes by hand. This is the one place the `claude-api` skill would prefer the SDK; noted here so the reviewer sees it.
