import json
import re
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import run
from harness import judge, judges
from test_judges import FakeAPI, openai_reply

sys.path.insert(0, str(HERE.parents[1] / "checks"))
from _util import QUALITY_ALL  # noqa: E402

CASE = {
    "runs": 2,
    "candidate_model": "gemini-4-neon-medium",
    "upgrade_model": "gemini-4-neon-high",
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
            "FAKE_PARENT": str(os.getpid()),
            "VEX_JUDGE_PROVIDER": "agy",
            "VEX_JUDGE_MODEL": "claude-opus-5-5-high",
            "VEX_SECRETS": str(tmp / "no-secrets.env"),
        }
        self.old = {k: os.environ.get(k) for k in [*self.env, "FAKE_PEEK", "OPENAI_API_KEY", "VEX_OPENAI_BASE_URL"]}
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

    def test_large_judge_prompt_goes_through_a_file(self):
        os.environ["FAKE_AGY_MODE"] = "big"
        result = json.loads(self.run_eval().read_text())
        self.assertIsNone(result["judge"]["error"])
        self.assertGreater(len((Path(result["run_dir"]) / "judge-prompt.md").read_text().encode()), judges.INLINE_MAX)
        self.assertTrue((Path(result["run_dir"]) / "review/judge-prompt.md").is_file())  # agy -p reads only its workspace
        sizes = [int(n) for n in (self.home / "judge-args.log").read_text().split()]
        self.assertTrue(all(n < 2000 for n in sizes), sizes)

    def test_judge_launch_failure_still_writes_result(self):
        real = judges.subprocess.run

        def no_judge(cmd, *a, **kw):
            if "--json-schema" in cmd:
                raise OSError(7, "Argument list too long", "agy")
            return real(cmd, *a, **kw)

        judges.subprocess.run = no_judge
        try:
            result = json.loads(self.run_eval().read_text())
        finally:
            judges.subprocess.run = real
        self.assertIn("could not start the judge", result["judge"]["error"])
        self.assertTrue(all(r["outcome"] == 1 for arm in "ABC" for r in result["arms"][arm]["runs"]))

    def openai_judge(self):
        api = FakeAPI()
        self.addCleanup(api.close)

        def grade(req):
            labels = re.findall(r"^## (R\d+)$", req["body"]["input"][0]["content"], re.M)
            runs = [{"label": l, "criteria": [{"name": "c1", "pass": True, "note": "ok"}]} for l in labels]
            return 200, {}, openai_reply(json.dumps({"runs": runs}))
        api.handler = grade
        os.environ.update({"VEX_JUDGE_PROVIDER": "openai", "VEX_JUDGE_MODEL": "gpt-6.2-sol",
                           "VEX_OPENAI_BASE_URL": api.url, "OPENAI_API_KEY": "sk-secret-123"})
        return api

    def test_result_records_judge_provider_and_usage(self):
        self.openai_judge()
        result = json.loads(self.run_eval().read_text())
        self.assertIsNone(result["judge"]["error"])
        self.assertEqual((result["judge"]["provider"], result["judge"]["model"]), ("openai", "gpt-6.2-sol"))
        self.assertEqual(result["judge"]["usage"]["input"], 100)
        self.assertTrue(all(r["compliance"] == 1.0 for arm in "ABC" for r in result["arms"][arm]["runs"]))

    def test_key_never_written(self):
        self.openai_judge()
        path = self.run_eval()
        run_dir = Path(json.loads(path.read_text())["run_dir"])
        leaks = [p for p in [path, *run_dir.rglob("*")] if p.is_file() and b"sk-secret-123" in p.read_bytes()]
        self.assertEqual(leaks, [])

    def test_candidates_never_see_api_keys(self):
        self.openai_judge()
        os.environ["FAKE_AGY_MODE"] = "env"
        path = self.run_eval()
        run_dir = Path(json.loads(path.read_text())["run_dir"])
        leaks = [p for p in [path, *run_dir.rglob("*")] if p.is_file() and b"sk-secret-123" in p.read_bytes()]
        self.assertEqual(leaks, [])

    def test_rejudge_refuses_a_same_family_judge(self):
        path = self.run_eval()
        os.environ.update({"VEX_JUDGE_PROVIDER": "agy", "VEX_JUDGE_MODEL": "gemini-4-argon-high"})
        with self.assertRaises(run.EvalError) as ctx:
            run.rejudge(path)
        self.assertIn("family", str(ctx.exception))

    def test_reading_the_secrets_file_invalidates_a_run(self):
        os.environ["FAKE_AGY_MODE"] = "peek"
        os.environ["FAKE_PEEK"] = os.environ["VEX_SECRETS"]
        result = json.loads(self.run_eval().read_text())
        self.assertTrue(all(r["invalid"] for arm in "ABC" for r in result["arms"][arm]["runs"]))

    def test_missing_key_fails_before_runs(self):
        os.environ.update({"VEX_JUDGE_PROVIDER": "openai", "VEX_JUDGE_MODEL": "gpt-6.2-sol"})
        os.environ.pop("OPENAI_API_KEY", None)
        with self.assertRaises(run.EvalError) as ctx:
            self.run_eval()
        self.assertIn("OPENAI_API_KEY", str(ctx.exception))
        self.assertFalse((self.home / "candidates").exists())
        self.assertEqual(self.installed(), "original install")

    def test_judge_sees_committed_changes(self):
        os.environ["FAKE_AGY_MODE"] = "commit"
        result = json.loads(self.run_eval().read_text())
        prompt = (Path(result["run_dir"]) / "judge-prompt.md").read_text()
        self.assertIn("+fixed", prompt)
        self.assertIn("-broken", prompt)
        self.assertNotIn("__pycache__", prompt)

    def test_rejudge_rebuilds_from_run_dir(self):
        path = self.run_eval()
        before = json.loads(path.read_text())
        (Path(before["run_dir"]) / "judge-prompt.md").unlink()
        os.environ["FAKE_AGY_MODE"] = "badjudge"
        self.assertEqual(run.main(["rejudge", str(path)]), 0)
        after = json.loads(path.read_text())
        self.assertTrue((Path(after["run_dir"]) / "judge-prompt.md").is_file())
        self.assertIn("R6", after["judge"]["error"])
        self.assertEqual(after["arms"]["A"]["tree_sha256"], before["arms"]["A"]["tree_sha256"])
        self.assertEqual([r["outcome"] for r in after["arms"]["B"]["runs"]], [r["outcome"] for r in before["arms"]["B"]["runs"]])

    def test_judge_too_few_criteria_sets_error(self):
        (self.repo / "evals/x/cases/c1/rubric.md").write_text("1. Fixes it.\n2. Shows proof.\n")
        git(self.repo, "commit", "-qam", "two criteria")
        result = json.loads(self.run_eval().read_text())
        self.assertIsNotNone(result["judge"]["error"])

    def test_unfinished_run_cost_is_not_zero(self):
        os.environ["FAKE_AGY_MODE"] = "crash"
        result = json.loads(self.run_eval().read_text())
        bad = [r for a in "ABC" for r in result["arms"][a]["runs"] if r["status"] == "UNFINISHED"][0]
        self.assertGreater(bad["duration_s"], 0)

    def test_sigterm_still_restores_plugin(self):
        os.environ["FAKE_AGY_MODE"] = "sigterm"
        with self.assertRaises(BaseException):
            self.run_eval()
        self.assertEqual(self.installed(), "original install")
        self.assertFalse((self.cache / "vex-mode/restore-pending").exists())

    def test_pending_restore_blocks_next_run(self):
        backup = self.cache / "vex-mode/runs/old/installed-backup"
        backup.mkdir(parents=True)
        (backup / "plugin.json").write_text("{}")
        (backup / "skills/x").mkdir(parents=True)
        (backup / "skills/x/SKILL.md").write_text("from backup")
        (self.cache / "vex-mode/restore-pending").write_text(str(backup))
        with self.assertRaises(run.EvalError):
            self.run_eval()
        self.assertEqual(run.main(["restore"]), 0)
        self.assertEqual(self.installed(), "from backup")
        self.assertFalse((self.cache / "vex-mode/restore-pending").exists())

    def test_workdirs_are_private_and_removed(self):
        os.environ["FAKE_AGY_MODE"] = "ls"
        result = json.loads(self.run_eval().read_text())
        listings = (self.home / "ls.log").read_text().splitlines()
        self.assertTrue(listings)
        self.assertTrue(all(line == "ledger-app" for line in listings), listings)
        self.assertEqual(list((self.cache / "vex-work").glob("*")), [])
        self.assertTrue(list((Path(result["run_dir"]) / "diffs").glob("*.diff")))

    def test_rejudge_uses_saved_diffs(self):
        path = self.run_eval()
        self.assertEqual(run.main(["rejudge", str(path)]), 0)
        prompt = (Path(json.loads(path.read_text())["run_dir"]) / "judge-prompt.md").read_text()
        self.assertIn("+fixed", prompt)

    def test_result_name_has_case_and_never_overwrites(self):
        path = self.run_eval()
        self.assertIn("-c1-", path.name)
        with self.assertRaises(run.EvalError):
            self.run_eval()

    def test_refuses_dirty_variant(self):
        (self.repo / "skills/x/SKILL.md").write_text("dirty")
        with self.assertRaises(run.EvalError):
            self.run_eval()

    def enable_quality(self):
        case = dict(CASE, quality=True)
        (self.repo / "evals/x/cases/c1/case.json").write_text(json.dumps(case))
        git(self.repo, "commit", "-qam", "quality on")

    def passing(self, result):
        return [r for a in "ABC" for r in result["arms"][a]["runs"] if r["outcome"] == 1]

    def test_quality_only_on_passing_runs(self):
        self.enable_quality()
        os.environ["FAKE_AGY_MODE"] = "failB"
        result = json.loads(self.run_eval().read_text())
        self.assertTrue(all("quality" not in r for r in result["arms"]["B"]["runs"]))
        self.assertTrue(all("quality" in r for a in "AC" for r in result["arms"][a]["runs"]))
        self.assertEqual(result["signals"]["B_vs_A"]["prod_lines"], "few")
        self.assertIsNone(result["metrics"]["B"]["prod_lines"])

    def test_quality_measures_recorded(self):
        self.enable_quality()
        result = json.loads(self.run_eval().read_text())
        self.assertTrue(result["quality"]["enabled"])
        self.assertEqual(result["quality"]["errors"], [])
        for r in self.passing(result):
            self.assertEqual(set(r["quality"]), set(QUALITY_ALL))
            self.assertEqual(r["quality"]["prod_lines"], 2)
            self.assertEqual(r["quality"]["judge_reuse"], 1.0)
        self.assertEqual(result["metrics"]["A"]["prod_lines"]["mean"], 2.0)
        self.assertEqual(result["signals"]["B_vs_A"]["prod_lines"], "noise")
        self.assertEqual(run.main(["verdict", str(self.repo / "evals/x/results" / next(
            p.name for p in (self.repo / "evals/x/results").iterdir())), "promote", "same quality"]), 0)

    def test_quality_judge_error_blocks_promote(self):
        self.enable_quality()
        api = self.openai_judge()
        compliance = api.handler

        def handler(req):
            if "## Q1" in req["body"]["input"][0]["content"]:
                return 400, {}, {"error": {"message": "bad request"}}
            return compliance(req)
        api.handler = handler
        path = self.run_eval()
        result = json.loads(path.read_text())
        self.assertIsNone(result["judge"]["error"])
        self.assertEqual(len(result["quality"]["errors"]), 9)
        self.assertEqual(result["signals"]["B_vs_A"]["judge_reuse"], "error")
        with self.assertRaises(run.EvalError) as ctx:
            run.set_verdict(path, "promote", "looks fine")
        self.assertIn("judge_reuse error", str(ctx.exception))
        run.set_verdict(path, "reject", "quality judge failed")

    def test_promote_refused_when_outcome_worse(self):
        path = self.run_eval()
        result = json.loads(path.read_text())
        result["signals"]["B_vs_A"]["outcome"] = "worse"
        path.write_text(json.dumps(result))
        with self.assertRaises(run.EvalError) as ctx:
            run.set_verdict(path, "promote", "x")
        self.assertIn("outcome worse", str(ctx.exception))
        run.set_verdict(path, "reject", "x")
        self.assertEqual(json.loads(path.read_text())["verdict"], "reject")

    def test_case_without_quality_has_none(self):
        result = json.loads(self.run_eval().read_text())
        self.assertFalse(result["quality"]["enabled"])
        self.assertTrue(all("quality" not in r for a in "ABC" for r in result["arms"][a]["runs"]))
        self.assertNotIn("prod_lines", result["signals"]["B_vs_A"])

    def test_saved_diff_is_never_truncated(self):
        os.environ["FAKE_AGY_MODE"] = "big"
        result = json.loads(self.run_eval().read_text())
        run_dir = Path(result["run_dir"])
        diff = next((run_dir / "diffs").glob("*.diff")).read_text()
        self.assertGreater(len(diff), run.DIFF_LIMIT)
        self.assertNotIn("[diff truncated]", diff)
        self.assertIn("[diff truncated]", (run_dir / "judge-prompt.md").read_text())

    def test_rejudge_recomputes_quality(self):
        self.enable_quality()
        path = self.run_eval()
        before = json.loads(path.read_text())
        self.assertEqual(run.main(["rejudge", str(path)]), 0)
        after = json.loads(path.read_text())
        self.assertEqual([r.get("quality") for r in self.passing(after)], [r.get("quality") for r in self.passing(before)])
        self.assertTrue(after["quality"]["enabled"])

    def test_diff_keeps_trailing_context_and_ignores_user_prefixes(self):
        work = self.home / "w"
        write(work, {"a.py": "x = 1\ny = 2\n\n\n"})
        for args in (["init", "-q"], ["config", "diff.mnemonicPrefix", "true"], ["add", "-A"], ["commit", "-qm", "i"]):
            git(work, *args)
        (work / "a.py").write_text("x = 3\ny = 2\n\n\n")
        diff = run._diff(work)
        self.assertTrue(diff.startswith("diff --git a/a.py b/a.py"), diff[:40])
        self.assertTrue(diff.endswith(" \n"), repr(diff[-20:]))

    def test_quality_survives_unreadable_project_file(self):
        case = self.repo / "evals/x/cases/c1"
        (case / "project/data.bin").write_bytes(b"\xff\xfe\x00binary")
        run_dir = self.cache / "qrun"
        (run_dir / "diffs").mkdir(parents=True)
        (run_dir / "diffs/1.diff").write_text("diff --git a/data.bin b/data.bin\nBinary files differ\n")
        records = {"A": {"runs": [{"slot": 1, "invalid": None, "outcome": 1}]}}
        real = run.quality_judge.grade
        run.quality_judge.grade = lambda patches, context, *a: ({s: {} for s in patches}, [], {})
        try:
            rec = run._quality(records, case, {"quality": True}, "fix it", {}, run_dir, __import__("random").Random(1))
        finally:
            run.quality_judge.grade = real
        self.assertTrue(rec["errors"])
        self.assertTrue(records["A"]["runs"][0]["quality_errors"])

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

    def test_wrong_criterion_count_is_an_error(self):
        verdict = {"runs": [{"label": "R1", "criteria": [{"name": "a", "pass": True, "note": ""}]}]}
        self.assertIsNotNone(judge.check_verdict(verdict, ["R1"], 4))
        full = {"runs": [{"label": "R1", "criteria": [{"name": str(i), "pass": True, "note": ""} for i in range(4)]}]}
        self.assertIsNone(judge.check_verdict(full, ["R1"], 4))
        dup = {"runs": full["runs"] * 2}
        self.assertIsNotNone(judge.check_verdict(dup, ["R1"], 4))

    def test_parse_output_never_crashes(self):
        for out in ("null", "[]", json.dumps({"structured_output": {"runs": ["x"]}}), json.dumps({"structured_output": None})):
            verdict, error = judge.parse_output(out)
            self.assertIsNotNone(error, out)

    def test_rubric_criteria_count(self):
        self.assertEqual(judge.criteria_count("1. a\n2. b\n\n3. c\n"), 3)

    def test_parse_output(self):
        ok = json.dumps({"status": "SUCCESS", "structured_output": {"runs": []}})
        self.assertEqual(judge.parse_output(ok), ({"runs": []}, None))
        self.assertIsNotNone(judge.parse_output("not json")[1])
        self.assertIsNotNone(judge.parse_output(json.dumps({"status": "SUCCESS"}))[1])


if __name__ == "__main__":
    unittest.main()


CC_CASE = {**CASE, "harness": "claude-code", "candidate_model": "claude-sonnet-5-5", "upgrade_model": "claude-opus-5-5"}


class ClaudeCodeRunTest(RunTest):
    """The same harness with `"harness": "claude-code"`: per-arm --plugin-dir, nothing installed."""

    def setUp(self):
        super().setUp()
        write(self.repo, {"evals/x/cases/c1/case.json": json.dumps(CC_CASE),
                          "adapters/claude-code.md": "adapter\n"})
        git(self.repo, "checkout", "-q", "main")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "claude code case")
        git(self.repo, "checkout", "-q", "feature")
        git(self.repo, "rebase", "-q", "main")
        os.environ["VEX_CLAUDE"] = f"{sys.executable} {HERE / 'fake_claude.py'}"
        os.environ["VEX_JUDGE_MODEL"] = "gpt-6.2-sol"
        self.old.setdefault("VEX_CLAUDE", None)
        self.old.setdefault("FAKE_CLAUDE_MODE", None)

    def calls(self) -> list[list[str]]:
        return [json.loads(l) for l in (self.home / "claude-args.log").read_text().splitlines()]

    def test_end_to_end_with_fake_claude(self):
        result = json.loads(self.run_eval().read_text())
        self.assertEqual(result["harness"], "claude-code")
        self.assertEqual(result["arms"]["A"]["model"], "claude-sonnet-5-5")
        self.assertEqual(result["arms"]["C"]["model"], "claude-opus-5-5")
        for arm in "ABC":
            self.assertEqual(result["metrics"][arm]["outcome"]["mean"], 1.0)
            self.assertEqual(result["arms"][arm]["runs"][0]["cost_usd"], 0.05)
        self.assertNotEqual(result["arms"]["A"]["tree_sha256"], result["arms"]["B"]["tree_sha256"])
        self.assertEqual(self.installed(), "original install")
        self.assertFalse((self.home / "installs").exists())

    def test_each_arm_loads_its_own_build_in_isolation(self):
        self.run_eval()
        trees = set()
        for argv in self.calls():
            self.assertEqual(argv[argv.index("--setting-sources") + 1], "project")
            self.assertEqual(argv[-2:][0], "-p")
            tree = Path(argv[argv.index("--plugin-dir") + 1])
            self.assertEqual(argv[argv.index("--add-dir") + 1], str(tree))
            self.assertTrue((tree / ".claude-plugin/plugin.json").is_file())
            trees.add(tree)
        self.assertEqual(len(trees), 3)
        texts = {(t / "skills/x/SKILL.md").read_text() for t in trees}
        self.assertEqual(texts, {"v1", "v2"})

    def test_subagent_search_of_the_rubric_invalidates_run(self):
        os.environ["FAKE_CLAUDE_MODE"] = "peek"
        os.environ["FAKE_PEEK"] = str(self.repo / "evals/x/cases/c1")
        result = json.loads(self.run_eval().read_text())
        for arm in "ABC":
            for r in result["arms"][arm]["runs"]:
                self.assertIsNotNone(r["invalid"])
                self.assertEqual(r["outcome"], 0)

    def test_crashed_run_is_invalid(self):
        os.environ["FAKE_CLAUDE_MODE"] = "crash"
        result = json.loads(self.run_eval().read_text())
        self.assertIn("UNFINISHED", result["arms"]["A"]["runs"][0]["invalid"])

    def test_pending_agy_restore_does_not_block(self):
        run._marker().parent.mkdir(parents=True, exist_ok=True)
        run._marker().write_text("-")
        self.addCleanup(lambda: run._marker().unlink(missing_ok=True))
        self.assertTrue(self.run_eval().exists())


# The agy-only tests of RunTest do not apply to the Claude Code subclass.
for _name in [n for n in dir(RunTest) if n.startswith("test_")]:
    if _name not in vars(ClaudeCodeRunTest):
        setattr(ClaudeCodeRunTest, _name, None)
