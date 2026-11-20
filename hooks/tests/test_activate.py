import unittest

from _helpers import REPO, pre_invocation, tmpdir

import activate


def message(out):
    return out["injectSteps"][0]["systemMessage"]["systemMessage"]


class ActivateTest(unittest.TestCase):
    def test_activates_on_slash_command(self):
        state = tmpdir()
        out = activate.handle(pre_invocation("c1", "/vex-mode fix x"), REPO, state)
        self.assertTrue((state / "active" / "c1").exists())
        self.assertIn(str(REPO / "skills/vex-mode/worker.md"), message(out))

    def test_reading_list_comes_from_read_first_block(self):
        out = activate.handle(pre_invocation(), REPO, tmpdir())
        self.assertIn(str(REPO / "skills/vex-mode/worker.md"), message(out))
        self.assertNotIn("principle-", message(out))
        self.assertIn(str(REPO / "skills/vex-mode/playbooks/opening-a-pr.md"), message(out))

    def test_injects_once(self):
        state = tmpdir()
        activate.handle(pre_invocation("c1"), REPO, state)
        self.assertEqual(activate.handle(pre_invocation("c1"), REPO, state), {})

    def test_inactive_conversation_untouched(self):
        state = tmpdir()
        out = activate.handle(pre_invocation("c2", "hello there"), REPO, state)
        self.assertEqual(out, {})
        self.assertFalse((state / "active" / "c2").exists())

    def test_other_conversation_not_affected(self):
        state = tmpdir()
        activate.handle(pre_invocation("c1"), REPO, state)
        self.assertEqual(activate.handle(pre_invocation("c2", "hello"), REPO, state), {})
        self.assertFalse((state / "active" / "c2").exists())

    def test_slash_command_must_be_exact(self):
        out = activate.handle(pre_invocation("c3", "/vex-modest thing"), REPO, tmpdir())
        self.assertEqual(out, {})

    def test_unsafe_conversation_id_is_ignored(self):
        state = tmpdir() / "a" / "state"
        outside = tmpdir() / "pwned"
        for conv in (str(outside), "../../escape", "a/b", ""):
            with self.subTest(conv=conv):
                self.assertEqual(activate.handle(pre_invocation(conv), REPO, state), {})
        self.assertFalse(outside.exists())
        self.assertFalse((state.parent / "escape").exists())

    def test_plugin_skill_command_injects_its_text_and_folder(self):
        state = tmpdir()
        out = activate.handle(pre_invocation("c4", "/agent-ready set this repo up"), REPO, state)
        text = message(out)
        self.assertIn("# Agent-ready", text)
        self.assertIn(str(REPO / "skills/agent-ready"), text)
        self.assertFalse((state / "active" / "c4").exists())

    def test_skill_text_injected_once_per_message(self):
        state = tmpdir()
        activate.handle(pre_invocation("c5", "/correct"), REPO, state)
        self.assertEqual(activate.handle(pre_invocation("c5", "/correct"), REPO, state), {})
        self.assertIn("# Correct", message(activate.handle(pre_invocation("c5", "/correct again"), REPO, state)))

    def test_unknown_slash_command_is_ignored(self):
        self.assertEqual(activate.handle(pre_invocation("c6", "/nope x"), REPO, tmpdir()), {})
        self.assertEqual(activate.handle(pre_invocation("c6", "/../vex-mode x"), REPO, tmpdir()), {})

    def test_malformed_payload(self):
        self.assertEqual(activate.handle({}, REPO, tmpdir()), {})


if __name__ == "__main__":
    unittest.main()
