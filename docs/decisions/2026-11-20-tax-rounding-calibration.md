# Does tax-rounding measure vex-mode? (calibration)

- **Date:** 2026-11-20
- **Run:** `python3 evals/run.py calibrate vex-mode tax-rounding --runs 6` on Claude Code, sonnet 5.5, main at 42a4668 against no plugin. 12/12 runs valid, US$1.22. Result: `evals/vex-mode/calibration/2026-11-20-tax-rounding-claude-code-c0d39af911ce.json`.
- **Why:** all 8 tax-rounding evals so far gave B vs A "noise". With 3 runs per arm, Fisher's exact test cannot reach p < 0.05 even at 3/3 vs 0/3 (p = 0.1).

| | vex-mode (A) | no plugin (N) |
|---|---|---|
| hidden outcome check | 0/6 | 0/6 |
| reproduced the bug before the first edit (judge) | 6/6 | 0/6 |
| showed post-fix output (judge) | 6/6 | 0/6 |
| root-cause fix, exact decimal math (judge) | 6/6 | 6/6 |
| final reply opens with the goal (judge) | 1/6 | 0/6 |
| mean tokens / duration / cost | 245k / 23 s / US$0.14 | 89k / 11 s / US$0.07 |

## Reading

- **The case measures vex-mode's process, strongly:** reproduce-first and show-evidence move from 0/6 to 6/6 (Fisher p = 0.002 each). It is a valid case for changes to those behaviors.
- **It does not measure correctness:** both arms fail the hidden check in every run, with the same mistake (price to `Decimal`, quantity or `read_lines` values left float, so the types no longer mix). The outcome is at the floor; a change can only show there if it targets the public contract. vex-mode's "keep the public contract" line in bug-fix step 3 does not move it.
- Criterion 3 does not discriminate (6/6 both). Criterion 1 is a real miss: the rule says the final report opens with the goal, and 5 of 6 vex-mode replies do not.
- vex-mode costs 2.75x the tokens and 2x the time on this bug.
