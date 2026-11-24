---
name: frontend-ui
description: "Build and verify frontend UI/UX changes with clean visual hierarchy, craft floor anti-slop rules, complete UI states, accessibility, and a Design Desk review on the real rendered surface. Use for /frontend-ui or non-trivial UI/component/layout work."
disable-model-invocation: true
---

# Frontend UI/UX

In Claude Code, read [the Claude Code adapter](../../adapters/claude-code.md) once per session before you follow this skill. It maps the agy names in vex-mode skills to Claude Code.

Build interfaces that respect the project's design system, enforce a visual craft floor, handle every real-world state, and pass a Design Desk review on the actual rendered surface.

## Before writing UI code

1. **Pick the surface mode:** `Persuade` (landing, marketing, pricing), `Operate` (app UI, dashboards, settings, tools), `Read` (docs, articles, guides), or `Experience` (portfolios, showcases). Match ambition and restraint to the mode.
2. **Reuse before inventing.** Inspect existing components, design tokens, CSS variables, and layout patterns in the repo first. If `PRODUCT.md` or `DESIGN.md` exists, read them. If `impeccable` is installed in the environment, run `impeccable context` for project context; never block if unavailable.
3. **Explore variants when direction is open.** If layout or interaction is undecided, use the **prototype** skill (`UI.md`) on a throwaway branch before writing production components.

## Craft floor and anti-slop

- **Visual hierarchy:** one clear primary action per view or section, consistent spacing scale (more space above a heading than below it), and obvious type scale/weight steps.
- **Contrast and color:** body and placeholder text `>=4.5:1`, large text `>=3:1`. On colored surfaces, tint secondary text from that hue rather than neutral gray.
- **Typography and browser surfaces:** body measure `65-75ch`, display tracking floor `-0.04em`. Theme browser defaults (`::selection`, focus rings, scrollbars, `tabular-nums`) from the palette.
- **Complete states:** handle `loading`, `empty`, `error`, `disabled`, and `long-text/overflow` states with real product copy (errors name the problem and recovery). Never build only the happy path.
- **Refuse AI slop:** no nested cards, no kickers/eyebrows above headings, no gradient text, no one-sided accent bars on rounded boxes, no hard offset shadows outside neobrutalism, no emoji/unicode standing in for an icon system, and no monospace as a decorative "tech" costume.

## Delegation

- **Code changes:** delegate component implementation to `vex-agent` with exact file paths, surface mode, token/component references, and state requirements.

## Design Desk review (Mesa de diseño)

Run this gate before finishing any UI change. `vex-agent` has no browser tools: from the main session, start the app's dev server and use the `browser` subagent to inspect the live rendered page (and run `impeccable detect` / `shot` if `impeccable` is installed).

Check all three axes and fix any defect before marking done:

1. **Aesthetics (Estética):** hierarchy holds at a glance, contrast passes, typography rhythm is clean, and zero anti-slop tells remain.
2. **UX:** primary flow is self-evident, copy is specific to the product, and all five states (`loading`, `empty`, `error`, `disabled`, `overflow`) behave cleanly.
3. **Handling (Manejo):** semantic HTML (`button`, `a`, `nav`, `label`), keyboard navigation and visible focus rings, accessible names for icon-only controls, comfortable touch targets (`>=24x24` CSS px, `44x44` preferred), mobile and desktop viewports with zero horizontal overflow or clipped controls, and zero console or network errors.

If the environment has no browser tool (such as headless runs), run the project's build, typecheck, and UI/e2e test suite and state explicitly that live visual inspection was skipped.
