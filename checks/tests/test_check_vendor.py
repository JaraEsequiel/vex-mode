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
        root = make_repo({SKILL: "x"}, lock(files=[dict(entry(SKILL), adapted=True)]))
        self.assertEqual(check_vendor.run(root), [])

    def test_original_file_passes(self):
        root = make_repo({SKILL: "x"}, lock(original=[SKILL]))
        self.assertEqual(check_vendor.run(root), [])

    def test_missing_listed_path_is_error(self):
        root = make_repo({}, lock(files=[entry(SKILL)]))
        errors = check_vendor.run(root)
        self.assertTrue(any(SKILL in e for e in errors), errors)

    def test_bad_sha_format_is_error(self):
        root = make_repo({SKILL: "x"}, lock(files=[dict(entry(SKILL, sha="nothex"), adapted=True)]))
        errors = check_vendor.run(root)
        self.assertTrue(any("sha256" in e for e in errors), errors)

    def test_removed_ref_to_a_vendored_skill_is_error(self):
        other = "skills/unslop/SKILL.md"
        item = dict(entry(SKILL), adapted=True, removed_refs=["unslop", "arena"])
        root = make_repo({SKILL: "x", other: "u"}, lock(files=[item, dict(entry(other), adapted=True)]))
        errors = check_vendor.run(root)
        self.assertTrue(any("unslop" in e and "restore" in e for e in errors), errors)
        self.assertFalse(any("arena" in e for e in errors), errors)

    def test_local_additions_must_be_strings(self):
        bad = dict(entry(SKILL), adapted=True, local_additions="one line")
        errors = check_vendor.run(make_repo({SKILL: "x"}, lock(files=[bad])))
        self.assertTrue(any("local_additions" in e for e in errors), errors)

    def test_upstream_commit_must_be_a_sha(self):
        good = dict(entry(SKILL), adapted=True, upstream_commit="a" * 40)
        self.assertEqual(check_vendor.run(make_repo({SKILL: "x"}, lock(files=[good]))), [])
        bad = dict(entry(SKILL), adapted=True, upstream_commit="main")
        errors = check_vendor.run(make_repo({SKILL: "x"}, lock(files=[bad])))
        self.assertTrue(any("upstream_commit" in e for e in errors), errors)

    def test_unadapted_file_must_match_upstream_sha(self):
        import hashlib
        good = hashlib.sha256(b"x").hexdigest()
        ok = make_repo({SKILL: "x"}, lock(files=[entry(SKILL, sha=good)]))
        edited = make_repo({SKILL: "x edited"}, lock(files=[entry(SKILL, sha=good)]))
        self.assertEqual(check_vendor.run(ok), [])
        errors = check_vendor.run(edited)
        self.assertTrue(any("differs from upstream" in e for e in errors), errors)

    def test_adapted_file_may_diverge(self):
        item = dict(entry(SKILL), adapted=True)
        root = make_repo({SKILL: "x edited"}, lock(files=[item]))
        self.assertEqual(check_vendor.run(root), [])

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
