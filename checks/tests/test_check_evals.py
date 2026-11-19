import json
import os
import subprocess
import unittest
from pathlib import Path

from _helpers import make_repo

import check_evals
from _util import QUALITY_ALL, banned_hits, model_family, skill_tree_sha256

CASE_JSON = {
    "runs": 3,
    "candidate_model": "gemini-4-neon-medium",
    "upgrade_model": "gemini-4-neon-high",
    "workdir": "ledger-app",
    "timeout_s": 900,
}


def case_files(skill="x", case="c1", **over):
    cfg = dict(CASE_JSON, **over.pop("case_json", {}))
    base = f"evals/{skill}/cases/{case}/"
    files = {
        base + "prompt.md": "The total is off by a cent, please fix it.",
        base + "rubric.md": "1. Reproduces first.",
        base + "check.py": "import sys\n",
        base + "case.json": json.dumps(cfg),
        base + "project/app.py": "def total(xs):\n    return sum(xs)\n",
        "evals/judge.json": json.dumps(over.pop("judge", {"provider": "openai", "model": "gpt-6.2-sol", "effort": "medium"})),
    }
    files.update(over.pop("extra", {}))
    for k in over.pop("drop", []):
        files.pop(base + k)
    return files


def stats(v=1.0):
    return {"mean": v, "min": v, "max": v, "spread": 0.0}


def eval_result(skill="x", sha="a" * 64, **over):
    arm = {"model": "m", "plugin_ref": "r", "tree_sha256": sha, "runs": []}
    metrics = {"compliance": stats(), "outcome": stats(), "tokens": stats(), "duration_s": stats()}
    r = {
        "kind": "eval", "skill": skill, "tree_sha256": sha, "date": "2026-11-18",
        "case": "c1", "run_dir": "/tmp/r",
        "arms": {"A": dict(arm), "B": dict(arm), "C": dict(arm)},
        "judge": {"model": "claude-opus-5-5-high", "error": None},
        "metrics": {"A": dict(metrics), "B": dict(metrics), "C": dict(metrics)},
        "signals": {"B_vs_A": {}, "C_vs_A": {}},
        "verdict": "promote", "synthesis": "B reads the playbook; outcome same.",
    }
    r.update(over)
    return r


def git(root: Path, *args: str) -> str:
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True, env=env).stdout


def git_repo(files: dict) -> Path:
    root = make_repo(files)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    return root


class UtilTest(unittest.TestCase):
    def test_tree_hash_changes_with_any_file(self):
        root = make_repo({"skills/x/SKILL.md": "a", "skills/x/playbooks/p.md": "p"})
        before = skill_tree_sha256(root / "skills/x")
        (root / "skills/x/__pycache__").mkdir()
        (root / "skills/x/__pycache__/x.pyc").write_text("c")
        self.assertEqual(skill_tree_sha256(root / "skills/x"), before)
        (root / "skills/x/playbooks/p.md").write_text("p2")
        self.assertNotEqual(skill_tree_sha256(root / "skills/x"), before)

    def test_banned_hits_catch_inflections_and_camel(self):
        for text in ("tests/", "evaluation", "myJudge", "foo_test"):
            self.assertTrue(banned_hits(text), text)
        for text in ("latest", "contest", "ledger app"):
            self.assertEqual(banned_hits(text), [], text)

    def test_model_family(self):
        self.assertEqual(model_family("claude-opus-5-5-high"), "claude")
        self.assertEqual(model_family("gemini-3.8-flash-low"), "gemini")
        self.assertEqual(model_family("gpt-oss-120b-medium"), "gpt")
        self.assertEqual(model_family("grok-5"), "grok")


class LayoutTest(unittest.TestCase):
    def errors(self, files):
        files.setdefault("skills/x/SKILL.md", "---\nname: x\ndescription: d\n---\n")
        return check_evals.layout_errors(make_repo(files))

    def test_valid_case_has_no_errors(self):
        self.assertEqual(self.errors(case_files()), [])

    def test_case_layout_required(self):
        errors = self.errors(case_files(drop=["check.py"]))
        self.assertTrue(any("evals/x/cases/c1" in e and "check.py" in e for e in errors), errors)

    def test_banned_word_in_prompt_project_or_workdir(self):
        base = "evals/x/cases/c1/"
        self.assertTrue(self.errors(case_files(extra={base + "prompt.md": "Please evaluate the fix."})))
        self.assertTrue(self.errors(case_files(extra={base + "project/test_x.py": "x = 1\n"})))
        self.assertTrue(self.errors(case_files(extra={base + "project/app.py": "SCORE = 1\n"})))
        self.assertTrue(self.errors(case_files(case_json={"workdir": "rubric-app"})))

    def test_case_json_fields(self):
        for bad in ({"runs": 0}, {"workdir": "Bad Name"}, {"timeout_s": "x"}, {"candidate_model": ""}):
            self.assertTrue(self.errors(case_files(case_json=bad)), bad)

    def test_judge_same_family_rejected(self):
        errors = self.errors(case_files(judge={"provider": "agy", "model": "gemini-4-argon-high", "effort": "high"}))
        self.assertTrue(any("family" in e for e in errors), errors)

    def test_judge_lives_in_judge_json_not_in_the_case(self):
        errors = self.errors(case_files(case_json={"judge_model": "claude-opus-5-5-high"}))
        self.assertTrue(any("judge_model" in e and "evals/judge.json" in e for e in errors), errors)
        files = case_files()
        files.pop("evals/judge.json")
        self.assertTrue(any("evals/judge.json" in e for e in self.errors(files)))
        self.assertTrue(any("provider" in e for e in self.errors(case_files(judge={"provider": "x", "model": "m"}))))

    def test_evals_dir_without_skill(self):
        files = case_files(skill="ghost")
        errors = self.errors(files)
        self.assertTrue(any("ghost" in e and "skills/ghost" in e for e in errors), errors)

    def test_harness_and_tests_dirs_are_not_skills(self):
        files = case_files()
        files["evals/harness/__init__.py"] = ""
        files["evals/tests/test_a.py"] = ""
        files["evals/run.py"] = ""
        self.assertEqual(self.errors(files), [])


class ResultTest(unittest.TestCase):
    def errors(self, result, name="r.json"):
        files = {"skills/x/SKILL.md": "s", f"evals/x/results/{name}": json.dumps(result)}
        return check_evals.layout_errors(make_repo(files))

    def test_valid_eval_and_waiver(self):
        self.assertEqual(self.errors(eval_result()), [])
        waiver = {"kind": "waiver", "skill": "x", "tree_sha256": "b" * 64, "date": "2026-11-18", "reason": "vendored only"}
        self.assertEqual(self.errors(waiver), [])

    def test_waiver_needs_reason(self):
        waiver = {"kind": "waiver", "skill": "x", "tree_sha256": "b" * 64, "date": "2026-11-18", "reason": ""}
        self.assertTrue(self.errors(waiver))

    def test_judge_error_without_compliance_is_error(self):
        r = eval_result(judge={"model": "m", "error": "missing label R3"})
        r["metrics"]["B"]["compliance"] = None
        self.assertTrue(self.errors(r))

    def test_result_judge_must_differ_from_candidates(self):
        r = eval_result(judge={"model": "gemini-4-argon-high", "error": None})
        for arm in "ABC":
            r["arms"][arm]["model"] = "gemini-4-neon-medium"
        self.assertTrue(any("family" in e for e in self.errors(r)))

    def test_eval_needs_verdict(self):
        self.assertTrue(any("verdict" in e for e in self.errors(eval_result(verdict=None))))

    def test_bad_kind_skill_or_sha(self):
        self.assertTrue(self.errors(eval_result(kind="maybe")))
        self.assertTrue(self.errors(eval_result(skill="y")))
        self.assertTrue(self.errors(eval_result(tree_sha256="zz")))

    def test_unparseable_result(self):
        files = {"skills/x/SKILL.md": "s", "evals/x/results/r.json": "{nope"}
        self.assertTrue(check_evals.layout_errors(make_repo(files)))


class QualityResultTest(unittest.TestCase):
    def errors(self, result, quality=True):
        files = case_files(case_json={"quality": quality})
        files.update({"skills/x/SKILL.md": "---\nname: x\ndescription: d\n---\n",
                      "evals/x/results/r.json": json.dumps(result)})
        return check_evals.layout_errors(make_repo(files))

    def quality_result(self, **over):
        r = eval_result(date="2026-11-20", quality={"enabled": True, "errors": [], "judge_usage": {}}, **over)
        for arm in "ABC":
            r["metrics"][arm].update({n: stats(0.0) for n in QUALITY_ALL})
        r["signals"]["B_vs_A"].update({n: "noise" for n in QUALITY_ALL})
        return r

    def test_valid_quality_result(self):
        self.assertEqual(self.errors(self.quality_result()), [])

    def test_promote_with_worse_quality_fails(self):
        r = self.quality_result()
        r["signals"]["B_vs_A"]["verbosity"] = "worse"
        self.assertTrue(any("promote refused" in e and "verbosity worse" in e for e in self.errors(r)))
        self.assertEqual(self.errors(dict(r, verdict="reject")), [])

    def test_promote_with_worse_outcome_fails_without_quality(self):
        r = eval_result()
        r["signals"]["B_vs_A"]["outcome"] = "worse"
        self.assertTrue(any("promote refused" in e for e in self.errors(r, quality=False)))

    def test_quality_case_result_needs_quality_from_2026_11_20(self):
        r = eval_result(date="2026-11-20")
        self.assertTrue(any("quality" in e for e in self.errors(r)))
        self.assertEqual(self.errors(eval_result(date="2026-11-19")), [])
        self.assertEqual(self.errors(eval_result(date="2026-11-21"), quality=False), [])

    def test_quality_metric_may_be_null(self):
        r = self.quality_result()
        r["metrics"]["A"]["prod_lines"] = None
        self.assertEqual(self.errors(r), [])

    def test_quality_metric_must_be_present(self):
        r = self.quality_result()
        del r["metrics"]["A"]["prod_lines"]
        self.assertTrue(any("metrics.A.prod_lines" in e for e in self.errors(r)))

    def test_quality_signal_must_be_present(self):
        r = self.quality_result()
        del r["signals"]["B_vs_A"]["judge_reuse"]
        r["verdict"] = "promote"
        self.assertTrue(any("signals.B_vs_A.judge_reuse" in e for e in self.errors(r)))

    def test_case_quality_must_be_bool(self):
        self.assertTrue(any("quality" in e for e in self.errors(eval_result(), quality="yes")))


class PolicyTest(unittest.TestCase):
    def test_changed_skill_requires_matching_result(self):
        root = git_repo({"skills/x/SKILL.md": "v1"})
        git(root, "checkout", "-q", "-b", "feature")
        (root / "skills/x/SKILL.md").write_text("v2")
        git(root, "commit", "-qam", "change x")
        errors = check_evals.policy_errors(root, "main")
        self.assertTrue(any("skills/x" in e for e in errors), errors)
        sha = skill_tree_sha256(root / "skills/x")
        res = root / "evals/x/results/r.json"
        res.parent.mkdir(parents=True)
        res.write_text(json.dumps(eval_result(sha=sha)))
        self.assertEqual(check_evals.policy_errors(root, "main"), [])

    def test_stale_hash_does_not_satisfy(self):
        root = git_repo({"skills/x/SKILL.md": "v1"})
        git(root, "checkout", "-q", "-b", "feature")
        (root / "skills/x/SKILL.md").write_text("v2")
        res = root / "evals/x/results/r.json"
        res.parent.mkdir(parents=True)
        res.write_text(json.dumps(eval_result(sha="c" * 64)))
        self.assertTrue(check_evals.policy_errors(root, "main"))

    def test_new_untracked_skill_counts_as_changed(self):
        root = git_repo({"skills/x/SKILL.md": "v1"})
        (root / "skills/y").mkdir()
        (root / "skills/y/SKILL.md").write_text("new")
        errors = check_evals.policy_errors(root, "main")
        self.assertTrue(any("skills/y" in e for e in errors), errors)

    def test_unchanged_skills_need_nothing(self):
        root = git_repo({"skills/x/SKILL.md": "v1"})
        self.assertEqual(check_evals.policy_errors(root, "main"), [])

    def test_deleted_skill_needs_nothing(self):
        root = git_repo({"skills/x/SKILL.md": "v1", "skills/y/SKILL.md": "y"})
        git(root, "rm", "-rq", "skills/y")
        git(root, "commit", "-qm", "drop y")
        self.assertEqual(check_evals.policy_errors(root, "main~1"), [])

    def test_unrelated_base_is_an_error(self):
        root = git_repo({"skills/x/SKILL.md": "v1"})
        git(root, "checkout", "-q", "--orphan", "other")
        git(root, "commit", "-qm", "orphan", "--allow-empty")
        git(root, "branch", "-q", "orphanbase")
        git(root, "checkout", "-q", "main")
        errors = check_evals.policy_errors(root, "orphanbase")
        self.assertEqual(len(errors), 1, errors)

    def test_plugin_wide_change_counts_for_vex_mode(self):
        root = git_repo({"skills/vex-mode/SKILL.md": "r", "skills/x/SKILL.md": "x", "hooks/activate.py": "a",
                         "rules/AGENTS.md": "r", "plugin.json": "{}"})
        for rel in ("hooks/activate.py", "rules/AGENTS.md", "plugin.json"):
            git(root, "checkout", "-q", "main")
            git(root, "checkout", "-qB", "f-" + rel.replace("/", "-"))
            (root / rel).write_text("changed")
            self.assertEqual(check_evals.changed_skills(root, "main"), {"vex-mode"}, rel)
            git(root, "checkout", "-q", "--", rel)

    def test_unresolvable_base_is_an_error(self):
        root = git_repo({"skills/x/SKILL.md": "v1"})
        old = os.environ.get("VEX_BASE_REF")
        os.environ["VEX_BASE_REF"] = "nope"
        try:
            errors = check_evals.run(root)
        finally:
            if old is None:
                del os.environ["VEX_BASE_REF"]
            else:
                os.environ["VEX_BASE_REF"] = old
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("VEX_BASE_REF", errors[0])


if __name__ == "__main__":
    unittest.main()
