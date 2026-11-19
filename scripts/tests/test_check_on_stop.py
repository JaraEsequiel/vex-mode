import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "skills/agent-ready/templates/check_on_stop.py"
ENV = dict(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")


class CheckOnStopTest(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp(prefix="agent-ready-"))
        self.addCleanup(shutil.rmtree, self.repo, ignore_errors=True)
        self.tmp = Path(tempfile.mkdtemp(prefix="agent-ready-state-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.repo / "scripts").mkdir()
        check = self.repo / "scripts/check"
        check.write_text("#!/bin/sh\nif [ -f broken ]; then echo 'lint: app.py:3 bad thing'; exit 1; fi\necho ok\n")
        check.chmod(0o755)
        (self.repo / ".agents").mkdir()
        if TEMPLATE.exists():
            shutil.copy(TEMPLATE, self.repo / ".agents/check_on_stop.py")
        (self.repo / "app.py").write_text("x = 1\n")
        for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "init"]):
            subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True, env=dict(os.environ, **ENV))
        self.conv = str(uuid.uuid4())

    def stop(self, stdin=None, check="../scripts/check"):
        payload = json.dumps({"hookEventName": "Stop", "conversationId": self.conv}) if stdin is None else stdin
        r = subprocess.run([sys.executable, "check_on_stop.py", check], cwd=self.repo / ".agents", input=payload,
                           capture_output=True, text=True, env=dict(os.environ, TMPDIR=str(self.tmp)))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def dirty(self, broken=True):
        (self.repo / "app.py").write_text("x = 2\n")
        if broken:
            (self.repo / "broken").write_text("1")

    def test_clean_tree_prints_nothing(self):
        (self.repo / "broken").write_text("1")
        subprocess.run(["git", "-C", str(self.repo), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "b"], check=True, env=dict(os.environ, **ENV))
        self.assertEqual(self.stop(), "")

    def test_failing_check_continues_with_output(self):
        self.dirty()
        out = json.loads(self.stop())
        self.assertEqual(out["decision"], "continue")
        self.assertIn("lint: app.py:3 bad thing", out["reason"])

    def test_passing_check_prints_nothing(self):
        self.dirty(broken=False)
        self.assertEqual(self.stop(), "")

    def test_gives_up_after_three(self):
        self.dirty()
        outs = [self.stop() for _ in range(4)]
        self.assertTrue(all(outs[:3]))
        self.assertEqual(outs[3], "")

    def test_counter_is_per_conversation(self):
        self.dirty()
        for _ in range(3):
            self.stop()
        self.conv = str(uuid.uuid4())
        self.assertTrue(self.stop())

    def test_malformed_input_is_silent(self):
        self.dirty()
        self.assertEqual(self.stop(stdin=""), "")
        self.assertEqual(self.stop(stdin="not json"), "")

    def test_missing_check_is_reported_once(self):
        self.dirty()
        out = json.loads(self.stop(check="../scripts/nope"))
        self.assertEqual(out["decision"], "continue")
        self.assertIn("nope", out["reason"])
        for _ in range(3):
            self.stop(check="../scripts/nope")
        self.assertEqual(self.stop(check="../scripts/nope"), "")


if __name__ == "__main__":
    unittest.main()
