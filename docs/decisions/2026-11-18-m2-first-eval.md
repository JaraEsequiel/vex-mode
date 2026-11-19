# M2 first real eval: vex-mode, case `tax-rounding`

- **Date:** 2026-11-18
- **agy:** 1.5.11. Candidates `gemini-4-neon-medium` (arms A, B) and `gemini-4-neon-high` (arm C), judge `claude-opus-5-5-high`. 3 runs per arm.
- **Arms:** A = `main` (`539ae35e6a18`), B = `m2` (`751c0e58ac82`), C = `main` on the upgrade model.
- **Result:** `evals/vex-mode/results/2026-11-18-751c0e58ac82.json`. **Verdict: promote.**
- **Run dir (local only):** `~/.cache/vex-mode/runs/20261118-221441-180861`

## Numbers (mean, spread over 3 runs)

| Arm | Compliance | Outcome | Tokens | Time (s) |
|---|---|---|---|---|
| A | 1.00 (0) | 0.67 (1.0) | 78,213 (17,850) | 249 (51) |
| B | 1.00 (0) | 1.00 (0) | 66,444 (11,243) | 232 (39) |
| C | 1.00 (0) | 1.00 (0) | 138,528 (37,026) | 560 (120) |

- **B vs A:** noise on every metric. The gap in outcome is one run.
- **C vs A:** noise on quality. Tokens and time are worse, at about 2x and 2.3x.

## What reading every output showed

1. **The judge and the hidden check disagreed once, and the check was right.**
   - Run A/5 (judge label R3) passed all 4 rubric criteria.
   - Its fix made `invoice_total` require `Decimal` inputs, so the shipped API now raises `TypeError` for float callers.
   - The rubric does not ask about compatibility; `check.py` does. This is the failure mode cursor/plugins#1178 describes. Pairing compliance with outcome caught it.
2. **The harness hid committed work from the judge (fixed).**
   - Every candidate committed its fix on a branch, so a diff against `HEAD` was empty.
   - Fixed: the diff now runs from the planted commit, guarded by `test_judge_sees_committed_changes`. The result was re-graded with `evals/run.py rejudge`.
3. **Every run delegated the edit to a subagent.** Each parent used `manage_subagents`, and the parent transcript holds no edit steps.
4. **Every run read the 14 injected files first,** in all three arms. The activation hook works on both `main` and `m2`.

## Limits

- **n=3 per arm.** One run moves the mean by 0.33.
- **The case exercises the bug-fix path, not the Eval playbook** that M2 adds. The result shows no harm, not a benefit.
- **Isolation checks only the parent's reads.** Subagents are separate conversations (`2026-11-18-hook-probe.md`, finding 4), and their transcripts are not in `stream-json`. A subagent that read a rubric would go unflagged.
  - Mitigation in place: rubrics and the run dir live outside every candidate's project, and the plugin build excludes `evals/`.
