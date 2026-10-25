import json
import unittest

from whoknows import scenario
from whoknows.story import all_main_choices, run

SECRETS = ("sk_test_", "ghp_", "Buy Nina a coffee", "STRIPE_SECRET_KEY", "GITHUB_TOKEN")


class MainStoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace = run("main")
        cls.summary = cls.trace["summary"]

    def test_everyone_gets_what_they_need_without_waking_anyone(self):
        self.assertEqual(self.summary["woken_up"], 0)
        self.assertEqual(self.summary["blocked"], [])
        board = {p["id"]: p for p in self.summary["board"]}
        self.assertTrue(all(p["owners"] for p in board.values()))
        self.assertEqual(board["checkout"]["note"], "fixed")

    def test_only_shareable_files_crossed(self):
        crossed = {(f["owner"], f["path"]) for f in self.summary["files_crossed"]}
        self.assertEqual(crossed, {
            ("omar", "docs/payments-api.md"),      # shareable notes, quoted and then fetched
            ("omar", "drafts/charge-fix-wip.py"),  # a draft, sent only after Omar said yes at 7:00
            ("nina", "notes/checkout-bug.md"),     # Nina's notes, pulled by Ade when he became checkout backup
            ("nina", "web/checkout.tsx"),
            ("priya", "notes/auth.md"),            # Priya's notes, pulled by Lucas as the login backup
        })
        never = {(f["person"], f["path"]) for f in self.summary["never_left"]}
        self.assertIn(("omar", ".env"), never)
        self.assertIn(("omar", "personal/journal.md"), never)

    def test_the_commit_goes_to_three_people_not_ten(self):
        commits = [s for s in self.trace["steps"] if s["type"] == "commit"]
        self.assertEqual(commits[0]["to"], ["nina", "theo", "ade"])
        self.assertEqual(commits[1]["to"], ["nina", "theo"])

    def test_runs_are_identical(self):
        self.assertEqual(json.dumps(run("main"), sort_keys=True), json.dumps(self.trace, sort_keys=True))


class EveryBranchTests(unittest.TestCase):
    def test_every_choice_combination_runs_cleanly(self):
        count = 0
        for choices in all_main_choices():
            trace = run("main", choices)
            text = json.dumps(trace)
            with self.subTest(choices=choices):
                self.assertEqual(trace["summary"]["woken_up"], 0)
                self.assertEqual(trace["summary"]["blocked"], [])
                for key, value in choices.items():
                    self.assertEqual(trace["summary"]["decisions"][key], value)
                for secret in SECRETS:
                    self.assertNotIn(secret, text)
            count += 1
        self.assertEqual(count, 48)


class RogueStoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace = run("rogue")
        cls.text = json.dumps(cls.trace)

    def test_every_attack_is_stopped(self):
        reasons = [b["reason"] for b in self.trace["summary"]["blocked"]]
        self.assertEqual(reasons, ["private file", "not this person's file", "not on this team"])
        self.assertEqual(self.trace["summary"]["decisions"]["omar_fix"], "decline")
        self.assertNotIn('"applied"', self.text)

    def test_nothing_private_appears_anywhere_in_the_trace(self):
        for secret in SECRETS:
            self.assertNotIn(secret, self.text)

    def test_omar_hears_about_it_when_he_wakes_up(self):
        alerts = [s for s in self.trace["steps"] if s["type"] == "phone" and s.get("tone") == "alert"]
        self.assertEqual(alerts[0]["person"], "omar")
        self.assertIn("skip your approval", alerts[0]["text"])

    def test_the_wipe_never_happens(self):
        self.assertNotIn(scenario.CHARGE, "")  # sanity: the original file is non-empty
        self.assertEqual([s for s in self.trace["steps"] if s["type"] == "commit"], [])


if __name__ == "__main__":
    unittest.main()
