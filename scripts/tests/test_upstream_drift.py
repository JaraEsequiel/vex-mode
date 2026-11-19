import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import upstream_drift as ud

ENV = dict(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")


def git(path: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True,
                          env=dict(os.environ, **ENV)).stdout.strip()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class DriftTest(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp(prefix="drift-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.up, self.repo = tmp / "upstream", tmp / "repo"
        files = {"pstack/skills/a/SKILL.md": "a v1\n", "pstack/skills/b/SKILL.md": "b v1\nline\n",
                 "pstack/skills/c/SKILL.md": "c v1\n", "pstack/skills/d/SKILL.md": "d v1\n"}
        for rel, text in files.items():
            (self.up / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.up / rel).write_text(text)
        git(self.up, "init", "-q")
        git(self.up, "add", "-A")
        git(self.up, "commit", "-qm", "v1")
        self.v1 = git(self.up, "rev-parse", "HEAD")
        entries = []
        for name, adapted in (("a", False), ("b", True), ("c", False), ("d", False)):
            up_path = f"pstack/skills/{name}/SKILL.md"
            local = self.repo / f"skills/{name}/SKILL.md"
            local.parent.mkdir(parents=True, exist_ok=True)
            data = (self.up / up_path).read_bytes()
            local.write_bytes(data + (b"our adaptation\n" if adapted else b""))
            e = {"path": f"skills/{name}/SKILL.md", "upstream_path": up_path, "upstream_sha256": sha(data),
                 "pending_refs": [], "upstream_commit": self.v1}
            if adapted:
                e["adapted"] = True
            entries.append(e)
        (self.repo / "vendor.lock").write_text(json.dumps(
            {"upstream": {"repo": "https://example.invalid/plugins", "commit": self.v1}, "files": entries, "original": []}))
        (self.up / "pstack/skills/a/SKILL.md").write_text("a v2\n")
        (self.up / "pstack/skills/b/SKILL.md").write_text("b v2\nline\n")
        (self.up / "pstack/skills/c/SKILL.md").unlink()
        git(self.up, "add", "-A")
        git(self.up, "commit", "-qm", "v2")
        self.v2 = git(self.up, "rev-parse", "HEAD")

    def by_path(self):
        return {e["path"]: e for e in ud.report(self.repo, self.up)}

    def test_same_changed_deleted(self):
        r = self.by_path()
        self.assertEqual(r["skills/a/SKILL.md"]["status"], "changed")
        self.assertEqual(r["skills/b/SKILL.md"]["status"], "changed")
        self.assertEqual(r["skills/c/SKILL.md"]["status"], "deleted")
        self.assertEqual(r["skills/d/SKILL.md"]["status"], "same")

    def test_adapted_change_shows_diff_not_revendor(self):
        text = ud.render(ud.report(self.repo, self.up), self.v2)
        b = text.split("skills/b/SKILL.md", 1)[1].split("###", 1)[0]
        self.assertIn("-b v1", b)
        self.assertIn("+b v2", b)
        self.assertIn("re-apply", b)
        self.assertNotIn("vendor.py", b)

    def test_adapted_change_lists_our_local_additions(self):
        lock = json.loads((self.repo / "vendor.lock").read_text())
        for e in lock["files"]:
            if e["path"] == "skills/b/SKILL.md":
                e["local_additions"] = ["Keep the public contract (docs/decisions/x.md)"]
        (self.repo / "vendor.lock").write_text(json.dumps(lock))
        text = ud.render(ud.report(self.repo, self.up), self.v2)
        b = text.split("skills/b/SKILL.md", 1)[1].split("###", 1)[0]
        self.assertIn("Keep the public contract", b)
        self.assertIn("keep", b.lower())

    def test_unadapted_change_says_revendor(self):
        text = ud.render(ud.report(self.repo, self.up), self.v2)
        a = text.split("skills/a/SKILL.md", 1)[1].split("###", 1)[0]
        self.assertIn("scripts/vendor.py", a)

    def test_deleted_upstream_file(self):
        text = ud.render(ud.report(self.repo, self.up), self.v2)
        self.assertIn("deleted upstream", text)

    def test_accept_updates_hash_and_commit(self):
        (self.repo / "skills/a/SKILL.md").write_text("a v2\n")
        ud.accept(self.repo, self.up, "skills/a/SKILL.md")
        e = {x["path"]: x for x in json.loads((self.repo / "vendor.lock").read_text())["files"]}["skills/a/SKILL.md"]
        self.assertEqual(e["upstream_commit"], self.v2)
        self.assertEqual(e["upstream_sha256"], sha(b"a v2\n"))
        self.assertEqual(self.by_path()["skills/a/SKILL.md"]["status"], "same")
        ud.accept(self.repo, self.up, "skills/b/SKILL.md")  # adapted: reconciled by hand, any content
        self.assertEqual(self.by_path()["skills/b/SKILL.md"]["status"], "same")

    def test_accept_refuses_unadapted_mismatch(self):
        with self.assertRaises(ud.DriftError):
            ud.accept(self.repo, self.up, "skills/a/SKILL.md")  # local still v1, upstream v2

    def test_fail_exit_code(self):
        self.assertEqual(ud.main(["--upstream", str(self.up), "--repo", str(self.repo)]), 0)
        self.assertEqual(ud.main(["--upstream", str(self.up), "--repo", str(self.repo), "--fail"]), 1)


class IssueTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="drift-gh-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.log, self.state = self.tmp / "gh.log", self.tmp / "open.json"
        fake = self.tmp / "gh.py"
        fake.write_text(
            "import json,sys\n"
            f"open({str(self.log)!r},'a').write(json.dumps(sys.argv[1:])+'\\n')\n"
            "if sys.argv[1:3]==['issue','list']:\n"
            f"    print(open({str(self.state)!r}).read())\n")
        self.state.write_text("[]")
        os.environ["VEX_GH"] = f"{sys.executable} {fake}"
        self.addCleanup(os.environ.pop, "VEX_GH", None)

    def calls(self):
        return [json.loads(l) for l in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_issue_created_when_drift(self):
        ud.sync_issue("## drift report", drift=True)
        creates = [c for c in self.calls() if c[:2] == ["issue", "create"]]
        self.assertEqual(len(creates), 1)
        self.assertIn(ud.ISSUE_TITLE, creates[0])

    def test_issue_updated_not_duplicated(self):
        self.state.write_text(json.dumps([{"number": 7, "title": ud.ISSUE_TITLE}]))
        ud.sync_issue("## new report", drift=True)
        self.assertFalse([c for c in self.calls() if c[:2] == ["issue", "create"]])
        self.assertTrue([c for c in self.calls() if c[:3] == ["issue", "edit", "7"]])

    def test_issue_closed_when_clean(self):
        self.state.write_text(json.dumps([{"number": 7, "title": ud.ISSUE_TITLE}]))
        ud.sync_issue("no drift", drift=False)
        self.assertTrue([c for c in self.calls() if c[:3] == ["issue", "close", "7"]])

    def test_no_issue_and_no_drift_does_nothing(self):
        ud.sync_issue("no drift", drift=False)
        self.assertEqual([c for c in self.calls() if c[:2] != ["issue", "list"]], [])


if __name__ == "__main__":
    unittest.main()
