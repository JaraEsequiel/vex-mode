# UI Prototype

Generate **several radically different UI variations** on a single route, switchable from a floating bottom bar. The user flips between variants in the browser, picks one (or steals parts from each), then throws the rest away.

If the question is about logic or state rather than layout and interaction, use `LOGIC.md` instead.

## Two sub-shapes (prefer A)

- **Sub-shape A: adjustment to an existing page (preferred).** Render variants on the existing route gated by `?variant=A|B|C`, keeping real header, sidebar, data fetching, params, and auth intact so variants are judged in real density.
- **Sub-shape B: a throwaway route (last resort).** Only when no existing page can host the surface. Follow the project's routing convention and include `prototype` in the path or filename.

## Process

1. **State the question and pick N.** Default to 3 variants (cap at 5). Write a one-line comment at the top of the switcher naming the question and route.
2. **Generate structurally different variants.** Export clear names (`VariantA`, `VariantB`, `VariantC`) using the project's existing styling system and components. Vary layout, information hierarchy, and primary affordance, not just colors. If `PRODUCT.md` or `DESIGN.md` exists (or `impeccable` is installed), ground variants in that context and obey the **frontend-ui** skill craft floor (readable contrast, real copy, zero AI slop such as nested cards, gradient text, or decorative side borders).
3. **Wire them with a floating bottom switcher.** Fixed bar at bottom-center with previous arrow, current variant label (`B (Sidebar layout)`), and next arrow. Sync with `?variant=` via the framework router and support `Left`/`Right` arrow keys.
4. **Automated browser + impeccable loop (max 3 rounds).** Whether invoked from **frontend-ui** skill or standalone via `/prototype`, run this closed loop before handing off to the user:
   - Start the dev server in the background.
   - Run the bundled **impeccable** skill detector (`skills/impeccable/scripts/impeccable detect <url-or-files> --json`) and the `browser` subagent across every `?variant=` route (plus `Left`/`Right` switcher keys) to verify zero console/runtime errors, readable contrast, and zero horizontal overflow on desktop and mobile.
   - If any variant fails or throws errors, fix it (via `vex-agent` or direct edit) and re-verify, capping at **3 rounds**. Stop the background dev server when done unless the user asked to keep it open.
