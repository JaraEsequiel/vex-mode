import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import vendor


def setup():
    up = Path(tempfile.mkdtemp(prefix="up-"))
    src = up / "pstack/skills/poteto-mode/worker.md"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"rules\r\nwith CRLF and trailing space \n")
    repo = Path(tempfile.mkdtemp(prefix="repo-"))
    (repo / "vendor.lock").write_text(json.dumps({"upstream": {}, "files": [], "original": []}))
    return up, src, repo


class VendorTest(unittest.TestCase):
    def test_copies_bytes_identically(self):
        up, src, repo = setup()
        dest = repo / "skills/vex-mode/worker.md"
        vendor.vendor(up, "pstack/skills/poteto-mode/worker.md", dest, repo)
        self.assertEqual(dest.read_bytes(), src.read_bytes())

    def test_upserts_lock_entry(self):
        up, src, repo = setup()
        dest = repo / "skills/vex-mode/worker.md"
        vendor.vendor(up, "pstack/skills/poteto-mode/worker.md", dest, repo)
        vendor.vendor(up, "pstack/skills/poteto-mode/worker.md", dest, repo)
        files = json.loads((repo / "vendor.lock").read_text())["files"]
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["path"], "skills/vex-mode/worker.md")
        self.assertEqual(files[0]["upstream_path"], "pstack/skills/poteto-mode/worker.md")
        self.assertEqual(files[0]["upstream_sha256"], hashlib.sha256(src.read_bytes()).hexdigest())
        self.assertEqual(files[0]["pending_refs"], [])


    def test_records_upstream_commit_and_keeps_refs(self):
        import subprocess
        up, src, repo = setup()
        env = dict(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        import os
        for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "a"]):
            subprocess.run(["git", "-C", str(up), *args], check=True, capture_output=True, env=dict(os.environ, **env))
        head = subprocess.run(["git", "-C", str(up), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        dest = repo / "skills/vex-mode/worker.md"
        vendor.vendor(up, "pstack/skills/poteto-mode/worker.md", dest, repo)
        lock = json.loads((repo / "vendor.lock").read_text())
        lock["files"][0].update(adapted=True, removed_refs=["arena"], pending_refs=["tdd"])
        (repo / "vendor.lock").write_text(json.dumps(lock))
        vendor.vendor(up, "pstack/skills/poteto-mode/worker.md", dest, repo)
        item = json.loads((repo / "vendor.lock").read_text())["files"][0]
        self.assertEqual(item["upstream_commit"], head)
        self.assertEqual(item["removed_refs"], ["arena"])
        self.assertEqual(item["pending_refs"], ["tdd"])
        self.assertNotIn("adapted", item)  # a fresh copy is verbatim until the adapt commit


if __name__ == "__main__":
    unittest.main()
