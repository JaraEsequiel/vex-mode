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

    def test_interpreter_with_relative_script(self):
        self.dirty(broken=False)
        r = subprocess.run([sys.executable, "check_on_stop.py", "sh", "../scripts/check"], cwd=self.repo / ".agents",
                           input=json.dumps({"conversationId": self.conv, "terminationReason": "NO_TOOL_CALL"}),
                           capture_output=True, text=True, env=dict(os.environ, TMPDIR=str(self.tmp)))
        self.assertEqual(r.stdout.strip(), "")

    def stop(self, stdin=None, check="../scripts/check", reason="NO_TOOL_CALL", prompt="fix it", timeout=None):
        payload = json.dumps({"hookEventName": "Stop", "conversationId": self.conv, "terminationReason": reason,
                              "lastUserInput": prompt}) if stdin is None else stdin
        env = dict(os.environ, TMPDIR=str(self.tmp))
        if timeout:
            env["AGENT_READY_CHECK_TIMEOUT"] = str(timeout)
        r = subprocess.run([sys.executable, "check_on_stop.py", check], cwd=self.repo / ".agents", input=payload,
                           capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def dirty(self, broken=True):
        (self.repo / "app.py").write_text("x = 2\n")
        if broken:
            (self.repo / "broken").write_text("1")

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


    def test_cancel_or_error_never_continues(self):
        self.dirty()
        for reason in ("USER_CANCELED", "ERROR", "MAX_INVOCATIONS", "MAX_TOKEN_BUDGET_EXCEEDED"):
            self.assertEqual(self.stop(reason=reason), "", reason)

    def test_unrunnable_check_is_a_failure(self):
        self.dirty()
        (self.repo / "scripts/check").chmod(0o644)
        out = json.loads(self.stop())
        self.assertEqual(out["decision"], "continue")
        self.assertIn("check", out["reason"])

    def test_non_utf8_output_is_reported(self):
        self.dirty()
        (self.repo / "scripts/check").write_text("#!/bin/sh\nprintf 'bad \\377 byte\\n'\nexit 1\n")
        out = json.loads(self.stop())
        self.assertIn("bad", out["reason"])

    def test_hanging_check_is_killed_and_reported(self):
        self.dirty()
        pidfile = self.tmp / "pid"
        (self.repo / "scripts/check").write_text(f"#!/bin/sh\nsleep 30 &\necho $! > {pidfile}\nwait\n")
        out = json.loads(self.stop(timeout=1))
        self.assertIn("timed out", out["reason"])
        pid = int(pidfile.read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_new_prompt_resets_the_counter(self):
        self.dirty()
        for _ in range(3):
            self.stop(prompt="turn one")
        self.assertEqual(self.stop(prompt="turn one"), "")
        self.assertTrue(self.stop(prompt="turn two"))

    def test_committed_broken_change_is_checked(self):
        (self.repo / "broken").write_text("1")
        subprocess.run(["git", "-C", str(self.repo), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "b"], check=True, env=dict(os.environ, **ENV))
        self.assertTrue(self.stop())

    def test_pushed_clean_tree_prints_nothing(self):
        origin = self.tmp / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
        (self.repo / "broken").write_text("1")
        for args in (["add", "-A"], ["commit", "-qm", "b"], ["remote", "add", "origin", str(origin)],
                     ["push", "-q", "origin", "HEAD:refs/heads/main"], ["fetch", "-q", "origin"]):
            subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True, env=dict(os.environ, **ENV))
        self.assertEqual(self.stop(), "")

    def test_huge_single_line_is_capped(self):
        self.dirty()
        (self.repo / "scripts/check").write_text("#!/bin/sh\nprintf '%01000000d' 7\nprintf 'END_MARK'\nexit 1\n")
        out = json.loads(self.stop())
        self.assertLess(len(out["reason"]), 9000)
        self.assertIn("END_MARK", out["reason"])

    def test_corrupt_counter_counts_as_zero(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("check_on_stop_mod", TEMPLATE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.dirty()
        old = tempfile.tempdir
        tempfile.tempdir = str(self.tmp)
        try:
            counter = mod._counter(self.repo, self.conv, "fix it")
        finally:
            tempfile.tempdir = old
        counter.parent.mkdir(parents=True, exist_ok=True)
        for garbage in ("", "abc"):
            counter.write_text(garbage)
            out = json.loads(self.stop())
            self.assertEqual(out["decision"], "continue")

    def test_symlinked_hook_uses_symlink_folder_as_root(self):
        self.dirty()
        real = self.tmp / "elsewhere"
        real.mkdir()
        shutil.copy(TEMPLATE, real / "check_on_stop.py")
        (self.repo / ".agents/check_on_stop.py").unlink()
        (self.repo / ".agents/check_on_stop.py").symlink_to(real / "check_on_stop.py")
        out = json.loads(self.stop())
        self.assertEqual(out["decision"], "continue")
        self.assertIn("lint: app.py:3 bad thing", out["reason"])

    def test_check_path_relative_to_repo_root(self):
        self.dirty()
        out = json.loads(self.stop(check="scripts/check"))
        self.assertEqual(out["decision"], "continue")
        self.assertIn("lint: app.py:3 bad thing", out["reason"])


if __name__ == "__main__":
    unittest.main()


SETTINGS = ROOT / "skills/agent-ready/templates/claude-settings.json"


class ClaudeCodeCheckOnStopTest(unittest.TestCase):
    """The same template as a Claude Code Stop hook, run the way .claude/settings.json runs it."""

    setUp = CheckOnStopTest.setUp
    dirty = CheckOnStopTest.dirty

    def cc(self, prompt_id="p1", session=None, active=False):
        payload = {"hook_event_name": "Stop", "session_id": self.conv if session is None else session, "prompt_id": prompt_id,
                   "stop_hook_active": active, "cwd": str(self.repo)}
        command = json.loads(SETTINGS.read_text())["hooks"]["Stop"][0]["hooks"][0]["command"]
        env = dict(os.environ, TMPDIR=str(self.tmp), CLAUDE_PROJECT_DIR=str(self.repo))
        r = subprocess.run(["sh", "-c", command], cwd="/", input=json.dumps(payload),
                           capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_cc_failing_check_blocks_with_output(self):
        self.dirty()
        out = json.loads(self.cc())
        self.assertEqual(out["decision"], "block")
        self.assertIn("lint: app.py:3 bad thing", out["reason"])

    def test_cc_passing_check_prints_nothing(self):
        self.dirty(broken=False)
        self.assertEqual(self.cc(), "")

    def test_cc_gives_up_after_three_per_prompt(self):
        self.dirty()
        for _ in range(3):
            self.assertIn("block", self.cc(active=True))
        self.assertEqual(self.cc(active=True), "")
        self.assertIn("block", self.cc(prompt_id="p2"))

    def test_cc_without_session_is_silent(self):
        self.dirty()
        self.assertEqual(self.cc(session=""), "")
