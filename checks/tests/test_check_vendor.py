import unittest

from _helpers import entry, lock, make_repo

import check_vendor

SKILL = "skills/x/SKILL.md"


class CheckVendorTest(unittest.TestCase):
    def test_unlisted_file_is_error(self):
        root = make_repo({SKILL: "x"}, lock())
        errors = check_vendor.run(root)
        self.assertTrue(any(SKILL in e for e in errors), errors)

    def test_listed_file_passes(self):
        root = make_repo({SKILL: "x"}, lock(files=[entry(SKILL)]))
        self.assertEqual(check_vendor.run(root), [])

    def test_original_file_passes(self):
        root = make_repo({SKILL: "x"}, lock(original=[SKILL]))
        self.assertEqual(check_vendor.run(root), [])

    def test_missing_listed_path_is_error(self):
        root = make_repo({}, lock(files=[entry(SKILL)]))
        errors = check_vendor.run(root)
        self.assertTrue(any(SKILL in e for e in errors), errors)

    def test_bad_sha_format_is_error(self):
        root = make_repo({SKILL: "x"}, lock(files=[entry(SKILL, sha="nothex")]))
        errors = check_vendor.run(root)
        self.assertTrue(any("sha256" in e for e in errors), errors)

    def test_scope_covers_rules_and_agents(self):
        root = make_repo({"rules/AGENTS.md": "r", "agents/a.md": "a"}, lock())
        errors = check_vendor.run(root)
        self.assertEqual(len(errors), 2, errors)

    def test_files_outside_scope_ignored(self):
        root = make_repo({"docs/x.md": "d", "checks/y.py": "c"}, lock())
        self.assertEqual(check_vendor.run(root), [])

    def test_missing_lock_is_error(self):
        root = make_repo({SKILL: "x"})
        errors = check_vendor.run(root)
        self.assertTrue(any("vendor.lock" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
