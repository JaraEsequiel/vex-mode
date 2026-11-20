"""The same hooks, fed Claude Code payloads (docs/decisions/2026-11-19-claude-code-probes.md)."""
import unittest

from _helpers import REPO, SESSION, cc_bash, cc_prompt, cc_session_start, cc_stop, tmpdir

import activate
import irreversible
import session_start
import stop_gate


def context(out, event):
    spec = out["hookSpecificOutput"]
    assert spec["hookEventName"] == event, spec
    return spec["additionalContext"]


def active_state():
    state = tmpdir()
    activate.handle(cc_prompt(), REPO, state)
    return state


class SessionStartTest(unittest.TestCase):
    def test_injects_the_core_without_frontmatter(self):
        text = context(session_start.handle(cc_session_start(), REPO), "SessionStart")
        self.assertIn("# vex-mode core", text)
        self.assertNotIn("trigger: always_on", text)

    def test_names_the_command_and_the_adapter(self):
        text = context(session_start.handle(cc_session_start(source="compact"), REPO), "SessionStart")
        self.assertIn("/vex-mode:vex-mode", text)
        self.assertIn(str(REPO / "adapters/claude-code.md"), text)

    def test_ignores_agy_payloads(self):
        self.assertIsNone(session_start.handle({"conversationId": "c1", "hookEventName": "PreInvocation"}, REPO))


class ActivateTest(unittest.TestCase):
    def test_activates_on_namespaced_command(self):
        state = tmpdir()
        text = context(activate.handle(cc_prompt("/vex-mode:vex-mode fix x"), REPO, state), "UserPromptSubmit")
        self.assertTrue((state / "active" / SESSION).exists())
        self.assertIn(str(REPO / "skills/vex-mode/worker.md"), text)
        self.assertIn(str(REPO / "adapters/claude-code.md"), text)

    def test_activates_on_bare_command(self):
        state = tmpdir()
        activate.handle(cc_prompt("/vex-mode fix x"), REPO, state)
        self.assertTrue((state / "active" / SESSION).exists())

    def test_injects_once(self):
        state = active_state()
        self.assertIsNone(activate.handle(cc_prompt("/vex-mode:vex-mode again"), REPO, state))

    def test_other_prompts_untouched(self):
        state = tmpdir()
        self.assertIsNone(activate.handle(cc_prompt("fix x"), REPO, state))
        self.assertIsNone(activate.handle(cc_prompt("/vex-mode:vex-modeX"), REPO, state))
        self.assertFalse((state / "active").exists())

    def test_other_skills_are_not_injected(self):
        # Claude Code expands a plugin skill command itself, also in -p.
        self.assertIsNone(activate.handle(cc_prompt("/vex-mode:reflect"), REPO, tmpdir()))

    def test_unsafe_session_id_is_inactive(self):
        self.assertIsNone(activate.handle(cc_prompt(session="../x"), REPO, tmpdir()))


class IrreversibleTest(unittest.TestCase):
    def test_asks(self):
        out = irreversible.handle(cc_bash("git push --force origin x"))["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "PreToolUse")
        self.assertEqual(out["permissionDecision"], "ask")
        self.assertIn("irreversible", out["permissionDecisionReason"])

    def test_neutral_prints_nothing(self):
        self.assertIsNone(irreversible.handle(cc_bash("ls -la")))

    def test_never_allows(self):
        for cmd in ("ls", "rm -rf /", "gh pr merge 1"):
            out = irreversible.handle(cc_bash(cmd))
            self.assertNotEqual((out or {}).get("hookSpecificOutput", {}).get("permissionDecision"), "allow")

    def test_other_tools_ignored(self):
        self.assertIsNone(irreversible.handle({**cc_bash("rm -rf /"), "tool_name": "Read"}))


class StopGateTest(unittest.TestCase):
    def test_inactive_prints_nothing(self):
        self.assertIsNone(stop_gate.handle(cc_stop(), tmpdir()))

    def test_active_blocks_once_per_prompt(self):
        state = active_state()
        out = stop_gate.handle(cc_stop(), state)
        self.assertEqual(out["decision"], "block")
        self.assertIn("verification evidence", out["reason"])
        self.assertIsNone(stop_gate.handle(cc_stop(), state))
        self.assertEqual(stop_gate.handle(cc_stop(prompt_id="p2"), state)["decision"], "block")

    def test_never_blocks_a_continuation(self):
        self.assertIsNone(stop_gate.handle(cc_stop(active=True), active_state()))

    def test_no_prompt_id_prints_nothing(self):
        payload = cc_stop()
        del payload["prompt_id"]
        self.assertIsNone(stop_gate.handle(payload, active_state()))


if __name__ == "__main__":
    unittest.main()
