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
    "judge_model": "claude-opus-5-5-high",
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

    def test_unfinished_run_counts_as_failure(self):
        t = transcript.parse((FIX / "run_unfinished.ndjson").read_text())
        self.assertEqual(t.status, "UNFINISHED")
        self.assertEqual(t.total_tokens, 0)

    def test_garbage_lines_are_skipped(self):
        t = transcript.parse("not json\n\n")
        self.assertEqual(t.status, "UNFINISHED")


class ArmsTest(unittest.TestCase):
    def test_arms_fixed_order_and_levers(self):
        a, b, c = arms.build_arms(CASE, "base123", "head456")
        self.assertEqual([x.label for x in (a, b, c)], ["A", "B", "C"])
        self.assertEqual((a.model, b.model), (CASE["candidate_model"],) * 2)
        self.assertNotEqual(a.plugin_ref, b.plugin_ref)
        self.assertEqual(a.plugin_ref, c.plugin_ref)
        self.assertEqual(c.model, CASE["upgrade_model"])

    def test_judge_family_must_differ(self):
        with self.assertRaises(ValueError):
            arms.build_arms(dict(CASE, judge_model="gemini-4-argon-high"), "a", "b")
        with self.assertRaises(ValueError):
            arms.build_arms(dict(CASE, upgrade_model="claude-opus-5-5-high"), "a", "b")


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
