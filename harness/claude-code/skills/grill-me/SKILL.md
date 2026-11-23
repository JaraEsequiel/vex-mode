---
name: grill-me
description: "Interview the user relentlessly in rounds to stress-test a plan, decision, or idea before building. Use when the user invokes /grill-me or asks to stress-test or align on a design."
disable-model-invocation: true
---

# Grill Me

In Claude Code, read [the Claude Code adapter](../../adapters/claude-code.md) once per session before you follow this skill. It maps the agy names in vex-mode skills to Claude Code.

Source: adapted from `mattpocock/skills` (`grill-me` + `grilling`), collapsed into one skill for `vex-mode`.

This skill is an explicit, user-invoked pre-build interview. It temporarily overrides `never-block-on-the-human` in the main session only. Never run it from a `vex-agent` or `worker.md` subagent.

Interview the user relentlessly until you reach a shared understanding. Map the problem as a **design tree**, where each decision branches into the decisions that hang off it.

## Work in rounds

The **frontier** is every decision whose prerequisites are already settled: the questions you can ask now without guessing at answers you have not heard yet. Ask the whole frontier in one round, number each question with your recommended answer, and wait for the user's answers before starting the next round.

Format each round like this:

```
Q1. <question title>: <question body, including options when helpful>
Recommended: <your recommended answer>

Q2. <question title>: <question body, including options when helpful>
Recommended: <your recommended answer>
```

Word each question so "yes" accepts your recommended answer.

Each round reshapes the tree. Settled decisions push the frontier outward and unblock downstream questions. Recompute the frontier and ask the next round. A question that depends on an open question in the current round belongs to a later round, not this one.

## Facts vs. decisions

Finding **facts** is your job, never the user's. When a frontier question needs a fact from the codebase, filesystem, or tools, dispatch a read-only `research` subagent with a fresh context to look it up. Do not ask the user for anything you can verify yourself.

Do not stall on exploration: a running lookup is an unsettled prerequisite, so only the questions downstream of it wait for the subagent to report. Ask the rest of the frontier now.

## Finishing

The interview ends when the frontier is empty: every branch of the design tree is settled and nothing is silently assumed. Summarize the settled decisions and wait for the user to confirm shared understanding before acting or starting `/vex-mode`.
