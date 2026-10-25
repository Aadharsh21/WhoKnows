import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from whoknows.cards import when_words
from whoknows.repo import RepoTeam, build_team, owns

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)

COMMITS = [
    # who, email, days ago, subject, body, {path: text}
    ("Carol Moss", "carol@example.com", 400, "Document the setup steps", "",
     {"docs/setup.md": "Run make.\n"}),
    ("Alice Chen", "alice@example.com", 40, "Add session cookie expiry",
     "Cookies now expire after 30 days.\n\nCo-authored-by: Dan Park <dan@example.com>",
     {"auth/session.py": "EXPIRY = 30\n"}),
    ("Bob Diaz", "bob@example.com", 3, "Retry failed charges with backoff",
     "Each retry sends the same Idempotency-Key so the gateway never charges twice.",
     {"payments/retry.py": "def retry(): pass\n"}),
    ("Alice Chen", "alice.chen@school.edu", 2, "Fix login redirect loop", "",
     {"auth/login.py": "def login(): pass\n"}),
    ("dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com", 1, "Bump left-pad", "",
     {"requirements.txt": "left-pad==2\n"}),
]


def make_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    run = lambda *a, **extra: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True,
                                             env={**env, **extra})
    run("init", "-q")
    (repo / "CODEOWNERS").write_text("/payments/ @bob\n/auth/ @some-org/security-team\n")
    for name, email, ago, subject, body, files in COMMITS:
        for rel, text in files.items():
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_text(text)
        when = (NOW - timedelta(days=ago)).isoformat()
        run("add", "-A")
        run("commit", "-q", "-m", subject + (f"\n\n{body}" if body else ""),
            GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email, GIT_AUTHOR_DATE=when,
            GIT_COMMITTER_NAME=name, GIT_COMMITTER_EMAIL=email, GIT_COMMITTER_DATE=when)
    return repo


class RepoModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.repo = make_repo(Path(cls._tmp.name))
        cls.team = RepoTeam(cls.repo, now=NOW.timestamp())

    @classmethod
    def tearDownClass(cls):
        cls.team.close()
        cls._tmp.cleanup()

    def test_everyone_who_committed_gets_an_agent_but_bots_do_not(self):
        names = [p["name"] for p in self.team.info["people"]]
        self.assertEqual(names, ["Alice Chen", "Bob Diaz", "Carol Moss"])  # Alice's two addresses are one person

    def test_the_person_who_knows_answers_from_their_own_commits(self):
        r = self.team.ask("who knows the retry backoff?")
        self.assertEqual(r["who"][0]["person"], "Bob Diaz")
        self.assertIn("changed payments/retry.py on Thursday", r["who"][0]["why"])
        self.assertEqual(r["asked"], 3)
        self.assertEqual((r["notified"], r["blocked"]), (0, 0))
        self.assertIn("Idempotency-Key", r["quotes"][0]["text"])

    def test_codeowners_names_an_owner(self):
        r = self.team.ask("who owns payments?")
        self.assertEqual((r["who"][0]["person"], r["who"][0]["level"]), ("Bob Diaz", "owner"))

    def test_quotes_never_carry_email_addresses(self):
        r = self.team.ask("why do session cookies expire?")
        self.assertEqual(r["who"][0]["person"], "Alice Chen")
        self.assertTrue(r["quotes"])
        self.assertFalse(any("@" in q["text"] for q in r["quotes"]))

    def test_nobody_knows_is_a_real_answer(self):
        r = self.team.ask("who knows the kubernetes helm charts?")
        self.assertEqual((r["know"], r["who"], r["quotes"]), (0, [], []))

    def test_old_history_can_be_left_out(self):
        team = build_team(self.repo, days=100, now=NOW.timestamp())
        self.assertNotIn("Carol Moss", [p["name"] for p in team["people"]])


class HelperTests(unittest.TestCase):
    def test_codeowners_patterns(self):
        self.assertTrue(owns("/payments/", "payments/retry.py"))
        self.assertFalse(owns("/payments/", "src/payments/retry.py"))
        self.assertTrue(owns("payments/", "src/payments/retry.py"))
        self.assertTrue(owns("*.md", "docs/setup.md"))
        self.assertFalse(owns("*.md", "docs/setup.py"))

    def test_dates_read_naturally(self):
        self.assertEqual(when_words((NOW - timedelta(days=1)).timestamp(), NOW), "yesterday at 12:00 PM")
        self.assertEqual(when_words((NOW - timedelta(days=21)).timestamp(), NOW), "3 weeks ago")
        self.assertEqual(when_words(datetime(2025, 3, 2, tzinfo=timezone.utc).timestamp(), NOW), "in March 2025")


if __name__ == "__main__":
    unittest.main()
