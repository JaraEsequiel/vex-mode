---
name: prototype
description: "Build a throwaway prototype to answer a design question. Use when the user invokes /prototype, wants to sanity-check whether a state model or logic feels right, or wants to explore UI variations before committing."
disable-model-invocation: true
---

# Prototype

In Claude Code, read [the Claude Code adapter](../../adapters/claude-code.md) once per session before you follow this skill. It maps the agy names in vex-mode skills to Claude Code.

Source: adapted from `mattpocock/skills` (`skills/engineering/prototype`).

A prototype is **throwaway code that answers one question**. The question decides the shape.

## Pick a branch

Identify which question is being answered from the user's prompt or surrounding code:

- **"Does this logic / state model feel right?"** -> read `LOGIC.md` in this folder. Build a single shareable HTML file (free-play buttons plus tabbed guided walkthroughs) that pushes a pure state module through tricky cases.
- **"What should this look like?"** -> read `UI.md` in this folder. Generate 3 structurally different UI variations on a single route, switchable via a `?variant=` search param and a floating bottom bar.

If the question is ambiguous, default to whichever branch matches the surrounding code (backend/state module -> `LOGIC.md`; page/component -> `UI.md`) and state the assumption at the top of the prototype.

## Rules for both branches

1. **Throwaway from day one.** Never land throwaway prototype code on `main`. Work on a throwaway branch (`prototype/<topic>`) or an explicitly named scratch file, and mark prototype files clearly in their name or header.
2. **Trivial to run.** A UI prototype starts from one existing dev command. A logic demo is one self-contained HTML file opened directly in a browser.
3. **No persistence by default.** Keep state in memory. Only touch a scratch database or local file if persistence itself is the question under test.
4. **Skip the polish.** No tests, no extra error handling, no speculative abstractions. The goal is fast learning.
5. **Surface the state.** Render the full relevant state on every action (`LOGIC.md`) or variant switch (`UI.md`).
6. **Capture the answer, then clean up.** Fold the validated decision (or pure logic module) into real production code with normal tests, keep the throwaway branch only as a reference if needed, and keep `main` free of prototype scaffolding.
