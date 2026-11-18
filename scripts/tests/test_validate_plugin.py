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
