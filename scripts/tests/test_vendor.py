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


if __name__ == "__main__":
    unittest.main()
