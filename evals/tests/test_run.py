import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import run
from harness import judge

CASE = {
    "runs": 2,
    "candidate_model": "gemini-4-neon-medium",
    "upgrade_model": "gemini-4-neon-high",
    "judge_model": "claude-opus-5-5-high",
    "workdir": "ledger-app",
    "timeout_s": 60,
}
CHECK = "import pathlib, sys\nsys.exit(0 if 'fixed' in (pathlib.Path(sys.argv[1]) / 'app.py').read_text() else 1)\n"


def git(root: Path, *args: str) -> str:
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True, env=env).stdout


def write(root: Path, files: dict) -> None:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


class RunTest(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp(prefix="harness-"))
        self.repo, self.home, self.cache = tmp / "repo", tmp / "home", tmp / "cache"
        self.plugins = self.home / "plugins"
        self.plugins.mkdir(parents=True)
        write(self.plugins / "vex-mode", {"plugin.json": "{}", "skills/x/SKILL.md": "original install"})
        write(self.repo, {
            "plugin.json": "{}",
            "skills/x/SKILL.md": "v1",
            "evals/x/cases/c1/prompt.md": "/vex-mode the total is wrong",
            "evals/x/cases/c1/rubric.md": "1. Fixes it.",
            "evals/x/cases/c1/check.py": CHECK,
            "evals/x/cases/c1/case.json": json.dumps(CASE),
            "evals/x/cases/c1/project/app.py": "broken\n",
        })
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "base")
        git(self.repo, "checkout", "-qb", "feature")
        (self.repo / "skills/x/SKILL.md").write_text("v2")
        git(self.repo, "commit", "-qam", "variant")
        self.env = {
            "VEX_AGY": f"{sys.executable} {HERE / 'fake_agy.py'}",
            "VEX_PLUGIN_HOME": str(self.plugins),
            "VEX_CACHE": str(self.cache),
            "FAKE_HOME": str(self.home),
            "FAKE_AGY_MODE": "ok",
        }
        self.old = {k: os.environ.get(k) for k in [*self.env, "FAKE_PEEK"]}
        os.environ.update(self.env)

    def tearDown(self):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def run_eval(self):
        return run.run_eval(self.repo, "x", "c1", base="main", variant="HEAD")

    def installed(self) -> str:
        return (self.plugins / "vex-mode/skills/x/SKILL.md").read_text()

    def test_end_to_end_with_fake_agy(self):
        path = self.run_eval()
        result = json.loads(path.read_text())
        self.assertEqual(path.parent, self.repo / "evals/x/results")
        self.assertEqual(sorted(result["arms"]), ["A", "B", "C"])
        for arm in "ABC":
            self.assertEqual(len(result["arms"][arm]["runs"]), 2)
            for m in ("compliance", "outcome", "tokens", "duration_s"):
                self.assertIn("spread", result["metrics"][arm][m])
            self.assertEqual(result["metrics"][arm]["outcome"]["mean"], 1.0)
        self.assertEqual(result["arms"]["A"]["model"], "gemini-4-neon-medium")
        self.assertEqual(result["arms"]["C"]["model"], "gemini-4-neon-high")
        self.assertNotEqual(result["arms"]["A"]["tree_sha256"], result["arms"]["B"]["tree_sha256"])
        self.assertEqual(result["tree_sha256"], result["arms"]["B"]["tree_sha256"])
        self.assertIsNone(result["verdict"])
        self.assertIsNone(result["judge"]["error"])
        self.assertEqual(self.installed(), "original install")

    def test_restores_plugin_when_a_run_fails(self):
        os.environ["FAKE_AGY_MODE"] = "crash"
        result = json.loads(self.run_eval().read_text())
        runs = [r for arm in "ABC" for r in result["arms"][arm]["runs"]]
        unfinished = [r for r in runs if r["status"] == "UNFINISHED"]
        self.assertEqual(len(unfinished), 1)
        self.assertEqual(unfinished[0]["outcome"], 0)
        self.assertEqual(unfinished[0]["compliance"], 0.0)
        self.assertEqual(self.installed(), "original install")

    def test_restores_plugin_when_harness_aborts(self):
        os.environ["FAKE_AGY_MODE"] = "badinstall"
        with self.assertRaises(Exception):
            self.run_eval()
        self.assertEqual(self.installed(), "original install")

    def test_peek_invalidates_run(self):
        os.environ["FAKE_AGY_MODE"] = "peek"
        os.environ["FAKE_PEEK"] = str(self.repo / "evals/x/cases/c1/rubric.md")
        result = json.loads(self.run_eval().read_text())
        runs = [r for arm in "ABC" for r in result["arms"][arm]["runs"]]
        self.assertTrue(all(r["invalid"] for r in runs))
        self.assertTrue(all(r["outcome"] == 0 for r in runs))

    def test_judge_missing_label_sets_error(self):
        os.environ["FAKE_AGY_MODE"] = "badjudge"
        result = json.loads(self.run_eval().read_text())
        self.assertIn("R6", result["judge"]["error"])
        missing = [r for arm in "ABC" for r in result["arms"][arm]["runs"] if r["compliance"] is None]
        self.assertEqual(len(missing), 1)
        self.assertTrue(any(result["metrics"][arm]["compliance"] is None for arm in "ABC"))

    def test_refuses_dirty_variant(self):
        (self.repo / "skills/x/SKILL.md").write_text("dirty")
        with self.assertRaises(run.EvalError):
            self.run_eval()

    def test_verdict_subcommand_sets_fields(self):
        path = self.run_eval()
        self.assertEqual(run.main(["verdict", str(path), "inconclusive", "spread larger than the gap"]), 0)
        result = json.loads(path.read_text())
        self.assertEqual((result["verdict"], result["synthesis"]), ("inconclusive", "spread larger than the gap"))
        self.assertNotEqual(run.main(["verdict", str(path), "maybe", "x"]), 0)


class JudgeTest(unittest.TestCase):
    def test_labels_hide_arms(self):
        prompt = judge.build_prompt("1. Fixes it.", [("R2", "reply two"), ("R1", "reply one")])
        for leak in ("gemini", "claude", "Arm A", "arm B", "variant", "baseline"):
            self.assertNotIn(leak, prompt)
        self.assertIn("## R1", prompt)
        self.assertIn("1. Fixes it.", prompt)

    def test_compliance(self):
        verdict = {"runs": [{"label": "R1", "criteria": [{"name": "a", "pass": True, "note": ""},
                                                         {"name": "b", "pass": False, "note": ""}]}]}
        self.assertEqual(judge.compliance(verdict, "R1"), 0.5)
        self.assertIsNone(judge.compliance(verdict, "R2"))

    def test_parse_output(self):
        ok = json.dumps({"status": "SUCCESS", "structured_output": {"runs": []}})
        self.assertEqual(judge.parse_output(ok), ({"runs": []}, None))
        self.assertIsNotNone(judge.parse_output("not json")[1])
        self.assertIsNotNone(judge.parse_output(json.dumps({"status": "SUCCESS"}))[1])


if __name__ == "__main__":
    unittest.main()
