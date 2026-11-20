import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import validate_plugin

AGENTS_WARNING = {"severity": "warning", "file": "AGENTS.md", "message": "never loaded: plugins load rules only from rules/. Move it to rules/AGENTS.md"}


def report(*findings):
    return {"findings": list(findings)}


class EvaluateTest(unittest.TestCase):
    def test_clean_report_passes(self):
        self.assertEqual(validate_plugin.evaluate(report({"severity": "note", "file": "plugin.json", "message": "no logo"})), [])

    def test_root_agents_md_warning_is_allowed(self):
        self.assertEqual(validate_plugin.evaluate(report(AGENTS_WARNING)), [])

    def test_other_warning_fails(self):
        problems = validate_plugin.evaluate(report({"severity": "warning", "file": "plugin.json", "message": "no version"}))
        self.assertEqual(len(problems), 1)
        self.assertIn("no version", problems[0])

    def test_error_fails(self):
        problems = validate_plugin.evaluate(report({"severity": "error", "file": "agents/x.md", "message": "Invalid model tier"}))
        self.assertTrue(problems)

    def test_agents_md_error_is_not_allowed(self):
        problems = validate_plugin.evaluate(report({"severity": "error", "file": "AGENTS.md", "message": "never loaded"}))
        self.assertTrue(problems)


if __name__ == "__main__":
    unittest.main()


class ClaudeTest(unittest.TestCase):
    def fake(self, code):
        import os, tempfile
        script = Path(tempfile.mkdtemp(prefix="fakeclaude-")) / "claude"
        script.write_text(f"#!/bin/sh\necho \"$@\" >> \"$(dirname \"$0\")/calls\"\nexit {code}\n")
        script.chmod(0o755)
        os.environ["VEX_CLAUDE"] = str(script)
        self.addCleanup(os.environ.pop, "VEX_CLAUDE")
        return script.parent / "calls"

    def test_validates_marketplace_and_tree_strictly(self):
        calls = self.fake(0)
        self.assertEqual(validate_plugin.claude_problems(Path("/r")), [])
        lines = calls.read_text().splitlines()
        self.assertEqual(lines, ["plugin validate --strict /r", "plugin validate --strict /r/harness/claude-code"])

    def test_failure_is_a_problem(self):
        self.fake(1)
        self.assertEqual(len(validate_plugin.claude_problems(Path("/r"))), 2)
