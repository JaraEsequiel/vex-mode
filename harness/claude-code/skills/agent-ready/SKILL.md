---
name: agent-ready
description: "Prepare a repo so coding agents are stopped by checks instead of by a human: a rule table with what enforces each rule, one check command that runs the same locally and in CI, a Stop hook (agy or Claude Code) that returns the check's error to the agent, and a verify-<app> skill that drives the app and proves it can fail. Use for /agent-ready."
disable-model-invocation: true
---

# Agent-ready

In Claude Code, read [the Claude Code adapter](../../adapters/claude-code.md) once per session before you follow this skill. It maps the agy names in vex-mode skills to Claude Code.

Make this repo safe for agents that see only the files they open, copy the nearest example, and take the shortest path that compiles. Every rule ends in something that fails, not in more prose. Work in this order, and prove each artifact before the next.

## 1. Read the repo

Find, from the repo itself: the language and how the app runs, the lint, type and test commands it already has, its CI, and whether it has a GitHub remote. Ask the user only what the repo cannot tell you.

## 2. One check command

Write `scripts/check`, executable, that runs the repo's existing static checks and tests in one command and exits non-zero on any failure. If the repo has none, start with the cheapest real check its language offers (a compile or syntax pass over every source file). Don't invent a test suite here; the verify skill (step 5) covers behavior. The same command runs locally, in the hook and in CI.

## 3. The Stop hook

Copy `templates/check_on_stop.py` from this skill's folder into the repo's `.agents/`. One copy serves both harnesses; register it for each one the repo's agents use, keeping every other hook:

- agy: if `.agents/hooks.json` already exists, add the `agent-ready-check` entry from `templates/hooks.json` to it; otherwise copy the template.
- Claude Code: add the `Stop` entry from `templates/claude-settings.json` to the `hooks` key of `.claude/settings.json`, or copy the template when that file does not exist.

When the agent is about to finish with changes no remote has (uncommitted, or commits not pushed), the hook runs `scripts/check` and, on failure, sends the error back so the agent fixes it first. A check that can't run or hangs counts as a failure. It gives up after 3 tries per user message and stays silent on a cancel, an error, or a passing check. The check runs at `Stop`, where both harnesses send a hook's message back to the agent.

## 4. The rule table

In `AGENTS.md` (create it, or extend the existing one), keep a `| Rule | Enforced by |` table, following "Keep the rule table" in the **correct** skill. Enforce each rule at the highest level that works: architecture, then types and lint, then a test or the verify skill, and prose only for judgment calls. A rule nothing enforces says so in its row.

## 5. The verify skill

Run `/create-verification-skill` by following the **create-verification-skill** skill in full, including its proof that each driven journey can fail. It writes `.agents/skills/verify-<app>/`.

## 6. CI

If the repo has a GitHub remote, copy `templates/check.yml` to `.github/workflows/check.yml` (or add its job to an existing workflow of that name), and add the setup and install steps `scripts/check` needs on a fresh runner (language toolchain, dependencies). Otherwise say that CI is not set up and why.

## 7. Prove it

1. `scripts/check` passes on the repo as you leave it.
2. Make one small deliberate break (a syntax error, a violated rule). `scripts/check` fails, and the hook sends the error back for each harness you registered:
   - agy: `echo "{\"hookEventName\":\"Stop\",\"terminationReason\":\"NO_TOOL_CALL\",\"conversationId\":\"proof-$(date +%s%N)\"}" | (cd .agents && python3 check_on_stop.py ../scripts/check)` prints a `continue` with the error.
   - Claude Code: `echo "{\"hook_event_name\":\"Stop\",\"session_id\":\"proof-$(date +%s%N)\",\"prompt_id\":\"p\"}" | python3 .agents/check_on_stop.py ../scripts/check` prints a `block` with the error.
3. Restore the break. Both pass again, and the same commands print nothing.

**Reply:** each artifact with its path and the proof you ran, and every rule left without an enforcer.
