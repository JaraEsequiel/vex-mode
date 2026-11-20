"""skills/show-me-your-work/scripts/log.sh: rows it writes pass its own --check, and --check catches bad logs."""
import subprocess
import tempfile
import unittest
from pathlib import Path

LOG_SH = Path(__file__).resolve().parents[2] / "skills/show-me-your-work/scripts/log.sh"
HEADER = "ts\tphase\tdecision\twhy\tevidence\tresult\n"
GOOD = "2026-05-24T09:02:00Z\tframe\tcounted the work\twanted the size first\tcommit 3a9f1c2\topen\n"


def run(*args):
    return subprocess.run(["bash", str(LOG_SH), *args], capture_output=True, text=True)


class LogShTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "decisions.tsv"

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, text):
        self.log.write_text(text)
        return run("--check", str(self.log))

    def test_written_rows_pass_check(self):
        self.assertEqual(run(str(self.log), "frame", "chose x", "because\ty", "=1+1", "tests green").returncode, 0)
        self.assertEqual(run(str(self.log), "build", "line\nbreak", "why", "file:1", "open").returncode, 0)
        result = run("--check", str(self.log))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.log.read_text().splitlines()), 3)

    def test_writer_refuses_an_empty_cell(self):
        result = run(str(self.log), "frame", "chose x", " \t", "commit 1", "open")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("why", result.stderr)
        self.assertFalse(self.log.exists() and self.log.read_text().count("\n") > 1)

    def test_good_log_passes(self):
        self.assertEqual(self.check(HEADER + GOOD).returncode, 0)

    def test_repeated_header_line_is_tolerated(self):
        # log.sh can write a second header when a network mount fails its -s test.
        self.assertEqual(self.check(HEADER + GOOD + HEADER + GOOD).returncode, 0)

    def test_bad_header_fails(self):
        result = self.check("ts\tphase\tdecision\tevidence\twhy\tresult\n" + GOOD)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(":1:", result.stderr)

    def test_missing_or_empty_log_fails(self):
        self.assertNotEqual(run("--check", str(self.log)).returncode, 0)
        self.assertNotEqual(self.check("").returncode, 0)

    def test_wrong_column_count_fails(self):
        result = self.check(HEADER + GOOD + "2026-05-24T09:03:00Z\tframe\tonly four\tcells\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(":3:", result.stderr)

    def test_empty_cell_fails(self):
        result = self.check(HEADER + "2026-05-24T09:02:00Z\tframe\t\twhy\tcommit 1\topen\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(":2:", result.stderr)

    def test_local_or_malformed_timestamp_fails(self):
        for ts in ("2026-05-24T09:02:00-03:00", "2026-05-24 09:02:00Z", "2026-05-24T09:02Z", "yesterday"):
            with self.subTest(ts=ts):
                result = self.check(HEADER + GOOD.replace("2026-05-24T09:02:00Z", ts))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(":2:", result.stderr)

    def test_every_bad_line_is_reported(self):
        result = self.check(HEADER + "x\n" + GOOD + "y\n")
        self.assertIn(":2:", result.stderr)
        self.assertIn(":4:", result.stderr)
        self.assertNotIn(":3:", result.stderr)

    def test_check_usage(self):
        self.assertNotEqual(run("--check").returncode, 0)


if __name__ == "__main__":
    unittest.main()
