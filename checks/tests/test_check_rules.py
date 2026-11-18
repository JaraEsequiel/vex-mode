import unittest

from _helpers import make_repo

import check_rules

TABLE = "# Repo\n\n## Rules\n\n| Rule | Enforced by |\n|---|---|\n{rows}\n"


def agents(rows):
    return TABLE.format(rows="\n".join(rows))


class CheckRulesTest(unittest.TestCase):
    def test_missing_agents_md_is_error(self):
        errors = check_rules.run(make_repo({}))
        self.assertTrue(any("AGENTS.md" in e for e in errors), errors)

    def test_missing_rules_heading_is_error(self):
        errors = check_rules.run(make_repo({"AGENTS.md": "# Repo\n\nno table\n"}))
        self.assertTrue(any("## Rules" in e for e in errors), errors)

    def test_enforcer_path_must_exist(self):
        root = make_repo({"AGENTS.md": agents(["| Be good | `checks/nope.py` |"])})
        errors = check_rules.run(root)
        self.assertTrue(any("Be good" in e and "checks/nope.py" in e for e in errors), errors)

    def test_row_without_enforcer_is_error(self):
        root = make_repo({"AGENTS.md": agents(["| Be good |  |"])})
        errors = check_rules.run(root)
        self.assertTrue(any("Be good" in e for e in errors), errors)

    def test_judgment_needs_doc_path(self):
        bare = make_repo({"AGENTS.md": agents(["| Taste | judgment |"])})
        with_doc = make_repo({"AGENTS.md": agents(["| Taste | judgment `docs/taste.md` |"]), "docs/taste.md": "x"})
        self.assertTrue(check_rules.run(bare))
        self.assertEqual(check_rules.run(with_doc), [])

    def test_valid_table_passes(self):
        root = make_repo({"AGENTS.md": agents(["| Be good | `checks/a.py` `scripts/b.py` |"]), "checks/a.py": "", "scripts/b.py": ""})
        self.assertEqual(check_rules.run(root), [])

    def test_empty_table_is_error(self):
        root = make_repo({"AGENTS.md": agents([])})
        errors = check_rules.run(root)
        self.assertTrue(any("no rows" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
