import unittest

from helpers import TeamCase

from whoknows import clock, scenario
from whoknows.policy import AUTO
from whoknows.search import best_passage, terms

QUESTION = "why would a retry get a 409?"


class SearchTests(unittest.TestCase):
    def test_terms_drop_filler_words_and_fold_plurals(self):
        self.assertEqual(terms("Why would the retries get a 409?"), {"retry", "409"})

    def test_passages_are_exact_and_skip_headings(self):
        text = "# Retries\nEvery retry sends the same key.\n\nSomething else entirely."
        passage, score = best_passage(text, terms("retry key"))
        self.assertEqual(passage, "Every retry sends the same key.")
        self.assertEqual(score, 2)
        self.assertIn(passage, text)

    def test_no_overlap_means_no_passage(self):
        self.assertEqual(best_passage("Nothing to see here.", terms("retry key")), (None, 0))


class AnswerTests(TeamCase):
    def test_answers_quote_the_owners_shareable_files_word_for_word(self):
        found = self.a["nina"].ask_question(QUESTION, people=["omar", "theo"])
        self.assertEqual([(who, a["path"]) for who, a in found],
                         [("omar", "docs/payments-api.md"), ("theo", "notes/retry-change.md")])
        for who, a in found:
            self.assertIn(a["text"], self.a[who].ws.read(a["path"]))
            self.assertEqual(self.a[who].policy.tier(a["path"]), AUTO)
            self.assertFalse(a["text"].startswith("#"))
        text = self.phone_texts("nina")[-1]
        self.assertIn("409", text)
        self.assertIn("drafts/charge-fix-wip.py", text)  # named so Nina can ask, never quoted
        self.assertNotIn("sk_test_", text)

    def test_quotes_are_tracked_so_later_edits_reach_whoever_read_them(self):
        self.a["nina"].ask_question(QUESTION, people=["omar"])
        self.assertIn(("omar", "docs/payments-api.md"), self.a["nina"].quotes)
        self.net.advance_to(clock.parse("07:00"))
        self.a["omar"].edit_own("docs/payments-api.md", "notes_idempotency", "Note the fix")
        self.assertIn("nina", self.steps("commit")[-1]["to"])

    def test_the_gate_stops_made_up_private_or_early_quotes(self):
        omar = self.a["omar"]

        def reason(path, text):
            r = self.net.send("omar", "nina", "answer", {"answers": [{"path": path, "text": text}]})
            return r.get("reason")

        self.assertEqual(reason("docs/payments-api.md", "Retries never need a key."), "quote isn't in the file")
        self.assertEqual(reason(".env", omar.ws.read(".env").splitlines()[0]), "private file")
        draft = omar.ws.read("drafts/charge-fix-wip.py").splitlines()[0]
        self.assertEqual(reason("drafts/charge-fix-wip.py", draft), "needs the owner's OK first")

    def test_nothing_shareable_means_saying_so(self):
        self.assertEqual(self.a["nina"].ask_question("what color is the logo?", people=["omar"]), [])
        self.assertIn("Nothing in Omar's shareable notes answers that.", self.phone_texts("nina")[-1])

    def test_a_passed_on_question_waits_for_a_sleeping_owner(self):
        handed = self.a["nina"].pass_on("is the 409 new?", people=["omar"])
        self.assertEqual(handed, [("omar", "around 7:00 AM")])
        self.assertEqual(self.steps("phone", person="omar"), [])  # asleep: it waits for his morning summary
        self.assertTrue(any("is the 409 new?" in d for d in self.a["omar"].digest))
        self.assertIn("who will see it around 7:00 AM", self.phone_texts("nina")[-1])

    def test_a_passed_on_question_goes_to_the_best_match_only(self):
        self.a["nina"].find_who_knows("checkout fails. who knows the payments code?")
        handed = self.a["nina"].pass_on("why did the retry change yesterday?")
        self.assertEqual([who for who, _ in handed], ["theo"])  # Theo made the retry change
        self.assertTrue(any("why did the retry change" in t for t in self.phone_texts("theo")))
        self.assertEqual(self.a["omar"].digest, [])


class BusFactorTests(TeamCase):
    start = "01:30"

    def test_parts_the_demo_needs_get_a_backup_when_one_person_knows_them(self):
        for who in ("nina", "theo"):
            self.a[who].person["busy"] = True  # on a call together, as in the story
        self.net.team_check()
        board = {p["id"]: p for p in self.net.board_snapshot()}
        self.assertEqual(board["checkout"]["backup"], ["ade"])  # Ade watches checkout code
        self.assertEqual(board["auth"]["backup"], ["lucas"])
        self.assertEqual(board["payments"]["backup"], [])        # Omar and Theo both know it
        self.assertEqual(sorted(board["payments"]["knowers"]), ["omar", "theo"])
        self.assertTrue(board["checkout"]["critical"])
        self.assertFalse(board["design"]["critical"])
        self.assertIn(("nina", "notes/checkout-bug.md"), self.a["ade"].copies)
        self.assertFalse(any(path == ".env" for _, path in self.a["lucas"].copies))

    def test_when_nobody_steps_up_the_one_person_who_knows_hears_about_it(self):
        self.net.choices["ade_backup_checkout"] = "no"
        self.net.team_check()
        board = {p["id"]: p for p in self.net.board_snapshot()}
        self.assertEqual(board["checkout"]["backup"], [])
        self.assertEqual(board["checkout"]["note"], "only Nina knows it")
        self.assertTrue(any("The demo depends on the Checkout page and you're the only one who knows it" in t
                            for t in self.phone_texts("nina")))


class ReceiptTests(TeamCase):
    def test_omar_wakes_up_to_a_receipt_of_everything_done_without_asking(self):
        self.a["nina"].find_who_knows("checkout fails. who knows the payments code?")
        self.a["nina"].ask_question(QUESTION)
        self.assertEqual(self.steps("phone", person="omar"), [])  # nothing reaches him overnight
        self.net.advance_to(clock.parse("07:00"))
        receipts = [s["text"] for s in self.steps("phone", person="omar") if s.get("tone") == "receipts"]
        self.assertEqual(len(receipts), 1)
        self.assertIn("told Nina's agent you own the Payments API", receipts[0])
        self.assertIn("answered Nina's question from your docs/payments-api.md", receipts[0])
        self.assertEqual(self.net.used["omar_receipts"], "ok")

    def test_tightening_makes_the_agent_ask_first_next_time(self):
        self.net.choices["omar_receipts"] = "tighten"
        self.a["nina"].ask_question(QUESTION, people=["omar"])
        self.net.advance_to(clock.parse("07:00"))
        self.assertIn("docs/payments-api.md", self.a["omar"].policy.ask_first)
        r = self.a["nina"].fetch_from("omar", "payments")
        self.assertEqual(r["shared"], [])
        self.assertIn("docs/payments-api.md", [m["path"] for m in r["mentions"]])

    def test_nothing_goes_on_a_receipt_while_the_person_is_awake(self):
        self.a["nina"].ask_question(QUESTION, people=["theo"])
        self.assertEqual(self.a["theo"].receipts, [])


class TrustTests(TeamCase):
    start = "01:35"

    def approve_first_fix(self):
        self.a["nina"].request_change("omar", "payments/charge.py", "idempotency_key",
                                      "Send the same Idempotency-Key on every retry")
        self.net.advance_to(clock.parse("07:00"))  # Omar wakes, approves, and is offered trust
        return self.a["omar"]

    def ask_for_docstring(self, who="nina"):
        return self.a[who].request_change("omar", "payments/charge.py", "docstring", "Add a one-line docstring")

    def test_a_small_clean_approval_leads_to_a_trust_offer(self):
        omar = self.approve_first_fix()
        self.assertEqual(self.net.used["omar_fix"], "approve")
        self.assertEqual(self.net.used["omar_trust"], "yes")
        self.assertEqual(omar.trust, [{"requester": "nina", "glob": "payments/*", "since": "7:00 AM"}])

    def test_small_changes_from_a_trusted_teammate_save_at_once_with_undo_offered(self):
        omar = self.approve_first_fix()
        self.net.advance_to(clock.parse("07:50"))
        self.assertEqual(self.ask_for_docstring()["status"], "auto")
        self.assertIn('"""Charge one order through the payment gateway."""', omar.ws.read("payments/charge.py"))
        commit = self.steps("commit")[-1]["card"]
        self.assertTrue(commit["by_rule"])
        self.assertEqual(self.net.used["omar_undo"], "keep")
        self.assertIn("under the rule you set at 7:00 AM", self.steps("decision", key="omar_undo")[0]["prompt"])

    def test_undo_puts_the_file_back_and_tells_the_requester(self):
        self.net.choices["omar_undo"] = "undo"
        omar = self.approve_first_fix()
        before = omar.ws.read("payments/charge.py")
        self.net.advance_to(clock.parse("07:50"))
        self.ask_for_docstring()
        self.assertEqual(omar.ws.read("payments/charge.py"), before)
        undo = self.steps("commit")[-1]
        self.assertEqual(undo["card"]["message"], "Undo Nina's change: Add a one-line docstring")
        self.assertIn("nina", undo["to"])
        self.assertIn("Omar undid your change to payments/charge.py (+0 -1).", self.phone_texts("nina"))

    def test_trust_never_covers_big_or_flagged_changes(self):
        self.net.choices["omar_fix_2"] = "decline"
        omar = self.approve_first_fix()
        before = omar.ws.read("payments/charge.py")
        r = self.a["nina"].request_change("omar", "payments/charge.py", "empty_file", "Replace it with an empty file")
        self.assertEqual(r["status"], "queued")
        self.assertTrue(self.steps("decision", key="omar_fix_2")[0]["flags"])
        self.assertEqual(omar.ws.read("payments/charge.py"), before)

    def test_trust_is_given_to_one_person_not_everyone(self):
        omar = self.approve_first_fix()
        self.assertEqual(self.ask_for_docstring("theo")["status"], "queued")
        self.assertEqual(self.net.used["omar_fix_2"], "approve")
        self.assertFalse(self.steps("commit")[-1]["card"]["by_rule"])
        self.assertEqual(len(omar.trust), 2)  # Omar was then offered the same deal for Theo


if __name__ == "__main__":
    unittest.main()
