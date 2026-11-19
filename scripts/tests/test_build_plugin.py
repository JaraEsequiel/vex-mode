import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_plugin


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def make_repo(files: dict[str, str]) -> Path:
    repo = Path(tempfile.mkdtemp(prefix="buildsrc-"))
    for rel, text in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    git(repo, "init", "-q")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init")
    return repo


def files_under(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}


class BuildPluginTest(unittest.TestCase):
    def test_exports_only_plugin_parts(self):
        repo = make_repo({
            "plugin.json": "{}",
            "skills/x/SKILL.md": "s",
            "hooks/a.py": "a",
            "hooks/tests/t.py": "t",
            "evals/x/rubric.md": "r",
            "docs/d.md": "d",
            "AGENTS.md": "m",
        })
        (repo / "hooks/__pycache__").mkdir()
        (repo / "hooks/__pycache__/a.pyc").write_text("c")
        out = Path(tempfile.mkdtemp(prefix="buildout-")) / "plugin"
        build_plugin.build(repo, out)
        self.assertEqual(files_under(out), {"plugin.json", "skills/x/SKILL.md", "hooks/a.py"})

    def test_ref_exports_committed_content(self):
        repo = make_repo({"plugin.json": "{}", "skills/x/SKILL.md": "v1"})
        (repo / "skills/x/SKILL.md").write_text("v2")
        base = Path(tempfile.mkdtemp(prefix="buildout-"))
        self.assertEqual((build_plugin.build(repo, base / "a", ref="HEAD") / "skills/x/SKILL.md").read_text(), "v1")
        self.assertEqual((build_plugin.build(repo, base / "b") / "skills/x/SKILL.md").read_text(), "v2")

    def test_out_is_replaced(self):
        repo = make_repo({"plugin.json": "{}"})
        out = Path(tempfile.mkdtemp(prefix="buildout-")) / "plugin"
        out.mkdir()
        (out / "stale.txt").write_text("old")
        build_plugin.build(repo, out)
        self.assertEqual(files_under(out), {"plugin.json"})


if __name__ == "__main__":
    unittest.main()
