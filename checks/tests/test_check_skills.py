import unittest

from _helpers import entry, lock, make_repo

import check_skills


def skill(name="foo", description="does foo", body=""):
    return f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n"


class FrontmatterTest(unittest.TestCase):
    def test_name_must_match_folder(self):
        root = make_repo({"skills/foo/SKILL.md": skill(name="bar")}, lock())
        errors = check_skills.run(root)
        self.assertTrue(any("foo" in e and "name" in e for e in errors), errors)

    def test_description_required(self):
        root = make_repo({"skills/foo/SKILL.md": skill(description="")}, lock())
        errors = check_skills.run(root)
        self.assertTrue(any("description" in e for e in errors), errors)

    def test_valid_skill_passes(self):
        root = make_repo({"skills/foo/SKILL.md": skill()}, lock())
        self.assertEqual(check_skills.run(root), [])


class SizeTest(unittest.TestCase):
    def _padded(self, total):
        base = skill()
        return base + "x" * (total - len(base.encode()))

    def test_skill_size_cap(self):
        over = make_repo({"skills/foo/SKILL.md": self._padded(16385)}, lock())
        at = make_repo({"skills/foo/SKILL.md": self._padded(16384)}, lock())
        self.assertTrue(any("16384" in e for e in check_skills.run(over)))
        self.assertEqual(check_skills.run(at), [])

    def test_rule_size_cap(self):
        root = make_repo({"rules/x.md": "r" * 24577}, lock())
        errors = check_skills.run(root)
        self.assertTrue(any("24576" in e for e in errors), errors)


class ReferenceTest(unittest.TestCase):
    def test_missing_playbook_ref(self):
        root = make_repo({"skills/foo/SKILL.md": skill(body="open playbooks/nope.md")}, lock())
        errors = check_skills.run(root)
        self.assertTrue(any("playbooks/nope.md" in e for e in errors), errors)

    def test_existing_playbook_ref_passes(self):
        root = make_repo({
            "skills/foo/SKILL.md": skill(body="open playbooks/ok.md"),
            "skills/foo/playbooks/ok.md": "steps",
        }, lock())
        self.assertEqual(check_skills.run(root), [])

    def test_missing_bold_skill_ref(self):
        root = make_repo({"skills/foo/SKILL.md": skill(body="use the **ghost** skill")}, lock())
        errors = check_skills.run(root)
        self.assertTrue(any("ghost" in e for e in errors), errors)

    def test_bold_principle_ref_resolves_to_principle_folder(self):
        root = make_repo({
            "skills/foo/SKILL.md": skill(body="the **fix-root-causes** principle"),
            "skills/principle-fix-root-causes/SKILL.md": skill(name="principle-fix-root-causes"),
        }, lock())
        self.assertEqual(check_skills.run(root), [])

    def test_missing_principle_token_ref(self):
        root = make_repo({"skills/foo/SKILL.md": skill(body="see principle-ghost")}, lock())
        errors = check_skills.run(root)
        self.assertTrue(any("principle-ghost" in e for e in errors), errors)

    def test_pending_ref_is_allowed(self):
        root = make_repo(
            {"skills/foo/SKILL.md": skill(body="the **ghost** skill and playbooks/later.md")},
            lock(files=[entry("skills/foo/SKILL.md", pending_refs=["ghost", "playbooks/later.md"])]),
        )
        self.assertEqual(check_skills.run(root), [])

    def test_stale_pending_ref_is_error(self):
        root = make_repo(
            {"skills/foo/SKILL.md": skill(body="nothing referenced here")},
            lock(files=[entry("skills/foo/SKILL.md", pending_refs=["ghost"])]),
        )
        errors = check_skills.run(root)
        self.assertTrue(any("stale pending_ref" in e and "ghost" in e for e in errors), errors)

    def test_pending_ref_must_match_whole_token(self):
        root = make_repo(
            {"skills/foo/SKILL.md": skill(body="unslopped prose")},
            lock(files=[entry("skills/foo/SKILL.md", pending_refs=["unslop"])]),
        )
        errors = check_skills.run(root)
        self.assertTrue(any("stale pending_ref 'unslop'" in e for e in errors), errors)

    def test_relative_link_must_resolve(self):
        root = make_repo({"skills/foo/SKILL.md": skill(body="[x](../missing/SKILL.md)")}, lock())
        errors = check_skills.run(root)
        self.assertTrue(any("../missing/SKILL.md" in e for e in errors), errors)

    def test_refs_checked_in_rules_and_agents(self):
        root = make_repo({"rules/AGENTS.md": "use the **ghost** skill", "agents/a.md": "see principle-nope"}, lock())
        errors = check_skills.run(root)
        self.assertEqual(len(errors), 2, errors)


if __name__ == "__main__":
    unittest.main()
