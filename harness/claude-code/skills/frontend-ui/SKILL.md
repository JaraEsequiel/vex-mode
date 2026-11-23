---
name: frontend-ui
description: "Build and verify frontend UI/UX changes with clean visual hierarchy, complete UI states, accessibility, and real browser checks. Use for /frontend-ui or non-trivial UI/component/layout work."
disable-model-invocation: true
---

# Frontend UI/UX

In Claude Code, read [the Claude Code adapter](../../adapters/claude-code.md) once per session before you follow this skill. It maps the agy names in vex-mode skills to Claude Code.

Build interfaces that respect the project's design system, handle every real-world state, and are verified on the actual rendered surface.

## Before writing UI code

1. **Reuse before inventing.** Inspect existing components, design tokens, CSS variables, and layout patterns in the repo first. Match the project's styling system (Tailwind, CSS modules, shadcn, QML, etc.) rather than introducing a parallel one.
2. **Explore variants when direction is open.** If layout or interaction is undecided, use the **prototype** skill (`UI.md`) on a throwaway branch before writing production components.

## UI quality bar

- **Visual hierarchy:** one clear primary action per view or section, consistent spacing scale, and scannable typography.
- **Complete states:** handle loading, empty, error, disabled, and long-text/overflow states. Never build only the happy path.
- **Responsive layout:** verify mobile/narrow and desktop viewports without horizontal overflow or clipped controls.
- **Accessibility:** use semantic HTML (`button`, `a`, `nav`, `label`), keyboard focus states, accessible names for icon-only controls, and readable contrast.

## Delegation and verification

- **Code changes:** delegate component implementation to `vex-agent` with exact file paths, token/component references, and state requirements.
- **Visual verification:** `vex-agent` has no browser tools. From the main session, start the app's dev server and use the `browser` subagent to inspect the live rendered page, exercise key interactions, check responsive layout, and confirm zero console or network errors.
- If the environment has no browser tool (such as headless runs), run the project's build, typecheck, and UI/e2e test suite and state explicitly that live visual inspection was skipped.
