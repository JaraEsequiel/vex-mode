import fcntl
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import scheduled_correct

FAKE_AGY = ROOT / "evals/tests/fake_agy.py"
ENV = dict(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True,
                          env=dict(os.environ, **ENV)).stdout.strip()


class RunTest(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp(prefix="sched-"))
        self.origin = tmp / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        seed = tmp / "seed"
        seed.mkdir()
        (seed / "app.py").write_text("broken\n")
        git(seed, "init", "-q", "-b", "main")
        git(seed, "add", "-A")
        git(seed, "commit", "-qm", "seed")
        git(seed, "remote", "add", "origin", str(self.origin))
        git(seed, "push", "-q", "origin", "main")
        git(seed, "checkout", "-qb", "other")
        (seed / "other.txt").write_text("o\n")
        git(seed, "add", "-A")
        git(seed, "commit", "-qm", "other")
        git(seed, "push", "-q", "origin", "other")
        self.repo = tmp / "repo"
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.repo)], check=True)
        self.state = tmp / "state"
        fake_home = tmp / "fake"
        plugins = tmp / "plugins"
        (plugins / "vex-mode/skills/correct").mkdir(parents=True)
        (plugins / "vex-mode/skills/correct/SKILL.md").write_text("x")
        fake_home.mkdir()
        self.notes = tmp / "notes.log"
        self.env = {
            "VEX_AGY": f"{sys.executable} {FAKE_AGY}",
            "FAKE_HOME": str(fake_home),
            "VEX_PLUGIN_HOME": str(plugins),
            "VEX_NOTIFY": f"{sys.executable} -c \"import sys; open({str(self.notes)!r}, 'a').write(' '.join(sys.argv[1:]) + chr(10))\"",
            **ENV,
        }
        self.old = {k: os.environ.get(k) for k in [*self.env, "FAKE_AGY_MODE"]}
        os.environ.update(self.env)

    def tearDown(self):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def run_it(self, mode="ok", **kw):
        os.environ["FAKE_AGY_MODE"] = mode
        return scheduled_correct.run(self.repo, state=self.state, model="gemini-4-neon-high", **kw)

    def worktrees(self):
        return sorted(p.name for p in self.state.glob("wt-*"))

    def branches(self):
        return git(self.repo, "branch", "--list", "correct/*")

    def test_no_commits_cleans_up(self):
        self.assertEqual(self.run_it("ok"), 0)
        self.assertEqual(self.worktrees(), [])
        self.assertEqual(self.branches(), "")
        self.assertTrue(list(self.state.glob("*.ndjson")))
        self.assertIn("vex-mode correct", self.notes.read_text())

    def test_commits_keep_worktree(self):
        self.assertEqual(self.run_it("commit"), 0)
        self.assertEqual(len(self.worktrees()), 1)
        self.assertIn("correct/", self.branches())

    def test_uncommitted_trail_is_committed(self):
        self.assertEqual(self.run_it("commit-trail"), 0)
        wt = self.state / self.worktrees()[0]
        self.assertIn("docs/decisions/2026-01-01-correct.tsv", git(wt, "show", "--name-only", "HEAD"))
        self.assertEqual(git(wt, "status", "--porcelain"), "")
        self.assertTrue(list(self.state.glob("*-correct.tsv")))

    def test_trail_without_fix_is_kept_outside_the_cleaned_worktree(self):
        self.assertEqual(self.run_it("trail"), 0)
        self.assertEqual(self.worktrees(), [])
        self.assertEqual(self.branches(), "")
        self.assertTrue(list(self.state.glob("*-correct.tsv")))

    def test_branch_does_not_track_main(self):
        self.assertEqual(self.run_it("commit"), 0)
        wt = self.state / self.worktrees()[0]
        upstream = subprocess.run(["git", "-C", str(wt), "rev-parse", "--abbrev-ref", "@{u}"], capture_output=True)
        self.assertNotEqual(upstream.returncode, 0)

    def test_agy_failure_keeps_worktree_and_fails(self):
        self.assertEqual(self.run_it("fail"), 1)
        self.assertEqual(len(self.worktrees()), 1)
        self.assertIn("failed", self.notes.read_text())

    def test_second_run_is_refused(self):
        self.state.mkdir(parents=True)
        with open(self.state / "run.lock", "w") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            self.assertEqual(self.run_it("ok"), 2)
        self.assertEqual(self.worktrees(), [])

    def test_base_ref_is_used(self):
        self.assertEqual(self.run_it("commit", base="origin/other"), 0)
        wt = self.state / self.worktrees()[0]
        self.assertTrue((wt / "other.txt").exists())


class PromptAndUnitsTest(unittest.TestCase):
    def test_prompt_shape(self):
        p = scheduled_correct.build_prompt("2026-11-15", open_pr=True)
        self.assertTrue(p.startswith("/correct"))
        for part in ("2026-11-15", "AGENTS.md", "show-me-your-work", "How to change a skill", "Never merge", "gh pr create", "paused command ends this run"):
            self.assertIn(part, p)
        q = scheduled_correct.build_prompt("2026-11-15", open_pr=False)
        self.assertNotIn("gh pr create", q)
        self.assertIn("Do not push", q)

    def test_units(self):
        units = scheduled_correct.render_units(Path("/r/scripts/scheduled_correct.py"), Path("/r"))
        service, timer = units["vex-correct.service"], units["vex-correct.timer"]
        self.assertIn("Type=oneshot", service)
        self.assertIn("ExecStart=/usr/bin/python3 /r/scripts/scheduled_correct.py run --repo /r", service)
        self.assertIn("OnCalendar=Sun *-*-* 03:00:00", timer)
        self.assertIn("Persistent=true", timer)


if __name__ == "__main__":
    unittest.main()
