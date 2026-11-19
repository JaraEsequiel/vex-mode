import unittest

from _helpers import run_command

import irreversible

FLAGGED = [
    "git push -f origin main",
    "git push --force",
    "git push --force-with-lease origin x",
    "git push origin +main",
    "git push --mirror",
    "git push origin --delete feature",
    "rm -rf /srv/data",
    "rm -rf ~/projects",
    "rm -fr /var/lib/db",
    "psql -c 'DROP TABLE users'",
    "mysql -e 'truncate table logs'",
    "terraform destroy",
    "terraform apply -auto-approve",
    "kubectl delete ns prod",
    "firebase deploy",
    "fly deploy",
    "vercel --prod",
    "cd repo && git push -f",
    'bash -c "git push -f"',
    "sh -lc 'git push --force origin main'",
    "env FOO=1 git push -f",
    "sudo -u deploy git push -f",
    "(git push -f)",
    "echo $(git push -f)",
    "/usr/bin/git push -f",
    "command git push -f",
    "nohup git push --force &",
    "time git push -f",
    "xargs rm -rf /",
    "git push origin :main",
    "git push --prune origin",
    "rm -rf $HOME",
    'rm -fr "$HOME"/x',
    "rm -rf ../..",
]

ALLOWED = [
    "git push",
    "git push --follow-tags",
    "ls -la",
    "rm -rf ./build",
    "rm -rf node_modules",
    "rm -f /tmp/x.log",
    "grep -r force .",
    "echo 'git push -f is dangerous'",
    'bash -c "ls -la"',
    "env FOO=1 git push",
    "rm -rf ./dist",
]


class ClassifyTest(unittest.TestCase):
    def test_flags_irreversible(self):
        for cmd in FLAGGED:
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(irreversible.classify(cmd))

    def test_allows_ordinary(self):
        for cmd in ALLOWED:
            with self.subTest(cmd=cmd):
                self.assertIsNone(irreversible.classify(cmd))


class MergeGuardTest(unittest.TestCase):
    def test_merge_and_push_to_main_are_irreversible(self):
        for cmd in ("gh pr merge 3 --squash", "gh api -X PUT repos/o/r/pulls/3/merge",
                    "git push origin main", "git push origin HEAD:main",
                    "git push origin refs/heads/master", "cd x && git push origin main",
                    "git push -u origin feature:refs/heads/main"):
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(irreversible.classify(cmd))

    def test_push_of_feature_branch_is_ordinary(self):
        for cmd in ("git push -u origin correct/2026-11-22", "git push origin HEAD",
                    "git push origin main-fix", "gh pr create --fill", "gh pr view 3",
                    "gh api repos/o/r/pulls/3"):
            with self.subTest(cmd=cmd):
                self.assertIsNone(irreversible.classify(cmd))


class HandleTest(unittest.TestCase):
    def test_handle_force_asks(self):
        out = irreversible.handle(run_command("git push --force"))
        self.assertEqual(out["decision"], "force_ask")
        self.assertTrue(out["reason"])

    def test_handle_neutral(self):
        self.assertIsNone(irreversible.handle(run_command("ls -la")))

    def test_handle_never_allows(self):
        for cmd in FLAGGED + ALLOWED:
            out = irreversible.handle(run_command(cmd))
            self.assertNotEqual((out or {}).get("decision"), "allow")

    def test_handle_malformed(self):
        self.assertIsNone(irreversible.handle({}))
        self.assertIsNone(irreversible.handle({"toolCall": {"name": "run_command", "args": None}}))

    def test_unparseable_quotes_still_classified(self):
        self.assertIsNotNone(irreversible.classify("git push --force 'unterminated"))


if __name__ == "__main__":
    unittest.main()
