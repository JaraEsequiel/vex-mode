import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from harness import arms, isolation, stats, transcript

FIX = HERE / "fixtures"
CASE = {
    "candidate_model": "gemini-4-neon-medium",
    "upgrade_model": "gemini-4-neon-high",
}


class TranscriptTest(unittest.TestCase):
    def test_parse_reads_commands_usage(self):
        t = transcript.parse((FIX / "run_ok.ndjson").read_text())
        self.assertEqual(t.reads, ["/work/proj/notes.txt"])
        self.assertEqual(t.commands, ['find . -name "notes.txt"'])
        self.assertEqual(t.status, "SUCCESS")
        self.assertEqual(t.total_tokens, 15184)
        self.assertEqual(t.model, "gemini-3.8-flash-low")
        self.assertEqual(t.response, "lantern\n")
        self.assertGreater(t.duration_s, 0)

    def test_parse_keeps_every_tool_in_order(self):
        t = transcript.parse((FIX / "run_ok.ndjson").read_text())
        self.assertEqual(t.steps, ['run_command: find . -name "notes.txt" (exit 0)', "read_file: /work/proj/notes.txt"])
        edit = '{"event": "step_update", "step_update": {"step_type": "tool", "state": "DONE", "tool_info": {"name": "edit_file", "parameters": {"TargetFile": "/w/a.py", "Instruction": "x"}}}}'
        self.assertEqual(transcript.parse(edit).steps, ['edit_file: {"TargetFile": "/w/a.py", "Instruction": "x"}'])

    def test_unfinished_run_counts_as_failure(self):
        t = transcript.parse((FIX / "run_unfinished.ndjson").read_text())
        self.assertEqual(t.status, "UNFINISHED")
        self.assertEqual(t.total_tokens, 0)

    def test_unfinished_run_keeps_step_tokens(self):
        t = transcript.parse((FIX / "run_unfinished.ndjson").read_text())
        self.assertGreater(t.step_tokens, 0)

    def test_parse_claude_code_stream(self):
        t = transcript.parse_claude((FIX / "claude_run_ok.ndjson").read_text())
        self.assertEqual(t.conversation_id, "s1")
        self.assertEqual(t.model, "claude-sonnet-5-5")
        self.assertEqual(t.status, "SUCCESS")
        self.assertEqual(t.response, "Fixed the total.")
        self.assertEqual(t.duration_s, 12.5)
        self.assertEqual(t.total_tokens, 1000)  # modelUsage covers subagents too
        self.assertEqual(t.cost_usd, 0.42)
        # Subagent calls (parent_tool_use_id set) count: their reads can break isolation too.
        self.assertEqual(t.reads, ["/plug/skills/x/SKILL.md", "/w"])
        self.assertEqual(t.commands, ["python3 -m pytest -q"])
        self.assertEqual(t.steps[0], "Read: /plug/skills/x/SKILL.md")
        self.assertEqual(t.steps[2], "Bash: python3 -m pytest -q (error) [subagent]")
        self.assertTrue(t.steps[1].startswith("Agent: "))
        self.assertIn("Grep", t.steps[4])

    def test_parse_claude_code_error_and_unfinished(self):
        err = transcript.parse_claude(json.dumps({"type": "result", "subtype": "error_max_turns", "is_error": True,
                                                  "usage": {"input_tokens": 1, "output_tokens": 2}}))
        self.assertEqual(err.status, "ERROR_MAX_TURNS")
        self.assertEqual(err.total_tokens, 3)
        cut = transcript.parse_claude((FIX / "claude_run_ok.ndjson").read_text().rsplit("\n", 2)[0])
        self.assertEqual(cut.status, "UNFINISHED")
        self.assertEqual(cut.reads, ["/plug/skills/x/SKILL.md", "/w"])

    def test_errors_are_kept(self):
        agy = json.dumps({"event": "result", "result": {"status": "ERROR", "error": "Individual quota reached. Resets in 130h."}})
        self.assertIn("quota", transcript.parse(agy).error)
        cc = json.dumps({"type": "result", "subtype": "success", "is_error": True, "result": "Claude usage limit reached",
                         "api_error_status": 429})
        t = transcript.parse_claude(cc)
        self.assertIn("usage limit", t.error)
        self.assertIn("429", t.error)
        self.assertNotEqual(t.status, "SUCCESS")

    def test_claude_reply_before_the_stop_gate(self):
        def say(text):
            return json.dumps({"type": "assistant", "parent_tool_use_id": None,
                               "message": {"content": [{"type": "text", "text": text}]}})
        gate = json.dumps({"type": "user", "message": {"content": [
            {"type": "text", "text": "Stop hook feedback:\nvex-mode: before finishing, show verification evidence"}]}})
        sub = json.dumps({"type": "assistant", "parent_tool_use_id": "t9",
                          "message": {"content": [{"type": "text", "text": "subagent words"}]}})
        end = json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "Evidence: 10.83"})
        t = transcript.parse_claude("\n".join([say("Looking."), say("Fixed: the total is 10.83."), sub, gate,
                                                say("Evidence: 10.83"), end]))
        self.assertEqual(t.gate_reply, "Fixed: the total is 10.83.")
        self.assertEqual(t.response, "Evidence: 10.83")
        self.assertEqual(transcript.parse_claude("\n".join([say("Done."), end])).gate_reply, "")

    def test_claude_hook_denial_with_a_text_message(self):
        denial = json.dumps({"type": "system", "subtype": "permission_denied",
                             "message": "vex-mode: irreversible action (rm -rf on an absolute path)."})
        end = json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "done"})
        self.assertEqual(transcript.parse_claude(denial + "\n" + end).status, "SUCCESS")

    def test_claude_unfinished_run_keeps_message_tokens(self):
        msg = {"type": "assistant", "message": {"id": "m1", "usage": {"input_tokens": 3, "output_tokens": 4}, "content": []}}
        self.assertEqual(transcript.parse_claude(json.dumps(msg) + "\n" + json.dumps(msg)).step_tokens, 7)

    def test_garbage_lines_are_skipped(self):
        t = transcript.parse("not json\n\n")
        self.assertEqual(t.status, "UNFINISHED")


class ArmsTest(unittest.TestCase):
    def test_arms_fixed_order_and_levers(self):
        a, b, c = arms.build_arms(CASE, "base123", "head456", "claude-opus-5-5-high")
        self.assertEqual([x.label for x in (a, b, c)], ["A", "B", "C"])
        self.assertEqual((a.model, b.model), (CASE["candidate_model"],) * 2)
        self.assertNotEqual(a.plugin_ref, b.plugin_ref)
        self.assertEqual(a.plugin_ref, c.plugin_ref)
        self.assertEqual(c.model, CASE["upgrade_model"])

    def test_judge_family_must_differ(self):
        with self.assertRaises(ValueError):
            arms.build_arms(CASE, "a", "b", "gemini-4-argon-high")
        with self.assertRaises(ValueError):
            arms.build_arms(dict(CASE, upgrade_model="gpt-6.2-astra"), "a", "b", "gpt-6.2-sol")


class IsolationTest(unittest.TestCase):
    def test_flags_reads_of_run_dir_and_repo(self):
        t = transcript.Transcript(reads=[
            "/run/x/rubric.md",
            "/repo/evals/x/cases/c/rubric.md",
            "/plug/vex-mode/skills/vex-mode/SKILL.md",
            "/elsewhere/skills/vex-mode/SKILL.md",
            "/work/app.py",
        ])
        v = isolation.violations(t, plugin_root=Path("/plug/vex-mode"), forbidden=[Path("/run/x"), Path("/repo")])
        self.assertEqual(len(v), 3, v)
        self.assertTrue(any("/run/x/rubric.md" in x for x in v))
        self.assertTrue(any("/repo/evals" in x for x in v))
        self.assertTrue(any("/elsewhere/skills" in x for x in v))

    def test_clean_run_has_no_violations(self):
        t = transcript.Transcript(reads=["/work/app.py", "/plug/vex-mode/skills/x/SKILL.md"])
        self.assertEqual(isolation.violations(t, plugin_root=Path("/plug/vex-mode"), forbidden=[Path("/run")]), [])


class IsolationHardeningTest(unittest.TestCase):
    def roots(self):
        return dict(plugin_root=Path("/plug/vex-mode"), forbidden=[Path("/cache/vex-mode"), Path("/repo")],
                    workdir=Path("/cache/vex-work/ab12/invoices"), work_root=Path("/cache/vex-work"))

    def test_dotdot_path_is_normalized(self):
        t = transcript.Transcript(reads=["/cache/vex-work/ab12/invoices/../../../vex-mode/runs/1/labels.json"])
        self.assertTrue(isolation.violations(t, **self.roots()))

    def test_relative_read_resolves_against_workdir(self):
        t = transcript.Transcript(reads=["../../cd34/invoices/invoices.py"])
        self.assertTrue(isolation.violations(t, **self.roots()))
        self.assertEqual(isolation.violations(transcript.Transcript(reads=["invoices.py"]), **self.roots()), [])

    def test_other_workdirs_and_evals_paths_are_forbidden(self):
        for path in ("/cache/vex-work/cd34/invoices/invoices.py", "/home/u/clone/evals/x/cases/c/rubric.md"):
            self.assertTrue(isolation.violations(transcript.Transcript(reads=[path]), **self.roots()), path)

    def test_shell_reads_are_checked(self):
        for cmd in ("cat /repo/evals/x/cases/c/rubric.md", "cat ~/.cache/vex-mode/runs/*/judge-prompt.md",
                    "ls ../../", "grep -r total /home/u/clone/evals"):
            t = transcript.Transcript(commands=[cmd])
            self.assertTrue(isolation.violations(t, **self.roots(), home=Path("/home/u"), cache=Path("/cache")), cmd)
        ok = transcript.Transcript(commands=["python3 invoices.py inv-1042.csv", "git diff HEAD~1"])
        self.assertEqual(isolation.violations(ok, **self.roots(), home=Path("/home/u"), cache=Path("/cache")), [])


class IsolationFalsePositiveTest(unittest.TestCase):
    """Commands from the M4 agent-ready eval that only touched their own workdir."""
    def check(self, cmd):
        roots = dict(plugin_root=Path("/plug/vex-mode"), forbidden=[Path("/cache/vex-mode"), Path("/repo")],
                     workdir=Path("/cache/vex-work/ab12/habit-tracker"), work_root=Path("/cache/vex-work"),
                     home=Path("/home/u"), cache=Path("/cache"))
        return isolation.violations(transcript.Transcript(commands=[cmd]), **roots)

    def test_own_workdir_path_is_allowed(self):
        self.assertEqual(self.check("cd .agents && printf '{\"cwd\":\"/cache/vex-work/ab12/habit-tracker\"}' | python3 hook.py"), [])

    def test_cd_then_relative_path_is_resolved(self):
        self.assertEqual(self.check("cd .agents && python3 ../scripts/stop_check.py"), [])
        self.assertTrue(self.check("cd .. && cat ../cd34/habit-tracker/habits.py"))

    def test_shell_expansions_are_not_resolved_as_paths(self):
        self.assertEqual(self.check("printf '%s' \"$(pwd)/..\""), [])

    def test_variable_cd_into_the_arm_then_relative_reads(self):
        # 2026-11-20 shipping-cleanup slot 6: a legitimate read of the arm's own files through a shell variable.
        cmd = ("B=/plug/vex-mode; cd $B; for f in adapters/claude-code.md skills/vex-mode/worker.md "
               "skills/vex-mode/playbooks/refactoring.md; do echo \"=== $f\"; cat $f; done")
        self.assertEqual(self.check(cmd), [])

    def test_variables_do_not_hide_a_forbidden_path(self):
        self.assertTrue(self.check("X=/repo/evals/x/cases/c; cat $X/rubric.md"))
        self.assertTrue(self.check("D=/cache/vex-work/cd34; cat ${D}/habit-tracker/habits.py"))

    def test_unresolvable_cd_still_checks_absolute_paths(self):
        self.assertEqual(self.check("cd \"$(git rev-parse --show-toplevel)\" && cat skills/x/SKILL.md"), [])
        self.assertTrue(self.check("cd \"$(pwd)\" && cat /cache/vex-work/cd34/habit-tracker/habits.py"))

    def test_unbalanced_quotes_still_split_on_separators(self):
        # 2026-11-20 points-cleanup slot 2: a heredoc with an apostrophe made shlex fail, and the fallback
        # kept "habit-tracker;" as one token, which is not the workdir.
        cmd = "cd /cache/vex-work/ab12/habit-tracker; cat > a.py <<'E'\nx = 'it''s\nE\ngit rm -q b.json"
        self.assertEqual(self.check(cmd), [])
        self.assertTrue(self.check("cd /cache/vex-work/ab12/habit-tracker; echo it's; cat ../../cd34/habit-tracker/a.py"))

    def test_paths_inside_the_own_workdir_are_never_a_skill_copy(self):
        # 2026-11-20 points-cleanup slot 6: a for-list of arm-relative names, read through $C/$f.
        cmd = ("C=/plug/vex-mode; for f in skills/vex-mode/worker.md skills/vex-mode/playbooks/bug-fix.md; "
               "do cat $C/$f; done")
        self.assertEqual(self.check(cmd), [])
        self.assertTrue(self.check("cat /elsewhere/skills/vex-mode/worker.md"))

    def test_other_workdir_and_markers_still_flagged(self):
        for cmd in ("cat /cache/vex-work/cd34/habit-tracker/habits.py", "ls ../../", "cat ~/.cache/vex-mode/runs/x"):
            self.assertTrue(self.check(cmd), cmd)


class StatsTest(unittest.TestCase):
    def test_summarize(self):
        self.assertEqual(stats.summarize([1.0, 0.0, 0.5]), {"mean": 0.5, "min": 0.0, "max": 1.0, "spread": 1.0})
        self.assertEqual(stats.summarize([]), {"mean": 0.0, "min": 0.0, "max": 0.0, "spread": 0.0})

    def test_rank_p_matches_brute_force_with_ties(self):
        from itertools import combinations

        a, b = [1, 2, 2, 3, 5], [2, 3, 3, 4]
        pooled = a + b
        order = sorted(pooled)
        rank = {v: (order.index(v) + 1 + len(order) - order[::-1].index(v)) / 2 for v in pooled}
        observed = sum(rank[v] for v in b)
        sums = [sum(rank[pooled[i]] for i in c) for c in combinations(range(len(pooled)), len(b))]
        self.assertAlmostEqual(stats.rank_p(a, b), sum(s >= observed for s in sums) / len(sums))

    def test_rank_signal_direction_and_p(self):
        # 2026-11-20 backlog: compliance 0.90 against 0.50 over 10 runs read as noise under the spread rule,
        # because one run at each end stretched the spread past the gap.
        bare = [0.5] * 8 + [0.0, 1.0]
        plugin = [0.9] * 8 + [0.5, 1.0]
        signal, p = stats.rank_signal(bare, plugin)
        self.assertEqual(signal, "better")
        self.assertLess(p, 0.01)
        self.assertEqual(stats.rank_signal(plugin, bare)[0], "worse")
        self.assertEqual(stats.rank_signal([0.5, 0.5, 0.5], [1.0, 1.0, 1.0]), ("better", 0.05))
        self.assertEqual(stats.rank_signal([0.5, 0.5, 0.5], [0.0, 1.0, 1.0])[0], "noise")
        self.assertEqual(stats.rank_signal([1.0, 1.0], [1.0, 1.0]), ("noise", 1.0))

    def test_rank_signal_lower_is_better_for_costs(self):
        self.assertEqual(stats.rank_signal([900, 1000, 1100], [400, 500, 600], lower_is_better=True),
                         ("better", 0.05))

    def test_fisher_one_sided_p(self):
        self.assertAlmostEqual(stats.fisher_p([0, 0, 0], [1, 1, 1]), 0.05)
        self.assertAlmostEqual(stats.fisher_p([1, 0, 0], [1, 1, 1]), 0.2)
        self.assertEqual(stats.fisher_p([1, 1], [1, 1]), 1.0)

    def test_outcome_signal_tests_pass_fail_counts(self):
        # 2026-11-20 points-cleanup: 10/10 against 4/10 is a real gap the spread rule called noise.
        plugin, bare = [1] * 10, [1] * 4 + [0] * 6
        self.assertEqual(stats.outcome_signal(bare, plugin), ("better", 0.005))
        self.assertEqual(stats.outcome_signal(plugin, bare), ("worse", 0.005))
        self.assertEqual(stats.outcome_signal([1, 0, 0], [1, 1, 1]), ("noise", 0.2))
        self.assertEqual(stats.outcome_signal([1, 1, 1], [1, 1, 1]), ("noise", 1.0))


if __name__ == "__main__":
    unittest.main()
