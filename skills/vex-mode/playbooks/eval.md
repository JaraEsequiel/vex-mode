### Eval

**You own the experiment design. Plan, blind, run, synthesize.**

**Non-negotiables for blinding:**

- No `eval`, `test`, `judge`, `experiment`, `rubric`, `score`, `compare`, `benchmark`, `candidate`, or `arena` in any directory, file, or prompt the candidate sees.
- The candidate prompt looks like an organic user request. State the goal, not the meta.
- No chain-eliciting cues. Don't ask the candidate to list which skills, principles, or files they applied. Ask for design notes generally and grade chain-following from code shape, not self-report.
- Sanitize directory and slug names. Use project-shaped names a user might pick.
- Don't tell the candidate other candidates exist.
- The judge can know it's judging but sees outputs by sanitized label only, never by model name.
- Comparing two variants: one judge scores both sets in a single pass on one scale, blind to which set each came from.

**Steps:**

1. **Frame.** State what variant is under test and what behavior counts as success. Write the rubric (3-6 concrete criteria) for the judge only. Hold it back from candidates. Pair the rubric with the case's outcome check, the code-quality measure (`"quality": true` in the case's `case.json`; it scores only runs that pass the check) and cost; change one lever per comparison.
2. **Set up sanitized environments.** Per-candidate working dir with the variant in place. Plant any context an organic task would have: a project skeleton, the skills the candidate would naturally read.
3. **Author one organic prompt.** What a user would type. No leakage of what's being measured.
4. **Run the candidates** with `python3 evals/run.py <skill> <case>` from the vex-mode source repo (the `repository` in `plugin.json`; clone it when absent, the installed plugin has no `evals/`). It builds the three arms, installs each arm's plugin build, runs one `agy -p` per candidate in its own sanitized dir, and restores the installed plugin. Same prompt to each.
5. **The same command runs one blinded judge** set in `evals/judge.json` (provider, model, effort; called over API), of a different model family than every candidate. Judge sees outputs by sanitized label and the rubric, never a model name.
6. **Verify the chain from transcripts, not self-report.** Read each candidate's `stream-json` transcript in the run directory the harness prints. Look at which files each candidate actually opened. Grade chain-following from the files it really read plus the shape of the code, never from the candidate's own claims.
7. **Read every candidate output yourself** end to end. Compare to the judge's verdict. Disagreement means a model is biased or the rubric is ambiguous. Synthesize. Record the decision with `python3 evals/run.py verdict <result> <promote|reject|inconclusive> "<synthesis>"`, per the **principle-explain-the-number** skill. Never promote when the outcome or a blocking quality measure got worse; CI rejects it.

**Not a plugin variant.** The harness runs only its three fixed arms (base and variant on the candidate model, base on the upgrade model). For any other comparison, such as several models or efforts on a repo task, build it by hand with the same discipline:

- Run each candidate as a `vex-agent` with `model` and `effort`, one environment each. When the user asks for worktrees, use them with neutral branch names, and say that `git worktree list` shows the others and that they share the remote. Put "no push" in the prompt and check with `git ls-remote`. Otherwise use clones with the remote removed.
- Write the decision rule before the runs. Calibrate the outcome-check script: it passes a reference solution and fails the base.
- Judge over API with `evals/harness/judges.py` from the source repo (it reads the key and base URL from `~/.config/vex-mode/secrets.env` and sends a `User-Agent`), never `agy -p`. Strip model names from the material (commit trailers carry them) and grep for them. Judge twice in opposite order; a winner that flips with the order is a tie.

**Reply:** variant under test, rubric, per-candidate notes, judge's verdict, your synthesis, and a recommendation for whether to promote the variant.
