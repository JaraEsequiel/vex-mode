---
name: agent-ready
description: "Prepare a repo so coding agents are stopped by checks instead of by a human: a rule table with what enforces each rule, one check command that runs the same locally and in CI, an agy Stop hook that returns the check's error to the agent, and a verify-<app> skill that drives the app and proves it can fail. Use for /agent-ready."
disable-model-invocation: true
---

# Agent-ready

Make this repo safe for agents that see only the files they open, copy the nearest example, and take the shortest path that compiles. Every rule ends in something that fails, not in more prose. Work in this order, and prove each artifact before the next.

## 1. Read the repo

Find, from the repo itself: the language and how the app runs, the lint, type and test commands it already has, its CI, and whether it has a GitHub remote. Ask the user only what the repo cannot tell you.

## 2. One check command

Write `scripts/check`, executable, that runs the repo's existing static checks and tests in one command and exits non-zero on any failure. If the repo has none, start with the cheapest real check its language offers (a compile or syntax pass over every source file). Don't invent a test suite here; the verify skill (step 5) covers behavior. The same command runs locally, in the hook and in CI.

## 3. The Stop hook

Copy `templates/check_on_stop.py` and `templates/hooks.json` from this skill's folder into the repo's `.agents/`. When the agent is about to finish with uncommitted changes, the hook runs `scripts/check` and, on failure, sends the error back so the agent fixes it first. It gives up after 3 tries per conversation and stays silent on a clean tree. agy ignores a `PostToolUse` hook's output, so the check runs at `Stop`.

## 4. The rule table

In `AGENTS.md` (create it, or extend the existing one), keep a `| Rule | Enforced by |` table, following "Keep the rule table" in the **correct** skill. Enforce each rule at the highest level that works: architecture, then types and lint, then a test or the verify skill, and prose only for judgment calls. A rule nothing enforces says so in its row.

## 5. The verify skill

Run `/create-verification-skill` by following the **create-verification-skill** skill in full, including its proof that each driven journey can fail. It writes `.agents/skills/verify-<app>/`.

## 6. CI

If the repo has a GitHub remote, copy `templates/check.yml` to `.github/workflows/check.yml`. Otherwise say that CI is not set up and why.

## 7. Prove it

1. `scripts/check` passes on the repo as you leave it.
2. Make one small deliberate break (a syntax error, a violated rule). `scripts/check` fails, and `echo '{"hookEventName":"Stop","conversationId":"proof"}' | (cd .agents && python3 check_on_stop.py ../scripts/check)` prints a `continue` with the error.
3. Restore the break. Both pass again, and the hook prints nothing.

Then delete the hook's proof counter (`$TMPDIR/agent-ready/`) so the real sessions start fresh.

**Reply:** each artifact with its path and the proof you ran, and every rule left without an enforcer.
