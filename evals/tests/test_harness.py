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

    def test_other_workdir_and_markers_still_flagged(self):
        for cmd in ("cat /cache/vex-work/cd34/habit-tracker/habits.py", "ls ../../", "cat ~/.cache/vex-mode/runs/x"):
            self.assertTrue(self.check(cmd), cmd)


class StatsTest(unittest.TestCase):
    def test_summarize(self):
        self.assertEqual(stats.summarize([1.0, 0.0, 0.5]), {"mean": 0.5, "min": 0.0, "max": 1.0, "spread": 1.0})
        self.assertEqual(stats.summarize([]), {"mean": 0.0, "min": 0.0, "max": 0.0, "spread": 0.0})

    def test_signal_noise_and_direction(self):
        a = stats.summarize([0.5, 0.5, 0.5])
        self.assertEqual(stats.signal(a, stats.summarize([1.0, 1.0, 1.0])), "better")
        self.assertEqual(stats.signal(a, stats.summarize([0.0, 0.0, 0.0])), "worse")
        self.assertEqual(stats.signal(a, stats.summarize([0.0, 1.0, 1.0])), "noise")


if __name__ == "__main__":
    unittest.main()
