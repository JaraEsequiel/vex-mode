# tax-rounding: the contract must be visible (second calibration)

- **Date:** 2026-11-20
- **Change:** the project gains `timesheet.py`, an existing caller that bills fractional hours through `invoice_total`, prints `line_total` per line, and averages `read_lines` values with float math; `read_lines` reads quantities as float. The hidden check is unchanged plus the timesheet's output.
- **Why:** the first calibration (`2026-11-20-tax-rounding-calibration.md`) failed 0/6 with and without vex-mode, all on contracts no file in the project used. A contract-verification sentence in bug-fix step 4 (branch `bugfix-contract-verify`, never pushed) gave B 1/6 vs A 0/6 on 12 salvaged runs: its runs varied argument types but had no caller showing fractional quantities, and one deleted `line_total` after `grep` found no user.
- **Run:** `calibrate vex-mode tax-rounding --runs 6`, sonnet 5.5, main at 733e829 against no plugin, 12/12 valid, US$1.29. Result: `evals/vex-mode/calibration/2026-11-20-tax-rounding-claude-code-c0d39af911ce-012738.json`.

| | vex-mode | no plugin |
|---|---|---|
| hidden outcome check | 6/6 | 6/6 |
| ran `timesheet.py` | 6/6 | 6/6 |
| reproduced before the first edit (judge) | 6/6 | 4/6 |
| showed post-fix output (judge) | 6/6 | 2/6 |
| exact arithmetic, half-up (judge) | 3/6 | 5/6 |
| final reply opens with the goal (judge) | 0/6 | 0/6 |
| mean tokens | 256k | 112k |

## Reading

- With the caller in the repo, every run finds it, runs it and keeps it working. The 0/6 floor was the case, not a model habit: Claude (and likely Gemini before it) keeps a contract it can see.
- The outcome check is now at the ceiling, so tax-rounding cannot show an outcome effect of any skill change. It remains a process case: reproduce-first and post-fix evidence still separate vex-mode from no plugin.
- The contract-verification sentence is not shipped: the problem it targeted was the case. The bug-fix step 3 line "keep the public contract" (2026-11-19, `skills-batch-a.md`) was also tuned against the invisible contract; its evidence is weaker than it looked.
- "Final reply opens with the goal" fails 6/6 with vex-mode even now that the judge sees the reply before the Stop gate: a real gap between the rule and behavior.
