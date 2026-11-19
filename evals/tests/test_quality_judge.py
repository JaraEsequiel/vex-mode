import json
import os
import random
import re
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from harness import quality_judge as qj  # noqa: E402
from test_judges import FakeAPI, openai_reply  # noqa: E402

CFG = {"provider": "openai", "model": "gpt-6.2-sol", "effort": "medium"}


def labels_in(prompt: str) -> list[str]:
    return re.findall(r"^## (Q\d+)$", prompt, re.M)


def all_vote(vote: str):
    def handler(req):
        prompt = req["body"]["input"][0]["content"]
        runs = [{"label": l, "vote": vote, "note": "seen"} for l in labels_in(prompt)]
        return 200, {}, openai_reply(json.dumps({"runs": runs}))
    return handler


class QualityJudgeTest(unittest.TestCase):
    def setUp(self):
        self.api = FakeAPI()
        self.addCleanup(self.api.close)
        tmp = Path(tempfile.mkdtemp(prefix="qj-"))
        self.run_dir = tmp / "run"
        env = {"VEX_OPENAI_BASE_URL": self.api.url, "OPENAI_API_KEY": "sk-test", "VEX_SECRETS": str(tmp / "none")}
        old = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
                                 for k, v in old.items()])
        self.patches = {4: "diff --git a/x.py b/x.py\n+four\n", 9: "diff --git a/x.py b/x.py\n+nine\n"}

    def grade(self):
        return qj.grade(self.patches, "### x.py\n\n```\nold\n```\n", CFG, self.run_dir, random.Random(3))

    def prompts(self):
        return [r["body"]["input"][0]["content"] for r in self.api.requests]

    def test_tally(self):
        self.assertEqual(qj.tally(["pass", "pass", "unknown"]), 1.0)
        self.assertEqual(qj.tally(["fail", "fail", "pass"]), 0.0)
        for votes in (["pass", "unknown", "unknown"], ["pass", "fail", "unknown"], [None, None, None]):
            self.assertIsNone(qj.tally(votes), votes)

    def test_grade_one_call_per_vote_and_dimension(self):
        self.api.handler = all_vote("pass")
        values, errors, usage = self.grade()
        self.assertEqual(errors, [])
        self.assertEqual(values, {s: {f"judge_{d}": 1.0 for d in qj.DIMENSIONS} for s in self.patches})
        self.assertEqual(len(self.api.requests), 3 * len(qj.DIMENSIONS))
        for prompt in self.prompts():
            self.assertEqual(sum(q in prompt for q in qj.DIMENSIONS.values()), 1)
        self.assertEqual(usage["input"], 100 * 9)

    def test_labels_are_blind_and_reshuffled(self):
        self.api.handler = all_vote("fail")
        values, _, _ = self.grade()
        self.assertEqual(values[4]["judge_reuse"], 0.0)
        orders = set()
        for prompt in self.prompts():
            self.assertEqual(sorted(labels_in(prompt)), ["Q1", "Q2"])
            self.assertNotRegex(prompt, r"\b(slot|arm)\b")
            orders.add(prompt.index("+four") < prompt.index("+nine"))
        self.assertEqual(orders, {True, False})

    def test_bad_vote_is_discarded_and_reported(self):
        calls = []

        def handler(req):
            calls.append(1)
            prompt = req["body"]["input"][0]["content"]
            labels = labels_in(prompt)
            if len(calls) == 1:
                labels = labels[:1]
            return 200, {}, openai_reply(json.dumps({"runs": [{"label": l, "vote": "pass", "note": "n"} for l in labels]}))

        self.api.handler = handler
        values, errors, _ = self.grade()
        self.assertTrue(all(v == 1.0 for run in values.values() for v in run.values()))
        self.assertEqual(len(errors), 1)
        self.assertRegex(errors[0], r"^judge_\w+ vote 1: ")

    def test_failed_call_is_an_error_not_a_crash(self):
        self.api.handler = lambda req: (400, {}, {"error": {"message": "bad request"}})
        values, errors, _ = self.grade()
        self.assertTrue(all(v is None for run in values.values() for v in run.values()))
        self.assertEqual(len(errors), 9)
        self.assertTrue((self.run_dir / "quality-judge").is_dir())


if __name__ == "__main__":
    unittest.main()
