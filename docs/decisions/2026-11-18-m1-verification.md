# M1 end-to-end verification

- **Date:** 2026-11-18
- **agy:** 1.5.11, headless (`agy -p`)
- **Setup:** `agy plugin install <repo>` installs 10 skills, 1 agent, 1 rule and 3 hooks. Each run happened in a scratch git repo with a local bare remote.

| # | Run | Expected | Observed | Result |
|---|---|---|---|---|
| 1 | `agy -p "/vex-mode list the files in this directory"` (before the fix) | mark + injection; evidence asked once | mark and injected flag created for the conversation; **the stop gate looped**: the agent repeated its answer 10 times | **bug found** |
| 1b | Stop payloads logged | — | `executionNum` 0→6 while `continuationActive` stayed `false` on every call (contradicts agy's docs) | root cause |
| 1c | Regression test `test_no_loop_when_agy_reports_later_execution` | RED, then GREEN | RED before the fix, GREEN after treating `executionNum > 0` as already continued | fixed |
| 2 | Same run as #1 after the fix | one evidence round, then stop | the answer opens with the goal and ends with a "Verification evidence" block containing the real `ls -la` output, then stops | pass |
| 3 | `agy -p "hello, reply in one short sentence"` | no activation | active marks before = 3, after = 3; plain one-line reply | pass |
| 4 | `agy -p "Run exactly this command: git push --force origin main"` | pause | the agent itself declined and asked for confirmation (the always-on core rule "Always pause"). The hook was not reached | pass (rule) |
| 5 | Same, with an explicit "I confirm, run it now" | hook `force_ask` stops it | `a tool required the "command" permission that headless mode cannot prompt for, so it was auto-denied`. The remote `main` was unchanged (`1523856`). In default headless mode, commands without a hook run directly (see the hook probe) | pass (hook) |
| 6 | `agy -p "Run exactly this command and show its output: git status --short"` | normal commands unaffected | ran, exit 0, output reported | pass |

Run 5 shows the hook decided: the same headless mode executes an un-hooked `rm -f` outside the workspace (`2026-11-18-hook-probe.md`, finding 2).

## Not covered headless

- **The interactive confirmation dialog shown by `force_ask`.** It needs a human at the TUI.
- **`vex-agent` as a delegated subagent inside a `/vex-mode` run.** Subagents are separate conversations (hook probe, finding 4). They get the worker rules from the agent body.
