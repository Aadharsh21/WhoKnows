#!/usr/bin/env python3
"""Conflict-conscious WhoKnows hardening patch generator.

Usage (from repository root):
  python3 /path/to/WhoKnows_apply_fixes.py           # preview changes + .patch only
  python3 /path/to/WhoKnows_apply_fixes.py --apply   # preview + apply after validating all anchors

Unlike a prebuilt diff tied to one commit, this checks anchors against the
current checkout. It refuses to overwrite target files with local modifications
or to proceed when Claude has edited the same code since this patch was made.
"""
from __future__ import annotations

import argparse
import difflib
import subprocess
import sys
from pathlib import Path

BASE_HEAD = "e56f5aea7a4dcd1df563eff10a9e0c1c928895a5"  # reviewed at preparation time
PATCH_NAME = "WhoKnows_hardening.patch"

HARDENING_TESTS = '''"""Regression tests for versioned approvals and safe automatic edits."""
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
        self.ws.write("drafts/summary.md", "Approved draft\\n")
        self.gate = Gate("omar", self.ws, Policy.from_dict({"ask": ["drafts/*"]}))

    def check_share(self, recipient="nina"):
        return self.gate.check("delivery", {"shared": [{
            "path": "drafts/summary.md", "text": self.ws.read("drafts/summary.md")
        }]}, recipient)

    def test_approval_is_for_one_person_and_one_file_version(self):
        self.gate.approve("drafts/summary.md", "nina")
        self.assertTrue(self.check_share()[0])
        self.assertFalse(self.check_share("theo")[0])
        self.ws.write("drafts/summary.md", "New version that wasn't approved\\n")
        self.assertFalse(self.check_share()[0])
        self.gate.approve("drafts/summary.md", "nina")
        self.assertTrue(self.check_share()[0])

    def test_stale_approval_does_not_allow_quotes(self):
        self.gate.approve("drafts/summary.md", "nina")
        self.ws.write("drafts/summary.md", "Different info\\n")
        allowed, why = self.gate.check("reply", {"answers": [{
            "path": "drafts/summary.md", "text": "Different info"
        }]}, "nina")
        self.assertFalse(allowed)
        self.assertEqual(why, "needs the owner's OK first")

    def test_cannot_approve_missing_file(self):
        with self.assertRaises(ValueError):
            self.gate.approve("drafts/missing.md", "nina")


class AutomaticEditTests(unittest.TestCase):
    BEFORE = "def charge(amount):\\n    return amount\\n"

    def test_python_docstring_change_can_be_trusted(self):
        after = "def charge(amount):\\n    \\\"\\\"\\\"Compute charge.\\\"\\\"\\\"\\n    return amount\\n"
        self.assertTrue(safe_automatic_change("payments/charge.py", self.BEFORE, after))

    def test_executable_python_change_needs_human_approval(self):
        after = "def charge(amount):\\n    return amount * 2\\n"
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
'''

# Anchors intentionally cover only files that Claude had not changed for the last
# round of Discord improvements, plus one isolated Live.answer guard.

def once(text: str, old: str, new: str, path: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{path}: expected one exact anchor, found {n}; Claude may have changed this area. Stop and review.")
    return text.replace(old, new, 1)


def rewrite(path: str, text: str) -> str:
    if path == "whoknows/gate.py":
        text = once(text,
            '        self.approved: set[tuple[str, str]] = set()  # (path, recipient) the owner said yes to\n',
            '        self.approved: dict[tuple[str, str], str] = {}  # (path, recipient) -> approved content digest\n', path)
        text = once(text,
            '        self.blocked: list[dict] = []                 # what this gate stopped\n\n    def check(',
            '''        self.blocked: list[dict] = []                 # what this gate stopped

    def approve(self, path: str, recipient: str) -> None:
        """Approve only the file version the owner actually reviewed."""
        version = self.ws.hash(path)
        if version is None:
            raise ValueError("cannot approve a missing file")
        self.approved[(path, recipient)] = version

    def allowed(self, path: str, recipient: str) -> bool:
        """A later edit invalidates the earlier authorization."""
        return (self.ws.exists(path) and
                self.approved.get((path, recipient)) == self.ws.hash(path))

    def check(''', path)
        old = '            if tier == ASK and (path, recipient) not in self.approved:\n'
        if text.count(old) != 2:
            raise RuntimeError(path + ": expected two ASK checks; source changed")
        text = text.replace(old, '            if tier == ASK and not self.allowed(path, recipient):\n')
    elif path == "whoknows/agent.py":
        text = once(text, 'import re\n', 'import ast\nimport re\n', path)
        text = once(text,
            'SKIP_APPROVAL = re.compile(\n',
            '''def _ast_without_docstrings(source: str) -> str:
    """Return Python structure ignoring comments, formatting, and docstrings."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr) and
                    isinstance(body[0].value, ast.Constant) and
                    isinstance(body[0].value.value, str)):
                del body[0]
    return ast.dump(tree, include_attributes=False)


def safe_automatic_change(path: str, old: str, new: str) -> bool:
    """Auto-apply only prose edits or Python changes with identical executable AST.

    The owner still approves the initial trust rule, and still sees every auto-edit
    with an undo option. Other code types require approval for each edit.
    """
    suffix = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if suffix in ("md", "txt", "rst"):
        return True
    if suffix != "py":
        return False
    try:
        return _ast_without_docstrings(old) == _ast_without_docstrings(new)
    except (SyntaxError, ValueError):
        return False


SKIP_APPROVAL = re.compile(
''', path)
        old = 'in self.gate.approved'
        n = text.count(old)
        if n < 3:
            raise RuntimeError(path + f": expected multiple gate approval checks, found {n}")
        text = text.replace('(path, sender) in self.gate.approved', 'self.gate.allowed(path, sender)')
        text = once(text,
            '                self.gate.approved.add((path, sender))\n',
            '                self.gate.approve(path, sender)\n', path)
        text = once(text,
            '''    def _trusted(self, prop: Proposal) -> dict | None:
        if prop.flags or prop.added + prop.removed > self.SMALL:
            return None
''',
            '''    def _trusted(self, prop: Proposal) -> dict | None:
        if (prop.flags or prop.added + prop.removed > self.SMALL or
                not safe_automatic_change(prop.path, prop.old, prop.new)):
            return None
''', path)
    elif path == "whoknows/live.py":
        text = once(text,
            '''        if self.seats.get(person) != user:
            return "That question is for someone else."
        del self.pending[qid]
''',
            '''        if self.seats.get(person) != user:
            return "That question is for someone else."
        if value not in {v for v, _ in item.options}:
            return "That's an invalid option. Please use one of the approval buttons."
        del self.pending[qid]
''', path)
    elif path == "tests/test_basics.py":
        text = once(text,
            '        self.gate.approved.add(("drafts/fix.py", "nina"))\n',
            '        self.gate.approve("drafts/fix.py", "nina")\n', path)
    elif path == "README.md":
        text = once(text,
            'Every half hour the agents compare who\'s doing what.',
            'At the 1:30 AM team check in the demo, the agents compare who\'s doing what.', path)
    elif path == "docs/design.md":
        text = once(text,
            'the half-hourly team check (duplicates, orphans, bus factor).',
            'an on-demand team check (duplicates, orphans, bus factor).', path)
    elif path == "site/index.html":
        text = once(text,
            'Every half hour the agents post which parts their person owns and knows.',
            'At the team check, agents post which parts their person owns and knows.', path)
    else:
        raise RuntimeError("Unrecognized patch target: " + path)
    return text


TARGETS = (
    "whoknows/gate.py",
    "whoknows/agent.py",
    "whoknows/live.py",
    "tests/test_basics.py",
    "README.md",
    "docs/design.md",
    "site/index.html",
)
NEW_TEST = "tests/test_hardening.py"


def git(*args: str) -> str:
    proc = subprocess.run(["git", *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write validated modifications into the current checkout")
    args = parser.parse_args()
    root = Path.cwd()
    if not (root / ".git").exists() or not (root / "whoknows" / "agent.py").exists():
        parser.error("Run this from the root of your local WhoKnows git clone")
    if "whoknows" not in git("remote", "-v").lower():
        parser.error("Current git repository does not look like WhoKnows")
    touched = set(git("status", "--porcelain", "--untracked-files=no").splitlines())
    dirty = [str(t) for t in TARGETS if any(line[3:] == t for line in touched)]
    if dirty:
        raise RuntimeError("Refusing to overwrite existing uncommitted edits: " + ", ".join(dirty))
    if (root / NEW_TEST).exists():
        raise RuntimeError(NEW_TEST + " already exists; don't overwrite someone else's tests")

    changes = {}
    for rel in TARGETS:
        old = (root / rel).read_text(encoding="utf-8")
        new = rewrite(rel, old)
        if old == new:
            raise RuntimeError("Unexpected no-op on " + rel)
        changes[rel] = (old, new)
    changes[NEW_TEST] = ("", HARDENING_TESTS)

    pieces = []
    for rel, (old, new) in changes.items():
        parts = list(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
            fromfile=("a/" + rel if old else "/dev/null"), tofile="b/" + rel, n=3))
        # Header with a/ and b/ names is accepted by git apply, including /dev/null additions.
        pieces.append("".join(parts))
    patch = "".join(pieces)
    (root / PATCH_NAME).write_text(patch, encoding="utf-8")
    print("Review base:", BASE_HEAD)
    print("Current HEAD:", git("rev-parse", "HEAD"))
    print("Validated", len(changes), "files; generated", PATCH_NAME)
    if not args.apply:
        print("Preview only. Run this again with --apply, or use git apply --check and git apply on the patch.")
        return 0
    for rel, (old, new) in changes.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new, encoding="utf-8")
    print("Changes applied. Run: python3 -m unittest discover -s tests -v")
    print("Then: python3 -m whoknows --export /tmp/whoknows-traces && diff -r /tmp/whoknows-traces site/traces")
    print("Finally: git diff --check && git status")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as e:
        print("No files were overwritten: " + str(e), file=sys.stderr)
        raise SystemExit(1)
