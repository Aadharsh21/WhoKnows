import time
import unittest

from whoknows import clock, scenario
from whoknows.live import Live
from whoknows.understand import by_rules

TEAM = {"project": scenario.PROJECT, "people": scenario.PEOPLE, "parts": scenario.PARTS}


class RuleTests(unittest.TestCase):
    def parse(self, text, me="nina"):
        return by_rules(text, me, TEAM)

    def test_the_demo_phrasings(self):
        self.assertEqual(self.parse("seat omar", None), {"action": "seat", "person": "omar"})
        self.assertEqual(self.parse("who knows the payments code?")["action"], "who_knows")
        self.assertEqual(self.parse("get omar's notes on payments"), {"action": "fetch", "person": "omar", "part": "payments"})
        self.assertEqual(self.parse("ask omar for drafts/charge-fix-wip.py"),
                         {"action": "file", "person": "omar", "path": "drafts/charge-fix-wip.py"})
        self.assertEqual(self.parse("can theo hop on a call?")["action"], "help")
        change = self.parse("ask omar's agent to send the same idempotency key on every retry in charge.py")
        self.assertEqual((change["action"], change["person"], change["path"], change["recipe"]),
                         ("change", "omar", "charge.py", "idempotency_key"))
        time = self.parse("i need 10 min with omar before the demo")
        self.assertEqual((time["action"], time["person"], time["minutes"], time["before"]), ("time", "omar", 10, "09:00"))
        self.assertEqual(self.parse("i'm doing the readme tonight")["part"], "readme")
        self.assertEqual(self.parse("skip to 7:00"), {"action": "clock", "before": "07:00"})
        self.assertEqual(self.parse("skip to 7:45 am"), {"action": "clock", "before": "07:45"})

    def test_questions_and_passing_them_on(self):
        self.assertEqual(self.parse("why would a retry get a 409?"),
                         {"action": "question", "question": "why would a retry get a 409?"})
        self.assertEqual(self.parse("who knows the payments code?")["action"], "who_knows")
        self.assertEqual(self.parse("pass it on"), {"action": "pass_on"})

    def test_your_own_name_is_not_the_target(self):
        self.assertNotEqual(self.parse("can nina hop on a call", me="nina")["action"], "help")

    def test_how_people_actually_type(self):
        # Typed live on Discord: no apostrophe, so it used to come back as "who knows" instead of a change request.
        change = self.parse("ask omars agent to send the same idempotency key on every retry in charge.py")
        self.assertEqual((change["action"], change["person"], change["path"]), ("change", "omar", "charge.py"))
        curly = self.parse("ask omar’s agent to send the same idempotency key on every retry in charge.py")
        self.assertEqual(curly["person"], "omar")
        self.assertEqual(self.parse("can lucas hop on a call?")["person"], "lucas")

    def test_a_dotfile_is_understood_so_it_can_be_refused(self):
        self.assertEqual(self.parse("ask theo for .env"), {"action": "file", "person": "theo", "path": ".env"})
        self.assertEqual(self.parse("ask theo for his config/.env.local file")["path"], "config/.env.local")
        self.assertEqual(self.parse("ask omar for drafts/charge-fix-wip.py")["path"], "drafts/charge-fix-wip.py")


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.live = Live()
        self.nina, self.omar = "user-a", "user-b"
        self.live.handle(self.nina, "seat nina")
        self.live.handle(self.omar, "seat omar")
        self.live.out.clear()

    def dms(self, user):
        return [o for o in self.live.out if o.kind == "dm" and o.to == user]

    def test_a_real_teammate_answers_with_buttons_and_the_rest_follows(self):
        live = self.live
        self.assertIsNone(live.handle(self.nina, "who knows the payments code?"))
        self.assertIn("Omar owns the Payments API", self.dms(self.nina)[-1].text)
        self.assertTrue(any(o.to == "backchannel" for o in live.out))

        live.handle(self.nina, "ask omar's agent to send the same idempotency key on every retry in charge.py")
        self.assertIn("payments/charge.py", self.dms(self.nina)[-1].text)
        self.assertEqual(self.dms(self.omar), [])  # Omar is asleep: nothing reaches him

        live.out.clear()
        self.assertIsNone(live.handle(self.nina, "skip to 7:00"))
        question = next(o for o in self.dms(self.omar) if o.question)
        self.assertEqual([v for v, _ in question.options], ["approve", "decline"])
        self.assertEqual(live.answer(self.nina, question.question, "approve"), "That question is for someone else.")
        self.assertEqual(live.answer(self.omar, question.question, "approve"), "Approve")
        omar_files = live.net.agents["omar"].ws
        self.assertIn("Idempotency-Key", omar_files.read("payments/charge.py"))
        commit = next(o for o in live.out if "COMMIT" in o.text)
        self.assertIn("sent only to Nina, Theo and Ade", commit.text)

    def test_answers_with_sources_and_a_question_passed_on(self):
        live = self.live
        live.handle(self.nina, "who knows the payments code?")
        live.handle(self.nina, "why would a retry get a 409?")
        answer = self.dms(self.nina)[-1].text
        self.assertIn("docs/payments-api.md", answer)
        self.assertIn("rejects it with a 409", answer)
        live.handle(self.nina, "is the 409 new this week?")
        live.handle(self.nina, "pass it on")
        self.assertIn("who will see it around 7:00 AM", self.dms(self.nina)[-1].text)
        self.assertEqual(self.dms(self.omar), [])  # asleep: it waits for his morning summary

    def test_a_quiet_night_starts_over_for_the_next_visitor(self):
        live, t0 = self.live, time.time() + 5
        live.handle(self.nina, "skip to 7:00", now=t0)
        self.assertEqual(clock.fmt(live.net.t), "7:00 AM")
        reply = live.handle("user-c", "seat priya", now=t0 + Live.QUIET + 1)
        self.assertIn("started over at 1:07 AM", reply)
        self.assertIn("You're Priya", reply)
        self.assertEqual(clock.fmt(live.net.t), "1:07 AM")
        self.assertNotIn("nina", live.seats)

    def test_reset_waits_while_someone_else_is_playing(self):
        live, t0 = self.live, time.time() + 5
        live.handle(self.omar, "status", now=t0)
        self.assertIn("Someone else is playing", live.handle(self.nina, "reset", now=t0 + 100))
        self.assertIn("Started the night over", live.handle(self.nina, "reset", now=t0 + Live.BUSY + 101))

    def test_people_without_a_seat_are_asked_to_take_one(self):
        self.assertIn("Take a seat first", self.live.handle("user-c", "who knows the payments code?"))
        self.assertIn("Someone already has Nina", self.live.handle("user-c", "seat nina"))

    def test_skipping_ahead_reads_in_order(self):
        # The new time used to arrive first, followed by "It's 2:00 AM ... Nina is asleep now".
        self.assertIsNone(self.live.handle(self.nina, "skip to 7:00"))
        texts = [o.text for o in self.dms(self.nina)]
        self.assertIn("2:00 AM in the demo and Nina is asleep now", texts[0])
        self.assertEqual(texts[-1], "It's now 7:00 AM in the demo.")
        self.assertIn("Demo time only moves forward", self.live.handle(self.nina, "skip to 6:00"))


class NinaAndTheoTests(unittest.TestCase):
    """The two seats awake together at 1:07 AM, so both people answer live."""

    def setUp(self):
        self.live = Live()
        self.nina, self.theo = "user-a", "user-c"
        self.live.handle(self.nina, "seat nina")
        self.live.handle(self.theo, "seat theo")
        self.live.out.clear()

    def dms(self, user):
        return [o for o in self.live.out if o.kind == "dm" and o.to == user]

    def test_a_secret_is_refused_and_its_owner_is_told(self):
        self.live.handle(self.nina, "ask theo for .env")
        self.assertIn("can't share .env", self.dms(self.nina)[-1].text)
        self.assertIn("didn't share it or say it exists", self.dms(self.theo)[-1].text)
        self.assertFalse(any(o.question for o in self.live.out))  # Theo isn't even asked
        self.assertFalse(any("GITHUB_TOKEN" in o.text for o in self.live.out))

    def test_code_waits_for_its_owner_and_a_no_keeps_it(self):
        self.live.handle(self.nina, "ask theo for payments/retry.py")
        ask = next(o for o in self.dms(self.theo) if o.question)
        self.assertEqual([v for v, _ in ask.options], ["share", "keep"])
        self.live.out.clear()
        self.assertEqual(self.live.answer(self.theo, ask.question, "keep"), "Keep it private")
        self.assertFalse(any("payments/retry.py]" in o.text for o in self.live.out))  # no file crossed

    def test_a_call_request_quotes_the_question_cleanly(self):
        self.live.handle(self.nina, "can theo hop on a call?")
        ask = next(o for o in self.dms(self.theo) if o.question)
        self.assertIn('"can theo hop on a call?" Hop on a call for 15 minutes now?', ask.text)


if __name__ == "__main__":
    unittest.main()
