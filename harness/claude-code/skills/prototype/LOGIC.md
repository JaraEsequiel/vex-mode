# Logic Prototype

Build a **single, self-contained HTML file** that lets anyone drive a state model by clicking buttons. Use this when the question is about business logic, state transitions, or data shape.

If the question is about layout or visual design, use `UI.md` instead.

## Process

1. **State the question.** Put a short plain-language title and one-paragraph explanation of the model and question at the top of the page.
2. **Isolate the logic in a pure module.** Inside one `<script>` block, write the reducer, state machine, or pure functions with zero DOM or button-handler dependencies so the validated logic can be lifted directly into production code later.
3. **Build the shareable HTML shell.** Plain HTML/CSS/JS, no framework, no bundler, no server. Include:
   - **Current state:** readable panel in domain language (not raw JSON), updated after every action.
   - **Free-play buttons:** one button per action, always clickable.
   - **Guided walkthroughs:** tabbed scenarios (happy path, edge cases, illegal transitions) with ordered step buttons and a reset to initial state.
4. **Capture the answer.** Once validated, lift the pure logic module into the real codebase with unit tests and keep the HTML shell out of `main`.
