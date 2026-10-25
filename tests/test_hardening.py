"""Regression tests for versioned approvals and safe automatic edits."""
import unittest
import tempfile
from pathlib import Path

from whoknows.gate import Gate
from whoknows.policy import Policy
from whoknows.workspace import Workspace
from whoknows.agent import safe_automatic_change
from whoknows.live import Live


class ApprovalVersionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Workspace(Path(self.tmp.name) / "owner")
        self.ws.write("drafts/summary.md", "Approved draft\n")
        self.gate = Gate("omar", self.ws, Policy.from_dict({"ask": ["drafts/*"]}))

    def check_share(self, recipient="nina"):
        return self.gate.check("delivery", {"shared": [{
            "path": "drafts/summary.md", "text": self.ws.read("drafts/summary.md")
        }]}, recipient)

    def test_approval_is_for_one_person_and_one_file_version(self):
        self.gate.approve("drafts/summary.md", "nina")
        self.assertTrue(self.check_share()[0])
        self.assertFalse(self.check_share("theo")[0])
        self.ws.write("drafts/summary.md", "New version that wasn't approved\n")
        self.assertFalse(self.check_share()[0])
        self.gate.approve("drafts/summary.md", "nina")
        self.assertTrue(self.check_share()[0])

    def test_stale_approval_does_not_allow_quotes(self):
        self.gate.approve("drafts/summary.md", "nina")
        self.ws.write("drafts/summary.md", "Different info\n")
        allowed, why = self.gate.check("reply", {"answers": [{
            "path": "drafts/summary.md", "text": "Different info"
        }]}, "nina")
        self.assertFalse(allowed)
        self.assertEqual(why, "needs the owner's OK first")

    def test_cannot_approve_missing_file(self):
        with self.assertRaises(ValueError):
            self.gate.approve("drafts/missing.md", "nina")


class AutomaticEditTests(unittest.TestCase):
    BEFORE = "def charge(amount):\n    return amount\n"

    def test_python_docstring_change_can_be_trusted(self):
        after = "def charge(amount):\n    \"\"\"Compute charge.\"\"\"\n    return amount\n"
        self.assertTrue(safe_automatic_change("payments/charge.py", self.BEFORE, after))

    def test_executable_python_change_needs_human_approval(self):
        after = "def charge(amount):\n    return amount * 2\n"
        self.assertFalse(safe_automatic_change("payments/charge.py", self.BEFORE, after))

    def test_javascript_changes_need_human_approval(self):
        self.assertFalse(safe_automatic_change("app/index.js", "const x = 1;", "const x = 2;"))

    def test_invalid_python_does_not_auto_apply(self):
        self.assertFalse(safe_automatic_change("payments/charge.py", self.BEFORE, "def charge(:"))


class LiveApprovalTests(unittest.TestCase):
    def test_invalid_choice_does_not_consume_pending_approval(self):
        live = Live()
        live.handle("nina-user", "seat nina")
        live.handle("omar-user", "seat omar")
        live.out.clear()
        live.handle("nina-user", "ask omar's agent to send the same idempotency key on every retry in charge.py")
        live.handle("nina-user", "skip to 7:00")
        qid = next(qid for qid, (person, item) in live.pending.items()
                   if person == "omar" and {v for v, _ in item.options} == {"approve", "decline"})
        self.assertIn("invalid", live.answer("omar-user", qid, "definitely-yes").lower())
        self.assertIn(qid, live.pending)
        self.assertEqual(live.answer("omar-user", qid, "approve"), "Approve")


if __name__ == "__main__":
    unittest.main()
