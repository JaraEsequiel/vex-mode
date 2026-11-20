import json
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


ADAPTER = "| `vex-agent` | x |\n| Run another vex-mode skill | x |\n| todolist | x |\n"
SOURCE = {
    "plugin.json": '{"name": "vex-mode", "version": "0.1.0"}',
    "adapters/claude-code.md": ADAPTER,
    "skills/plain/SKILL.md": "---\nname: plain\n---\n\n# Plain\n\nNo harness names here.\n",
    "skills/router/SKILL.md": "---\nname: router\n---\n\n# Router\n\nSpawn a `vex-agent`.\n",
    "agents/vex-agent.md": "---\nname: vex-agent\ndescription: d\nsubagent: true\ntools: [read_file]\n---\nbody\n",
    "rules/AGENTS.md": "core",
    "hooks/a.py": "a",
    "hooks/tests/t.py": "t",
    "hooks.json": "{}",
    "evals/x.md": "e",
}


class ClaudeTreeTest(unittest.TestCase):
    def render(self, **changes):
        return build_plugin.render_claude(make_repo({**SOURCE, **changes}))

    def test_tree_holds_only_claude_code_parts(self):
        files = self.render()
        self.assertEqual(set(files), {
            ".claude-plugin/plugin.json", "README.md", "adapters/claude-code.md", "agents/vex-agent.md",
            "hooks/a.py", "hooks/hooks.json", "rules/AGENTS.md", "skills/plain/SKILL.md", "skills/router/SKILL.md",
        })

    def test_hooks_use_claude_code_events_and_quote_the_root(self):
        hooks = json.loads(self.render()["hooks/hooks.json"][0])["hooks"]
        self.assertEqual(set(hooks), {"SessionStart", "UserPromptSubmit", "PreToolUse", "Stop"})
        self.assertEqual(hooks["PreToolUse"][0]["matcher"], "Bash")
        self.assertIn('"${CLAUDE_PLUGIN_ROOT}/hooks/', hooks["Stop"][0]["hooks"][0]["command"])

    def test_version_carries_a_content_hash(self):
        a = json.loads(self.render()[".claude-plugin/plugin.json"][0])["version"]
        b = json.loads(self.render(**{"rules/AGENTS.md": "core v2"})[".claude-plugin/plugin.json"][0])["version"]
        self.assertTrue(a.startswith("0.1.0+"))
        self.assertNotEqual(a, b)

    def test_agent_keeps_only_claude_code_fields(self):
        text = self.render()["agents/vex-agent.md"][0].decode()
        self.assertEqual(text, "---\nname: vex-agent\ndescription: d\n---\nbody\n")

    def test_adapter_line_only_where_agy_names_are_used(self):
        files = self.render()
        self.assertIn("../../adapters/claude-code.md", files["skills/router/SKILL.md"][0].decode())
        self.assertNotIn("adapter", files["skills/plain/SKILL.md"][0].decode())

    def test_missing_adapter_row_fails(self):
        with self.assertRaisesRegex(build_plugin.TreeError, "no row for .*vex-agent"):
            self.render(**{"adapters/claude-code.md": "nothing"})

    def test_unmapped_agy_name_fails(self):
        with self.assertRaisesRegex(build_plugin.TreeError, "names agy"):
            self.render(**{"skills/plain/SKILL.md": "# Plain\n\nRun agy doctor.\n"})

    def test_per_harness_lines_need_their_row(self):
        skill = "# Plain\n\n- agy: do a.\n- Claude Code: do b.\n"
        with self.assertRaisesRegex(build_plugin.TreeError, "no row for `Claude Code:` line"):
            self.render(**{"skills/plain/SKILL.md": skill})
        self.render(**{"skills/plain/SKILL.md": skill, "adapters/claude-code.md": ADAPTER + "| `Claude Code:` line | x |\n"})

    def test_check_finds_a_stale_tree(self):
        repo = make_repo(SOURCE)
        tree = Path(tempfile.mkdtemp(prefix="cctree-")) / "claude-code"
        build_plugin.write_claude(repo, tree)
        self.assertEqual(build_plugin.check_claude(repo, tree), [])
        (tree / "rules/AGENTS.md").write_text("edited by hand")
        (tree / "extra.md").write_text("x")
        self.assertEqual(build_plugin.check_claude(repo, tree), ["extra.md", "rules/AGENTS.md"])


class CommittedClaudeTreeTest(unittest.TestCase):
    def test_committed_tree_is_up_to_date(self):
        repo = Path(__file__).resolve().parents[2]
        self.assertEqual(build_plugin.check_claude(repo, repo / build_plugin.CLAUDE_TREE), [])
