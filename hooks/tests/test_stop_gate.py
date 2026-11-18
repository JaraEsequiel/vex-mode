import unittest

from _helpers import stop, tmpdir

import stop_gate


def active_state(conv="c1"):
    state = tmpdir()
    (state / "active").mkdir()
    (state / "active" / conv).touch()
    return state


class StopGateTest(unittest.TestCase):
    def test_inactive_allows_stop(self):
        self.assertEqual(stop_gate.handle(stop(), tmpdir()), {})

    def test_active_asks_for_evidence_once(self):
        out = stop_gate.handle(stop(), active_state())
        self.assertEqual(out["decision"], "continue")
        self.assertIn("verification evidence", out["reason"])

    def test_no_loop(self):
        self.assertEqual(stop_gate.handle(stop(continuation=True), active_state()), {})

    def test_no_loop_when_agy_reports_later_execution(self):
        # agy 1.5.11 keeps continuationActive=False after a Stop hook continues; executionNum counts up instead.
        self.assertEqual(stop_gate.handle(stop(continuation=False, execution=1), active_state()), {})

    def test_other_termination_allows(self):
        self.assertEqual(stop_gate.handle(stop(reason="USER_CANCELED"), active_state()), {})

    def test_other_conversation_allows(self):
        self.assertEqual(stop_gate.handle(stop(conv="c2"), active_state("c1")), {})

    def test_malformed(self):
        self.assertEqual(stop_gate.handle({}, active_state()), {})


if __name__ == "__main__":
    unittest.main()
