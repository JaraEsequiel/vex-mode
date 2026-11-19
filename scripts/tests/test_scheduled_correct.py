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
        (plugins / "vex-mode/hooks").mkdir()
        for name in ("irreversible.py", "vexio.py"):
            (plugins / "vex-mode/hooks" / name).write_text((ROOT / "hooks" / name).read_text())
        self.plugins, self.cache = plugins, tmp / "cache"
        fake_home.mkdir()
        self.notes = tmp / "notes.log"
        self.gh_log = tmp / "gh.log"
        self.env = {
            "VEX_AGY": f"{sys.executable} {FAKE_AGY}",
            "FAKE_HOME": str(fake_home),
            "VEX_PLUGIN_HOME": str(plugins),
            "VEX_NOTIFY": f"{sys.executable} -c \"import sys; open({str(self.notes)!r}, 'a').write(' '.join(sys.argv[1:]) + chr(10))\"",
            "VEX_CACHE": str(self.cache),
            "VEX_GH": f"{sys.executable} -c \"import sys; open({str(self.gh_log)!r}, 'a').write(' '.join(sys.argv[1:]) + chr(10)); print('https://pr/1')\"",
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
        self.assertEqual(self.run_it("noop"), 0)
        self.assertEqual(self.worktrees(), [])
        self.assertEqual(self.branches(), "")
        self.assertTrue(list(self.state.glob("*.ndjson")))
        self.assertIn("vex-mode correct", self.notes.read_text())

    def test_commits_keep_worktree(self):
        self.assertEqual(self.run_it("commit", open_pr=False), 0)
        self.assertEqual(len(self.worktrees()), 1)
        self.assertIn("correct/", self.branches())

    def test_wrapper_pushes_branch_and_opens_pr(self):
        self.assertEqual(self.run_it("commit"), 0)
        self.assertIn("refs/heads/correct/", git(self.origin, "for-each-ref", "refs/heads"))
        self.assertEqual(git(self.origin, "rev-parse", "main"), git(self.repo, "rev-parse", "origin/main"))
        log = self.gh_log.read_text()
        self.assertIn("pr create", log)
        self.assertIn("--head correct/", log)
        self.assertIn("--base main", log)

    def test_dry_run_does_not_push(self):
        self.assertEqual(self.run_it("commit", open_pr=False), 0)
        self.assertNotIn("correct/", git(self.origin, "for-each-ref", "refs/heads"))
        self.assertFalse(self.gh_log.exists())

    def test_cut_short_run_keeps_uncommitted_work(self):
        self.assertEqual(self.run_it("ok"), 1)
        self.assertEqual(len(self.worktrees()), 1)
        self.assertIn("uncommitted", self.notes.read_text())

    def test_missing_agy_notifies_failure(self):
        os.environ["VEX_AGY"] = "/nonexistent/agy"
        self.assertEqual(self.run_it("ok"), 1)
        self.assertIn("failed", self.notes.read_text())

    def test_preflight_refuses_without_correct_skill(self):
        (self.plugins / "vex-mode/skills/correct/SKILL.md").unlink()
        self.assertEqual(self.run_it("commit"), 3)
        self.assertEqual(self.worktrees(), [])
        self.assertIn("refused", self.notes.read_text())

    def test_preflight_refuses_without_merge_guard(self):
        (self.plugins / "vex-mode/hooks/irreversible.py").write_text("def classify(c):\n    return None\n")
        self.assertEqual(self.run_it("commit"), 3)

    def test_preflight_refuses_during_an_eval(self):
        (self.cache / "vex-mode").mkdir(parents=True)
        (self.cache / "vex-mode/restore-pending").write_text("x")
        self.assertEqual(self.run_it("commit"), 3)
        (self.cache / "vex-mode/restore-pending").unlink()
        with open(self.cache / "vex-mode/eval.lock", "w") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            self.assertEqual(self.run_it("commit"), 3)

    def test_uncommitted_trail_is_committed(self):
        self.assertEqual(self.run_it("commit-trail", open_pr=False), 0)
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
        self.assertEqual(self.run_it("commit", open_pr=False), 0)
        wt = self.state / self.worktrees()[0]
        upstream = subprocess.run(["git", "-C", str(wt), "rev-parse", "--abbrev-ref", "@{u}"], capture_output=True)
        self.assertNotEqual(upstream.returncode, 0)

    def test_agent_never_sees_api_keys(self):
        os.environ["OPENAI_API_KEY"] = "sk-secret-456"
        self.addCleanup(os.environ.pop, "OPENAI_API_KEY", None)
        self.run_it("env", open_pr=False)
        leaked = [p for p in self.state.rglob("leak.txt") if "sk-secret-456" in p.read_text()]
        self.assertEqual(leaked, [])

    def test_agy_failure_keeps_worktree_and_fails(self):
        self.assertEqual(self.run_it("fail"), 1)
        self.assertEqual(len(self.worktrees()), 1)
        self.assertIn("failed", self.notes.read_text())

    def test_second_run_is_refused(self):
        self.state.mkdir(parents=True)
        with open(self.state / "run.lock", "w") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            self.assertEqual(self.run_it("noop"), 2)
        self.assertEqual(self.worktrees(), [])

    def test_base_ref_is_used(self):
        self.assertEqual(self.run_it("commit", base="origin/other", open_pr=False), 0)
        wt = self.state / self.worktrees()[0]
        self.assertTrue((wt / "other.txt").exists())


class PromptAndUnitsTest(unittest.TestCase):
    def test_prompt_shape(self):
        p = scheduled_correct.build_prompt("2026-11-15")
        self.assertTrue(p.startswith("/correct"))
        for part in ("2026-11-15", "AGENTS.md", "show-me-your-work", "How to change a skill", "Never merge",
                     "never push", ".scratch/pr.md", "paused command ends this run"):
            self.assertIn(part, p)
        self.assertNotIn("gh pr create", p)

    def test_units(self):
        units = scheduled_correct.render_units(Path("/r/scripts/scheduled_correct.py"), Path("/r"),
                                               path="/m/bin:/usr/bin", agy="/m/bin/agy")
        service, timer = units["vex-correct.service"], units["vex-correct.timer"]
        self.assertIn("Type=oneshot", service)
        self.assertIn("ExecStart=/usr/bin/python3 /r/scripts/scheduled_correct.py run --repo /r", service)
        self.assertIn("Environment=PATH=/m/bin:/usr/bin", service)
        self.assertIn("Environment=VEX_AGY=/m/bin/agy", service)
        self.assertNotIn("EnvironmentFile", service)  # judges.py reads secrets.env itself; agents must not inherit keys
        self.assertIn("OnCalendar=Sun *-*-* 03:00:00", timer)
        self.assertIn("Persistent=true", timer)


if __name__ == "__main__":
    unittest.main()
