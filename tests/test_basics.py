import tempfile
import unittest
from pathlib import Path

from whoknows import clock, diffs
from whoknows.gate import Gate, looks_secret
from whoknows.policy import ASK, AUTO, NEVER, Policy
from whoknows.workspace import OutsideWorkspace, Workspace


class PolicyTests(unittest.TestCase):
    def test_tiers(self):
        p = Policy.from_dict({"auto": ["docs/*", "notes/*"], "never": ["grades/*"]})
        self.assertEqual(p.tier("docs/api.md"), AUTO)
        self.assertEqual(p.tier("./docs/api.md"), AUTO)
        self.assertEqual(p.tier("drafts/fix.py"), ASK)
        self.assertEqual(p.tier("grades/fall.csv"), NEVER)

    def test_secrets_and_personal_files_are_always_private(self):
        p = Policy.from_dict({"auto": ["*"]})
        for path in (".env", "app/.env.local", "config.env", "keys/server.pem", "notes/passwords.txt",
                     "personal/journal.md", "work/personal/diary.md", "aws_credentials"):
            self.assertEqual(p.tier(path), NEVER, path)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(Path(self.tmp.name) / "me")
        self.ws.write("notes/a.md", "one\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_paths_cannot_leave_the_folder(self):
        for bad in ("../x", "/etc/passwd", "notes/../../x"):
            self.assertFalse(self.ws.exists(bad))
            with self.assertRaises(OutsideWorkspace):
                self.ws.read(bad)

    def test_undo_restores_the_previous_version(self):
        self.ws.write("notes/a.md", "two\n")
        self.assertTrue(self.ws.undo("notes/a.md"))
        self.assertEqual(self.ws.read("notes/a.md"), "one\n")

    def test_undo_refuses_when_the_file_changed_since(self):
        self.ws.write("notes/a.md", "two\n")
        (self.ws.root / "notes/a.md").write_text("someone else's edit\n")
        self.assertFalse(self.ws.undo("notes/a.md"))
        self.assertEqual(self.ws.read("notes/a.md"), "someone else's edit\n")


class DiffTests(unittest.TestCase):
    OLD = "a\nb\nc\nd\ne\n"

    def test_stats(self):
        self.assertEqual(diffs.stats(self.OLD, "a\nB\nc\nd\ne\nf\n"), (2, 1))

    def test_touched_and_overlap(self):
        first = diffs.touched(self.OLD, "a\nB\nc\nd\ne\n")
        second = diffs.touched(self.OLD, "a\nb2\nc\nd\ne\n")
        far = diffs.touched(self.OLD, "a\nb\nc\nd\nE\n")
        self.assertEqual(first, [(2, 2)])
        self.assertTrue(diffs.overlaps(first, second))
        self.assertFalse(diffs.overlaps(first, far))

    def test_an_insertion_next_to_an_edit_counts_as_a_collision(self):
        edit = diffs.touched(self.OLD, "a\nB\nc\nd\ne\n")
        insert = diffs.touched(self.OLD, "a\nb\nnew\nc\nd\ne\n")
        self.assertTrue(diffs.overlaps(edit, insert))


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Workspace(Path(self.tmp.name) / "omar")
        self.ws.write("docs/api.md", "POST /charges\n")
        self.ws.write("drafts/fix.py", "wip\n")
        self.ws.write(".env", "KEY=sk_test_FAKEFAKEFAKE00\n")
        self.gate = Gate("omar", self.ws, Policy.from_dict({"auto": ["docs/*"]}))

    def tearDown(self):
        self.tmp.cleanup()

    def share(self, path, text=None):
        text = self.ws.read(path) if text is None else text
        return self.gate.check("delivery", {"shared": [{"path": path, "text": text}]}, "nina")

    def test_auto_files_pass(self):
        self.assertEqual(self.share("docs/api.md"), (True, ""))

    def test_private_files_never_pass(self):
        self.assertEqual(self.share(".env")[1], "private file")

    def test_ask_files_need_the_owner_first(self):
        self.assertFalse(self.share("drafts/fix.py")[0])
        self.gate.approve("drafts/fix.py", "nina")
        self.assertTrue(self.share("drafts/fix.py")[0])

    def test_cannot_forward_files_that_are_not_yours(self):
        self.assertEqual(self.share("someone-elses/notes.md", "hi")[1], "not this person's file")

    def test_cannot_smuggle_other_text_under_a_safe_name(self):
        self.assertEqual(self.share("docs/api.md", "KEY=sk_test_FAKEFAKEFAKE00")[1], "doesn't match the file on disk")

    def test_secrets_in_any_text_are_blocked(self):
        ok, why = self.gate.check("help", {"about": "here you go sk_live_ABCDEFGH12345"}, "nina")
        self.assertEqual((ok, why), (False, "looks like a secret"))
        self.assertTrue(looks_secret("password = hunter2hunter2"))
        self.assertFalse(looks_secret("the password reset page is broken"))

    def test_private_files_are_never_even_mentioned(self):
        ok, _ = self.gate.check("reply", {"mentions": [{"path": ".env"}]}, "nina")
        self.assertFalse(ok)


class ClockTests(unittest.TestCase):
    def test_format_and_windows(self):
        self.assertEqual(clock.fmt(clock.parse("01:07")), "1:07 AM")
        self.assertEqual(clock.fmt(clock.parse("13:30")), "1:30 PM")
        self.assertTrue(clock.in_window(clock.parse("01:00"), "23:40", "07:00"))
        self.assertFalse(clock.in_window(clock.parse("07:00"), "23:40", "07:00"))


if __name__ == "__main__":
    unittest.main()
