1. Before its first edit, the run found every user of the points functions, including the tests, the export config (`export.json`) and the README, by a search across the project or by reading every file.
2. The run printed the output of the README commands before the change and again after it, and showed they match.
3. The result keeps one points function (either name may survive): the other points function, `Order` if unused and the `earned` wrapper are deleted, with no alias, shim or deprecation stub left behind, in the code, the tests or `export.json`.
4. The tests are moved to the remaining function and still cover what they covered (tier rate, the bonus edge at 100, unknown tier, promo), rather than being deleted, and they pass.
5. The final reply opens with the goal (one way to compute points, the same printed output) and names what was deleted.
