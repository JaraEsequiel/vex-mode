"""The same hooks, fed Claude Code payloads (docs/decisions/2026-11-19-claude-code-probes.md)."""
import json
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


def user_prompt(prompt_id):
    return {"type": "user", "promptId": prompt_id, "message": {"role": "user", "content": "/vex-mode:vex-mode fix x"}}


def tool_use(name):
    params = {"command": "python3 check.py"} if name == "Bash" else {"file_path": "/w/a.py"}
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "id": "t", "name": name, "input": params}]}}


def turn_transcript(tools, prompt_id="p1"):
    """A Claude Code session file: the prompt, the tool calls (each followed by its result), the final text."""
    entries = [user_prompt(prompt_id)]
    for name in tools:
        entries.append(tool_use(name))
        entries.append({"type": "user", "promptId": prompt_id, "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": "ok"}]}})
    entries.append({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "done"}]}})
    path = tmpdir() / "session.jsonl"
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))
    return str(path)


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

    def test_skips_when_the_last_tool_ran_a_command_after_the_edits(self):
        out = stop_gate.handle(cc_stop(transcript=turn_transcript(["Edit", "Bash"])), active_state())
        self.assertIsNone(out)

    def test_blocks_when_an_edit_follows_the_last_command(self):
        out = stop_gate.handle(cc_stop(transcript=turn_transcript(["Bash", "Edit"])), active_state())
        self.assertEqual(out["decision"], "block")

    def test_blocks_a_turn_without_tools(self):
        out = stop_gate.handle(cc_stop(transcript=turn_transcript([])), active_state())
        self.assertEqual(out["decision"], "block")

    def test_commands_from_an_earlier_prompt_do_not_count(self):
        path = turn_transcript(["Bash"], prompt_id="p0")
        with open(path, "a") as f:
            f.write(json.dumps(user_prompt("p1")) + "\n")
        out = stop_gate.handle(cc_stop(transcript=path), active_state())
        self.assertEqual(out["decision"], "block")

    def test_subagent_commands_do_not_count(self):
        path = turn_transcript(["Edit"])
        with open(path, "a") as f:
            f.write(json.dumps({**tool_use("Bash"), "isSidechain": True}) + "\n")
        out = stop_gate.handle(cc_stop(transcript=path), active_state())
        self.assertEqual(out["decision"], "block")

    def test_unreadable_transcript_blocks(self):
        out = stop_gate.handle(cc_stop(transcript="/nonexistent/t.jsonl"), active_state())
        self.assertEqual(out["decision"], "block")
        bad = tmpdir() / "t.jsonl"
        bad.write_text("not json\n")
        self.assertEqual(stop_gate.handle(cc_stop(transcript=str(bad)), active_state())["decision"], "block")

    def test_no_prompt_id_prints_nothing(self):
        payload = cc_stop()
        del payload["prompt_id"]
        self.assertIsNone(stop_gate.handle(payload, active_state()))


if __name__ == "__main__":
    unittest.main()
