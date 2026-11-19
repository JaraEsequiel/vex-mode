import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "evals/agent-ready/cases/habit-tracker"
TEMPLATES = ROOT / "skills/agent-ready/templates"
ENV = dict(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")


def write(path: Path, text: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    if mode:
        path.chmod(mode)


class HiddenCheckTest(unittest.TestCase):
    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix="habit-work-")) / "habit-tracker"
        self.addCleanup(shutil.rmtree, self.work.parent, ignore_errors=True)
        shutil.copytree(CASE / "project", self.work)
        for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "root"]):
            subprocess.run(["git", "-C", str(self.work), *args], check=True, capture_output=True, env=dict(os.environ, **ENV))

    def reference_setup(self, check_body="python3 -m py_compile habits.py", hook=True):
        w = self.work
        write(w / "AGENTS.md", "# Agents\n\n| Rule | Enforced by |\n|---|---|\n| Code compiles | `scripts/check` |\n")
        write(w / "scripts/check", f"#!/bin/sh\nset -e\n{check_body}\n", 0o755)
        if hook:
            (w / ".agents").mkdir(exist_ok=True)
            shutil.copy(TEMPLATES / "check_on_stop.py", w / ".agents/check_on_stop.py")
            shutil.copy(TEMPLATES / "hooks.json", w / ".agents/hooks.json")
        else:
            write(w / ".agents/hooks.json", '{"noop": {"Stop": [{"type": "command", "command": "true"}]}}')
        write(w / ".agents/skills/verify-habits/SKILL.md", "---\nname: verify-habits\ndescription: drive habits\n---\n\n# Verify\n")
        write(w / ".agents/skills/verify-habits/features/README.md", "# Map\n\n- [Add](./add.md)\n")
        write(w / ".agents/skills/verify-habits/features/add.md", "# Add a habit\n")

    def run_check(self):
        r = subprocess.run([sys.executable, "-I", str(CASE / "check.py"), str(self.work)], capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def test_hidden_check_rejects_bare_project(self):
        code, out = self.run_check()
        self.assertNotEqual(code, 0, out)

    def test_hidden_check_accepts_reference_setup(self):
        self.reference_setup()
        code, out = self.run_check()
        self.assertEqual(code, 0, out)

    def test_hidden_check_rejects_a_check_that_never_fails(self):
        self.reference_setup(check_body="true")
        code, out = self.run_check()
        self.assertNotEqual(code, 0, out)
        self.assertIn("check", out)

    def test_hidden_check_rejects_a_hook_that_never_continues(self):
        self.reference_setup(hook=False)
        code, out = self.run_check()
        self.assertNotEqual(code, 0, out)
        self.assertIn("hook", out)


    def test_hook_with_agy_guards_is_accepted(self):
        self.reference_setup()
        write(self.work / ".agents/guarded.py",
              "import json, subprocess, sys\n"
              "p = json.load(sys.stdin)\n"
              "if p['terminationReason'] != 'NO_TOOL_CALL' or p['continuationActive']:\n    sys.exit(0)\n"
              "root = p['workspacePaths'][0]\n"
              "if subprocess.run(['./scripts/check'], cwd=root).returncode:\n"
              "    print(json.dumps({'decision': 'continue', 'reason': 'check failed'}))\n")
        write(self.work / ".agents/hooks.json", '{"g": {"Stop": [{"type": "command", "command": "python3 guarded.py"}]}}')
        code, out = self.run_check()
        self.assertEqual(code, 0, out)

    def test_non_executable_shell_check_is_found(self):
        self.reference_setup()
        (self.work / "scripts/check").unlink()
        write(self.work / "scripts/check.sh", "set -e\npython3 -m py_compile habits.py\n")
        write(self.work / ".agents/hooks.json",
              '{"a": {"Stop": [{"type": "command", "command": "python3 check_on_stop.py sh ../scripts/check.sh"}]}}')
        code, out = self.run_check()
        self.assertEqual(code, 0, out)

    def test_hook_that_ignores_the_check_is_rejected(self):
        self.reference_setup()
        write(self.work / ".agents/dirty.sh",
              "cd .. && [ -n \"$(git status --porcelain)\" ] && echo '{\"decision\": \"continue\"}'; exit 0\n")
        write(self.work / ".agents/hooks.json", '{"d": {"Stop": [{"type": "command", "command": "sh dirty.sh"}]}}')
        for args in (["add", "-A"], ["commit", "-qm", "setup"]):
            subprocess.run(["git", "-C", str(self.work), *args], check=True, capture_output=True, env=dict(os.environ, **ENV))
        code, out = self.run_check()
        self.assertNotEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
