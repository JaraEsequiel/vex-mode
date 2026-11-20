# Does a turn end on a write-only command? (Stop gate gap from #34)

- **Date:** 2026-11-20
- **Question:** since #34, the Claude Code Stop gate skips its ask when the turn's last main-agent tool call is `Bash` (`hooks/stop_gate.py`, `_ran_a_command_last`). A `Bash` call that only writes a file (`cat > f <<EOF`, `python3 - <<EOF ... open(p,'w')`, `sed -i`) would also skip the ask, with no check after the last change. Does that happen?
- **Data:** every Claude Code transcript in the eval cache, `~/.cache/vex-mode/runs/*/transcripts/*.ndjson`: 20 runs from 20261120-003232 to 20261120-150744 (tax-rounding 46, shipping-cleanup 36, points-cleanup 201 transcripts; evals and calibrations, all arms), 283 transcripts. Main agent only (`parent_tool_use_id` empty). The cache also holds 117 agy transcripts from 2026-11-18/19; they have no Claude Code tool calls and the Claude Code gate does not apply to them, so they are left out.

All 283 end on a `Bash` call. Of them, 94 contain a heredoc:

- 80 run code or a comparison after the heredoc's terminator: a before/after `diff`, `python3 <script> ...`, `python3 -m unittest`, a `git stash` rerun of the old code.
- 12 run only `git log` or `git status` after it. In 11 the heredoc is a commit message (`git commit -F - <<EOF`), not a file write. Read one by one, none writes after its last check: the call before the commit ends on a before/after `diff` of the README commands or an old-versus-new equivalence script (in one run a read-only `git diff` comes between). The 12th stashes the change, copies the old code, and compares it with the new in the heredoc.
- 2 end at the heredoc. Both are Python scripts that compare the old code with the new one, so they are checks too.

**No transcript ends on a write-only command.**

## Decision

Keep `stop_gate.py` as is. Telling a write from a check inside one shell command takes a heuristic, and a wrong "write" brings back the ask that #34 removed (about 80k tokens a run, repeating checks the agent had already shown; 2026-11-20 calibration). That would fix a case never observed at the price of a measured cost.

Reopen this if an eval transcript shows a turn that ends on a write-only `Bash` call, or on a commit right after an unchecked write, and finishes without evidence. Run the script below on the new runs and attach the transcript.

## Reproduce

```bash
cd ~/.cache/vex-mode/runs && python3 - <<'EOF'
import collections, glob, json, re
last_tools, heredoc_tails = collections.Counter(), collections.Counter()
for f in glob.glob('*/transcripts/*.ndjson'):
    last = None
    for line in open(f).read().splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get('type') != 'assistant' or e.get('parent_tool_use_id'):
            continue
        for c in (e.get('message') or {}).get('content') or []:
            if isinstance(c, dict) and c.get('type') == 'tool_use':
                last = c
    last_tools[last['name'] if last else 'none'] += 1
    if not last or last['name'] != 'Bash':
        continue
    cmd = last['input'].get('command', '')
    m = re.search(r"<<-?\s*['\"]?(\w+)['\"]?", cmd)
    if not m:
        continue
    parts = re.split(r"\n" + m.group(1) + r"\s*(?:\n|$)", cmd, maxsplit=1)
    tail = re.sub(r"^[&;| ]+", "", parts[-1].strip() if len(parts) > 1 else '')
    heredoc_tails[tail.split()[0] if tail else '(ends at heredoc)'] += 1
    if not tail:
        print('ends at heredoc:', f)
print(last_tools)  # 'none' counts the agy transcripts, which have no Claude Code tool calls
print(heredoc_tails)  # a tail of only `git log`/`git status` follows a commit message: read the call before it
EOF
```
