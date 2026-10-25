"""One person's agent.

It answers other agents for its person, shares only what its person's rules
allow, and asks its person before anything that changes their files or spends
their time. While its person sleeps it never wakes them: questions wait, and
news goes into a morning summary.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import Callable

from . import clock, diffs
from .cards import RANK, part_for_path, parts_in
from . import search
from .gate import Gate, looks_secret
from .policy import AUTO, NEVER
from .workspace import digest

def _ast_without_docstrings(source: str) -> str:
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
    r"(?i)without (?:asking|approval|review)|skip (?:the |your |their )?(?:approval|review)"
    r"|auto-?apply|don'?t ask|no need to ask")


def join_names(names) -> str:
    names = list(names)
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


@dataclass
class Proposal:
    """A change someone asked for, drafted on the owner's side and waiting for the owner."""
    id: str
    path: str
    requester: str
    intent_key: str
    intent: str
    base: str
    old: str
    new: str
    ranges: list
    added: int
    removed: int
    flags: list = field(default_factory=list)
    status: str = "pending"   # pending, applied, declined, not_picked, obsolete, undone
    rivals: set = field(default_factory=set)
    redrafted: bool = False


@dataclass
class Ask:
    """A question for the agent's person."""
    key: str
    prompt: str
    options: list
    on_answer: Callable[[str], None]
    order: int = 5
    extra: dict = field(default_factory=dict)


class PersonalAgent:
    def __init__(self, person: dict, workspace, policy, card, team: dict, drafter):
        self.person = person
        self.id = person["id"]
        self.ws = workspace
        self.policy = policy
        self.card = card
        self.team = team
        self.parts = team["parts"]
        self.drafter = drafter
        self.gate = Gate(self.id, workspace, policy)
        self.net = None
        self.holders: dict[str, set] = {}       # my file -> people whose agents hold a copy
        self.copies: dict[tuple, str] = {}       # (owner, path) -> text I was given
        self.requested: set[tuple] = set()       # (owner, path) changes my person asked for
        self.proposals: dict[str, Proposal] = {}  # changes others asked for, to my files
        self.time_asks: list[dict] = []
        self.waiting: list[Ask] = []
        self.digest: list[str] = []
        self.alerts: list[str] = []
        self.receipts: list[str] = []            # what I did for my person without asking, while they slept
        self.shared_unasked: set[str] = set()     # files behind those receipts
        self.quotes: dict[tuple, str] = {}        # (owner, path) -> passage another agent quoted to me
        self.trust: list[dict] = []               # teammates whose small changes my person lets through
        self.last_hits: list[str] = []            # who answered my person's last "who knows"
        self.last_whys: dict[str, str] = {}       # and the one line each gave as the reason
        self._seq = 0
        self._keys: dict[str, int] = {}

    # ---------------------------------------------------------------- basics

    @property
    def first(self) -> str:
        return self.person["name"].split()[0]

    def name(self, pid: str) -> str:
        return self.net.name(pid)

    def awake(self, t: int | None = None) -> bool:
        t = self.net.t if t is None else t
        return not any(clock.in_window(t, s, e) for s, e in self.person.get("sleep", ()))

    def wakes_at(self) -> str:
        for s, e in self.person.get("sleep", ()):
            if clock.in_window(self.net.t, s, e):
                return clock.fmt(clock.parse(e))
        return clock.fmt(self.net.t)

    def eta(self) -> str | None:
        return None if self.awake() else f"around {self.wakes_at()}"

    # ------------------------------------------------------ talking to my person

    def tell(self, text: str, short: str | None = None, **extra) -> None:
        """Message my person now, or save it for their morning summary if they're asleep."""
        if self.awake():
            self.net.phone(self.id, text, **extra)
        else:
            self.digest.append(f"{clock.fmt(self.net.t)}: {short or text}")

    def _key(self, what: str) -> str:
        """A fresh name for a question to my person: omar_fix, then omar_fix_2, and so on."""
        n = self._keys[what] = self._keys.get(what, 0) + 1
        return f"{self.id}_{what}" if n == 1 else f"{self.id}_{what}_{n}"

    def ask(self, key: str, prompt: str, options: list, on_answer, order: int = 5, **extra) -> None:
        """Ask my person something. If they're asleep, it waits until they wake up."""
        item = Ask(key, prompt, options, on_answer, order, extra)
        if self.awake():
            self.net.after(lambda: self._answer(item))
        else:
            self.waiting.append(item)

    def _answer(self, item: Ask) -> None:
        # The network decides how the question reaches the person: the demo answers
        # at once with the scripted choice, the Discord bot shows buttons and waits.
        self.net.ask_person(self.id, item)

    def _flag(self, text: str) -> None:
        if self.awake():
            self.net.phone(self.id, text, tone="alert")
        else:
            self.alerts.append(text)

    def _receipt(self, text: str, files=()) -> None:
        """Keep a record of anything done for my person without asking them, while they slept."""
        if not self.awake():
            self.receipts.append(f"{clock.fmt(self.net.t)}: {text}")
            self.shared_unasked.update(files)

    def wake(self) -> None:
        if self.alerts:
            self.net.phone(self.id, "Heads up from last night:\n" + "\n".join(f"- {a}" for a in self.alerts),
                           tone="alert")
            self.alerts = []
        if self.digest:
            self.net.phone(self.id, "While you were asleep:\n" + "\n".join(f"- {d}" for d in self.digest),
                           tone="digest")
            self.digest = []
        if self.receipts:
            self.net.phone(self.id, "What I did for you while you slept, without asking:\n"
                           + "\n".join(f"- {r}" for r in self.receipts), tone="receipts")
            self.receipts = []
            if self.shared_unasked:
                files = sorted(self.shared_unasked)
                self.shared_unasked = set()

                def answer(choice, files=files):
                    if choice == "tighten":
                        self.policy.ask_first.update(files)
                        self.tell(f"Done. I'll ask you before sharing {join_names(files)} from now on.")

                self.waiting.append(Ask(self._key("receipts"),
                                        f"I shared {join_names(files)} because your rules say it's fine. Keep it that way?",
                                        [("ok", "Keep it that way"), ("tighten", "Ask me first next time")],
                                        answer, order=9))
        for path in sorted({p.path for p in self.proposals.values() if p.status == "pending"}):
            self._review_changes(path)
        waiting, self.waiting = sorted(self.waiting, key=lambda a: a.order), []
        for item in [w for w in waiting if w.order < 7]:
            self._answer(item)
        self._review_time()
        for item in [w for w in waiting if w.order >= 7]:
            self._answer(item)

    # ------------------------------------------------- answering other agents

    def handle(self, kind: str, body: dict, sender: str) -> dict:
        handler = getattr(self, f"on_{kind}", None)
        if handler is None:
            return {"status": "unsupported"}
        return handler(body or {}, sender)

    def on_who_knows(self, body, sender):
        claim = self.card.best_for(parts_in(body.get("question", ""), self.parts))
        if not claim:
            return {"answer": "no"}
        reply = {"answer": claim.level, "part": claim.part, "why": claim.why}
        if not self.awake():
            reply["status"] = f"asleep until about {self.wakes_at()}"
            part = self._part_name(claim.part)
            said = {"owner": f"you own the {part}", "touched": f"you worked on the {part} recently",
                    "claims": f"you're on the {part}"}[claim.level]
            self._receipt(f"told {self.name(sender)}'s agent {said}")
        return reply

    def on_question(self, body, sender):
        """Answer from my person's own shareable files, quoting the exact passage and naming the file."""
        question = body.get("question", "")
        if body.get("hand_over"):
            # The notes didn't answer it, so the question goes to my person, at a decent hour.
            who = self.name(sender)
            self.tell(f"{who} asked: \"{question}\" Your shareable notes don't answer it. Reply to {who} when you can.",
                      short=f"{who} asked: \"{question}\" (your notes don't answer it)")
            return {"handed": True, "eta": self.eta()}
        want = search.terms(question)
        need = 1 if len(want) <= 2 else 2
        topics = set(parts_in(question, self.parts))
        answers, mentions = [], []
        for path in self.ws.files():
            tier = self.policy.tier(path)
            if tier == NEVER:
                continue
            if tier == AUTO or self.gate.allowed(path, sender):
                passage, score = search.best_passage(self.ws.read(path), want)
                if passage and score >= need:
                    answers.append({"path": path, "text": passage, "score": score})
            elif part_for_path(path, self.parts) in topics:
                mentions.append({"path": path, "needs": f"{self.first}'s OK"})
        answers = sorted(answers, key=lambda a: -a["score"])[:2]
        for a in answers:
            self.holders.setdefault(a["path"], set()).add(sender)
            self._receipt(f"answered {self.name(sender)}'s question from your {a['path']}", files=[a["path"]])
        if mentions:
            self._receipt(f"told {self.name(sender)}'s agent you have {join_names(m['path'] for m in mentions)}, "
                          f"which need your OK")
        return {"answers": answers, "mentions": mentions}

    def on_fetch(self, body, sender):
        part = body.get("part")
        wanted = {part} if part else {c.part for c in self.card.claims if c.level == "owner"}
        shared, mentions = [], []
        for path in self.ws.files():
            if part_for_path(path, self.parts) not in wanted:
                continue
            tier = self.policy.tier(path)
            if tier == NEVER:
                continue
            if tier == AUTO or self.gate.allowed(path, sender):
                shared.append(self._file(path, sender))
            else:
                mentions.append({"path": path, "needs": f"{self.first}'s OK"})
        if shared:
            paths = [f["path"] for f in shared]
            self._receipt(f"shared your {join_names(paths)} with {self.name(sender)}", files=paths)
        return {"shared": shared, "mentions": mentions}

    def on_share_request(self, body, sender):
        path = body.get("path", "")
        who = self.name(sender)
        if not self.ws.exists(path):
            owner = next((o for (o, p) in self.copies if p == path), None)
            if owner:
                self.tell(f"{who}'s agent asked me to pass on {self.name(owner)}'s {path}. "
                          f"I don't forward other people's files, so I pointed it to {self.name(owner)}'s agent.",
                          short=f"{who}'s agent asked me to forward {self.name(owner)}'s {path}. I said no.")
                return {"status": "not_mine", "owner": self.name(owner)}
            return {"status": "unavailable"}
        tier = self.policy.tier(path)
        if tier == NEVER:
            self._flag(f"{who}'s agent asked for your {path} at {clock.fmt(self.net.t)}. "
                       f"I didn't share it or say it exists.")
            return {"status": "unavailable"}
        if tier == AUTO or self.gate.allowed(path, sender):
            if tier == AUTO:
                self._receipt(f"shared your {path} with {who}", files=[path])
            return {"shared": [self._file(path, sender)]}

        def answer(choice):
            if choice == "share":
                self.gate.approve(path, sender)
                self.net.send(self.id, sender, "delivery", {"shared": [self._file(path, sender)]})
            else:
                self.net.send(self.id, sender, "delivery", {"kept": path})

        self.ask(self._key("share"), f"{who} asked for your {path}. Share it?",
                 [("share", "Share it"), ("keep", "Keep it private")], answer, order=6)
        return {"status": "queued", "eta": self.eta()}

    def on_help(self, body, sender):
        who = self.name(sender)
        if not self.awake():
            return {"status": "asleep", "eta": self.eta()}
        minutes = int(body.get("minutes", 15))
        about = body.get("about", "")
        part = body.get("part")

        def answer(choice):
            reply = {"answer": choice}
            if choice != "yes" and part:
                notes = [p for p in self.ws.files()
                         if self.policy.tier(p) == AUTO and part_for_path(p, self.parts) == part]
                reply["shared"] = [self._file(p, sender) for p in notes]
            self.net.send(self.id, sender, "help_answer", reply)

        self.ask(self._key("help"), f"{who}'s agent: \"{about}.\" Hop on a call for {minutes} minutes now?",
                 [("yes", "Yes, call now"), ("no", "Not now")], answer)
        return {"status": "asking"}

    def on_help_answer(self, body, sender):
        who = self.name(sender)
        if body.get("answer") == "yes":
            self.tell(f"{who} said yes and is free for a call now.")
        else:
            files = body.get("shared", [])
            for f in files:
                self.copies[(sender, f["path"])] = f["text"]
            sent = f" {who}'s agent sent {join_names(f['path'] for f in files)} instead." if files else ""
            self.tell(f"{who} can't right now.{sent}")
        return {"status": "ok"}

    def _resolve(self, path: str) -> str:
        """Accept a bare file name ("charge.py") when it matches exactly one shareable file."""
        if self.ws.exists(path) or "/" in path:
            return path
        matches = [p for p in self.ws.files() if p.rsplit("/", 1)[-1] == path and self.policy.tier(p) != NEVER]
        return matches[0] if len(matches) == 1 else path

    def on_change(self, body, sender):
        path = self._resolve(body.get("path", ""))
        intent = body.get("intent", "")
        who = self.name(sender)
        if not self.ws.exists(path) or self.policy.tier(path) == NEVER:
            if self.ws.exists(path):
                self._flag(f"{who}'s agent tried to change your {path}. Private files can't be changed by anyone else.")
            return {"status": "unavailable"}
        old = self.ws.read(path)
        new = self.drafter.draft(old, body.get("intent_key"), intent, path=path)
        if new is None:
            return {"status": "cant_draft"}
        if new == old:
            return {"status": "no_change"}
        self._seq += 1
        added, removed = diffs.stats(old, new)
        prop = Proposal(f"{self.id}-{self._seq}", path, sender, body.get("intent_key") or "", intent,
                        digest(old), old, new, diffs.touched(old, new), added, removed)
        prop.flags = self._red_flags(prop)
        if any("approval" in f for f in prop.flags):
            self._flag(f"{who}'s agent sent a change to your {path} and asked me to skip your approval. "
                       f"I ignored that part. You'll see the change and decide.")
        rivals = [q for q in self._pending(path) if q.base == prop.base and diffs.overlaps(q.ranges, prop.ranges)]
        for q in rivals:
            q.rivals.add(prop.id)
            prop.rivals.add(q.id)
        self.proposals[prop.id] = prop
        for requester in sorted({q.requester for q in rivals} - {sender}):
            self.net.after(lambda r=requester: self.net.send(
                self.id, r, "change_status", {"status": "collision", "path": path, "with": [who]}))
        rule = None if rivals else self._trusted(prop)
        if rule:
            self.net.after(lambda: self._apply_by_rule(prop, rule))
            return {"status": "auto", "id": prop.id, "path": path, "added": added, "removed": removed}
        if self.awake():
            self.net.after(lambda: self._review_changes(path))
        reply = {"status": "queued", "id": prop.id, "path": path, "eta": self.eta(), "added": added, "removed": removed}
        if rivals:
            reply["collides_with"] = sorted({self.name(q.requester) for q in rivals} - {who})
        return reply

    def on_change_status(self, body, sender):
        who, path, status = self.name(sender), body.get("path"), body.get("status")
        picked = body.get("picked")
        texts = {
            "not_picked": (f"{who} went with {picked}'s change to {path}, so yours was closed." if picked
                           else f"{who} didn't take any of the changes to {path}, including yours."),
            "declined": f"{who} said no to your change to {path}.",
            "redrafted": (f"{who}'s {path} changed after you asked, so {who}'s agent rewrote your change "
                          f"against the new version. {who} will see it again."),
            "obsolete": f"Your change to {path} isn't needed anymore. The current version already does it.",
            "collision": (f"Heads up: {join_names(body.get('with', []))} also asked {who} to change the same lines "
                          f"of {path}. {who} will see both and pick one."),
        }
        if status in texts:
            self.tell(texts[status])
        return {"status": "ok"}

    def on_time(self, body, sender):
        self.time_asks.append({"from": sender, "minutes": int(body.get("minutes", 10)),
                               "before": clock.parse(body.get("before", "23:59")), "about": body.get("about", "")})
        if self.awake():
            self.net.after(self._review_time)
        return {"status": "queued", "eta": self.eta()}

    def on_slot(self, body, sender):
        who = self.name(sender)
        if body.get("declined"):
            self.tell(f"{who} has no time before the deadline. Send your question in writing and {who}'s agent "
                      f"will pass it on.")
        else:
            people = join_names([who] + list(body.get("with", [])))
            self.tell(f"You're booked with {people} from {body['start']} to {body['end']}.",
                      short=f"booked with {people}, {body['start']} to {body['end']}")
        return {"status": "ok"}

    def on_delivery(self, body, sender):
        who = self.name(sender)
        for f in body.get("shared", []):
            self.copies[(sender, f["path"])] = f["text"]
            self.tell(f"{who} shared {f['path']} with you.")
        if body.get("kept"):
            self.tell(f"{who} kept {body['kept']} private.")
        return {"status": "ok"}

    def on_watch_check(self, body, sender):
        """Does my person need to see a change to this file? The other agent only learns yes or no."""
        reason = self._interest(sender, body.get("path", ""), body.get("part"))
        return {"answer": "yes" if reason else "no"}

    def on_commit(self, body, sender):
        c = body.get("commit", {})
        path = c.get("path", "")
        owner = self.name(sender)
        reason = self._interest(sender, path, c.get("part")) or "you're on the team"
        requested = [r for r in c.get("requested_by") or []]
        size = f"+{c.get('added', 0)} -{c.get('removed', 0)}"
        if c.get("undo_of") == self.id:
            self.tell(f"{owner} undid your change to {path} ({size}).",
                      short=f"{owner} undid your change to {path}", card=c, reason=reason)
        elif self.id in requested:
            if not c.get("by_rule"):  # a change saved under a trust rule was already confirmed to the requester
                self.tell(f"{owner} approved your change to {path} ({size}): \"{c.get('message', '')}\"",
                          short=f"{owner} approved your change to {path} ({size})", card=c, reason=reason)
        else:
            if requested and c.get("by_rule"):
                by = f"Requested by {join_names(self.name(r) for r in requested)}, saved under a rule {owner} set."
            elif requested:
                by = f"Requested by {join_names(self.name(r) for r in requested)}, approved by {owner}."
            else:
                by = f"Edited by {owner}."
            self.tell(f"New change to {owner}'s {path} ({size}): \"{c.get('message', '')}\" {by} "
                      f"You're seeing this because {reason}.",
                      short=f"{owner}'s {path} changed ({size}): {c.get('message', '')}",
                      card=c, reason=reason)
        if (sender, path) in self.copies or (sender, path) in self.quotes:
            self.net.after(lambda: self._refresh(sender, path))
        return {"status": "seen"}

    # --------------------------------------------- things my person asks for

    def find_who_knows(self, question: str) -> list:
        answers = {other: self.net.send(self.id, other, "who_knows", {"question": question})
                   for other in self.net.others(self.id)}
        hits = sorted(((o, r) for o, r in answers.items() if r.get("answer") in RANK),
                      key=lambda item: -RANK[item[1]["answer"]])
        self.last_hits = [o for o, _ in hits]
        self.last_whys = {o: r.get("why", "") for o, r in hits}
        if not hits:
            self.tell("Nobody's agent knows of anyone working on that yet.")
            return []
        lines = [f"{self.name(o)} {r['why']} ({r.get('status', 'awake')})." for o, r in hits]
        rest = len(answers) - len(hits)
        self.tell(" ".join(lines) + (f" The other {rest} said no." if rest else ""))
        return hits

    def ask_question(self, question: str, people=None) -> list:
        """Ask the people who know (or everyone) and collect answers quoted from their shareable notes."""
        people = list(people or self.last_hits or self.net.others(self.id))
        found, mentions = [], {}
        for other in people:
            r = self.net.send(self.id, other, "question", {"question": question})
            for a in r.get("answers", []):
                found.append((other, a))
                self.quotes[(other, a["path"])] = a["text"]
            if r.get("mentions"):
                mentions[other] = [m["path"] for m in r["mentions"]]
        bits = []
        if found:
            bits.append("Answers from your teammates' own notes:")
            bits += [f"- {self.name(o)}'s {a['path']}: \"{' '.join(a['text'].split())}\"" for o, a in found]
        else:
            bits.append(f"Nothing in {join_names(self.name(p) for p in people)}'s shareable notes answers that.")
        text = "\n".join(bits)
        for other, paths in mentions.items():
            verb = "needs" if len(paths) == 1 else "need"
            text += f"\n{self.name(other)} also has {join_names(paths)}, which {verb} {self.name(other)}'s OK."
        self.tell(text)
        return found

    def rank(self, question: str, people) -> list:
        """Order the people who know a part by how well their reason matches the question. A question
        about the retry change goes first to whoever made the retry change. Ties keep the who-knows order."""
        want = search.terms(question)
        return sorted(people, key=lambda p: -len(want & search.terms(self.last_whys.get(p, ""))))

    def pass_on(self, question: str, people=None) -> list:
        """When the notes don't answer it, hand the question to the person most likely to know. Their agent
        shows it to them now if they're awake, or in their morning summary if not. Never at night."""
        people = self.rank(question, list(people or self.last_hits))[:1]
        handed = []
        for other in people:
            r = self.net.send(self.id, other, "question", {"question": question, "hand_over": True})
            if r.get("handed"):
                handed.append((other, r.get("eta")))
        if handed:
            self.tell(" ".join(f"I passed your question to {self.name(o)}"
                               + (f", who will see it {eta}." if eta else ", who is awake.") for o, eta in handed))
        return handed

    def fetch_from(self, owner: str, part: str, look_for=()) -> dict:
        r = self.net.send(self.id, owner, "fetch", {"part": part})
        who = self.name(owner)
        shared = r.get("shared", [])
        bits = []
        if shared:
            for f in shared:
                self.copies[(owner, f["path"])] = f["text"]
            bits.append(f"{who}'s agent sent {join_names(f['path'] for f in shared)}.")
            for f in shared:
                line = next((ln.strip() for ln in f["text"].splitlines()
                             if any(w.lower() in ln.lower() for w in look_for)), None)
                if line:
                    bits.append(f"It says: \"{line}\"")
        mentions = [m["path"] for m in r.get("mentions", [])]
        if mentions:
            verb = "needs" if len(mentions) == 1 else "need"
            bits.append(f"{who} also has {join_names(mentions)}, which {verb} {who}'s OK.")
        self.tell(" ".join(bits) or f"{who}'s agent had nothing it could share.")
        return r

    def request_file(self, owner: str, path: str) -> dict:
        r = self.net.send(self.id, owner, "share_request", {"path": path})
        who = self.name(owner)
        if r.get("shared"):
            for f in r["shared"]:
                self.copies[(owner, f["path"])] = f["text"]
            self.tell(f"Got {path} from {who}'s agent.")
        elif r.get("status") == "queued":
            when = f" {who} will see it {r['eta']}." if r.get("eta") else ""
            self.tell(f"I asked {who} for {path}.{when}")
        else:
            self.tell(f"{who}'s agent can't share {path}.")
        return r

    def ask_for_help(self, helper: str, minutes: int, about: str, part: str | None = None) -> dict:
        r = self.net.send(self.id, helper, "help", {"minutes": minutes, "about": about, "part": part})
        if r.get("status") == "asleep":
            self.tell(f"{self.name(helper)} is asleep until {r['eta']}. I didn't wake them.")
        return r

    def request_change(self, owner: str, path: str, intent_key: str, intent: str) -> dict:
        self.requested.add((owner, path))
        r = self.net.send(self.id, owner, "change", {"path": path, "intent_key": intent_key, "intent": intent})
        who = self.name(owner)
        status = r.get("status")
        if status == "queued":
            path = r.get("path", path)
            self.requested.add((owner, path))
            when = f" {who} will see it {r['eta']}." if r.get("eta") else ""
            clash = (f" Heads up: {join_names(r['collides_with'])} asked to change the same lines, "
                     f"so {who} will see both and pick one." if r.get("collides_with") else "")
            self.tell(f"Sent your change to {who}'s agent ({path}, +{r['added']} -{r['removed']}). "
                      f"Nothing changes until {who} approves.{when}{clash}")
        elif status == "auto":
            path = r.get("path", path)
            self.requested.add((owner, path))
            self.tell(f"{who} lets your small changes to {path.rsplit('/', 1)[0]}/ through without asking, so it's "
                      f"saved already (+{r['added']} -{r['removed']}). {who} still gets the commit and can undo it.")
        elif status == "no_change":
            self.tell(f"{who}'s {path} already does that.")
        else:
            self.tell(f"{who}'s agent can't take that change to {path}.")
        return r

    def request_time(self, owner: str, minutes: int, before: str, about: str) -> dict:
        r = self.net.send(self.id, owner, "time", {"minutes": minutes, "before": before, "about": about})
        who = self.name(owner)
        when = f" {who} will see it {r['eta']}." if r.get("eta") else ""
        self.tell(f"Asked {who}'s agent for {minutes} minutes before {clock.fmt(clock.parse(before))}.{when}")
        return r

    def edit_own(self, path: str, intent_key: str, message: str):
        """My person changed one of their own files. Send the change to whoever needs it."""
        old = self.ws.read(path)
        new = self.drafter.draft(old, intent_key, message, path=path)
        if new is None or new == old:
            return None
        self.ws.write(path, new)
        return self._publish(path, old, new, message)

    def report(self, part: str, status: str, detail: str = "") -> None:
        self.net.board_update(self.id, part, status, detail)

    # -------------------------------------------------- reviewing changes

    def _pending(self, path: str) -> list:
        return [p for p in self.proposals.values() if p.path == path and p.status == "pending"]

    def _group(self, prop: Proposal) -> list:
        seen, todo = {prop.id}, [prop]
        while todo:
            for rid in todo.pop().rivals:
                rival = self.proposals.get(rid)
                if rival and rival.status == "pending" and rid not in seen:
                    seen.add(rid)
                    todo.append(rival)
        return sorted((self.proposals[i] for i in seen), key=lambda p: p.id)

    def _red_flags(self, prop: Proposal) -> list:
        flags = []
        if SKIP_APPROVAL.search(prop.intent):
            flags.append("asked to skip your approval (ignored)")
        total = max(1, len(prop.old.splitlines()))
        if prop.removed >= 5 or prop.removed > total / 2:
            flags.append(f"removes {prop.removed} of {total} lines")
        if looks_secret(prop.new) and not looks_secret(prop.old):
            flags.append("adds something that looks like a key")
        return flags

    def _review_changes(self, path: str) -> None:
        current = self.ws.hash(path)
        for prop in self._pending(path):
            if prop.base != current:
                self._redraft(prop)
        done = set()
        for prop in self._pending(path):
            if prop.id in done or prop.status != "pending":
                continue
            group = self._group(prop)
            done.update(p.id for p in group)
            if len(group) == 1:
                self._ask_one(prop)
            else:
                self._ask_pick(group)

    def _ask_one(self, prop: Proposal) -> None:
        who = self.name(prop.requester)
        again = " (rewritten for the current version)" if prop.redrafted else ""
        warn = f" Warning: {'; '.join(prop.flags)}." if prop.flags else ""
        prompt = (f"{who} wants to change your {prop.path}{again} (+{prop.added} -{prop.removed}): "
                  f"\"{prop.intent}\".{warn} Approve?")
        self.ask(self._key("fix"), prompt, [("approve", "Approve"), ("decline", "Decline")],
                 lambda choice: self._decide_one(prop, choice), order=1,
                 diffs={prop.requester: diffs.unified(prop.old, prop.new, prop.path)}, flags=prop.flags)

    def _ask_pick(self, group: list) -> None:
        path = group[0].path
        lines = " ".join(f"{self.name(p.requester)}'s: \"{p.intent}\" (+{p.added} -{p.removed})." for p in group)
        prompt = f"{len(group)} changes to your {path} touch the same lines. {lines} Which one?"
        options = [(p.requester, f"{self.name(p.requester)}'s change") for p in group] + [("neither", "Neither")]
        self.ask(self._key("fix"), prompt, options, lambda choice: self._decide_pick(group, choice), order=1,
                 diffs={p.requester: diffs.unified(p.old, p.new, p.path) for p in group},
                 flags=sorted({f for p in group for f in p.flags}))

    def _decide_one(self, prop: Proposal, choice: str) -> None:
        if prop.status != "pending":
            return
        if choice == "approve":
            self._apply(prop)
        else:
            prop.status = "declined"
            self.net.send(self.id, prop.requester, "change_status", {"status": "declined", "path": prop.path})

    def _decide_pick(self, group: list, choice: str) -> None:
        chosen = next((p for p in group if p.requester == choice and p.status == "pending"), None)
        if chosen:
            self._apply(chosen)
        for p in group:
            if p is not chosen and p.status == "pending":
                p.status = "not_picked"
                self.net.send(self.id, p.requester, "change_status",
                              {"status": "not_picked", "path": p.path,
                               "picked": self.name(chosen.requester) if chosen else None})

    def _apply(self, prop: Proposal, asked: bool = True) -> dict | None:
        if self.ws.hash(prop.path) != prop.base:
            self._redraft(prop)
            if prop.status == "pending":
                self.net.after(lambda: self._review_changes(prop.path))
            return None
        self.ws.write(prop.path, prop.new)
        prop.status = "applied"
        commit = self._publish(prop.path, prop.old, prop.new, prop.intent, requested_by=[prop.requester],
                               by_rule=not asked)
        if asked:
            sent = [self.name(p) for p in commit["to"]]
            self.tell(f"Saved {self.name(prop.requester)}'s change to {prop.path}. "
                      f"Sent it to {join_names(sent) or 'nobody else'}, the people it affects.")
            self._offer_trust(prop)
        # Anything else still waiting on this file was written against the old version.
        for other in self._pending(prop.path):
            if other.id not in prop.rivals:
                self._redraft(other)
        return commit

    # ----------------------------------------------------------- earned trust

    SMALL = 5  # lines added plus removed

    def _scope(self, path: str) -> str:
        return path.rsplit("/", 1)[0] + "/*" if "/" in path else path

    def _trusted(self, prop: Proposal) -> dict | None:
        if (prop.flags or prop.added + prop.removed > self.SMALL or
                not safe_automatic_change(prop.path, prop.old, prop.new)):
            return None
        return next((rule for rule in self.trust
                     if rule["requester"] == prop.requester and fnmatchcase(prop.path, rule["glob"])), None)

    def _offer_trust(self, prop: Proposal) -> None:
        """After my person approves a small, clean change, offer to let that teammate's small changes through."""
        if prop.flags or prop.added + prop.removed > self.SMALL or self._trusted(prop):
            return
        who, glob = self.name(prop.requester), self._scope(prop.path)
        folder = glob[:-1]

        def answer(choice):
            if choice == "yes":
                self.trust.append({"requester": prop.requester, "glob": glob, "since": clock.fmt(self.net.t)})

        self.ask(self._key("trust"),
                 f"That was a small, clean change. Let {who}'s small changes to {folder} ({self.SMALL} lines or fewer, "
                 f"nothing flagged) go through without asking you? You'd still get every commit, and undo is one tap.",
                 [("yes", f"Yes, small ones from {who}"), ("no", "Keep asking me")], answer, order=2)

    def _apply_by_rule(self, prop: Proposal, rule: dict) -> None:
        commit = self._apply(prop, asked=False)
        if not commit:
            return
        who = self.name(prop.requester)
        text = (f"Saved {who}'s change to {prop.path} without asking (+{prop.added} -{prop.removed}): "
                f"\"{prop.intent}\", under the rule you set at {rule['since']}. Keep it?")
        self._receipt(f"saved {who}'s small change to {prop.path} under your rule")

        def answer(choice):
            if choice == "undo":
                self.undo_last(prop.path, undoing=prop)

        self.ask(self._key("undo"), text, [("keep", "Keep it"), ("undo", "Undo it")], answer, order=3,
                 diffs={prop.requester: diffs.unified(prop.old, prop.new, prop.path)})

    def undo_last(self, path: str, undoing: Proposal | None = None) -> bool:
        """Put the file back the way it was. The undo goes out as a commit to the same kind of audience."""
        before = self.ws.read(path) if self.ws.exists(path) else ""
        if not self.ws.undo(path):
            return False
        after = self.ws.read(path) if self.ws.exists(path) else ""
        if undoing:
            undoing.status = "undone"
            message = f"Undo {self.name(undoing.requester)}'s change: {undoing.intent}"
        else:
            message = f"Undo the last change to {path}"
        self._publish(path, before, after, message, undo_of=undoing.requester if undoing else None)
        return True

    def _redraft(self, prop: Proposal) -> None:
        current = self.ws.read(prop.path) if self.ws.exists(prop.path) else None
        new = self.drafter.draft(current, prop.intent_key, prop.intent, path=prop.path) if current is not None else None
        if new is None or new == current:
            prop.status = "obsolete"
            self.net.send(self.id, prop.requester, "change_status", {"status": "obsolete", "path": prop.path})
            return
        prop.old, prop.new, prop.base = current, new, digest(current)
        prop.ranges = diffs.touched(current, new)
        prop.added, prop.removed = diffs.stats(current, new)
        prop.flags = self._red_flags(prop)
        prop.redrafted = True
        prop.rivals = {r for r in prop.rivals if self.proposals[r].status == "pending"}
        self.net.send(self.id, prop.requester, "change_status", {"status": "redrafted", "path": prop.path})

    # ------------------------------------------------------------- commits

    def _interest(self, owner: str, path: str, part: str | None) -> str | None:
        """Why my person would need to see a change to someone else's file, or None."""
        if (owner, path) in self.copies:
            return "you have a copy"
        if (owner, path) in self.quotes:
            return "it was quoted to you earlier"
        if (owner, path) in self.requested:
            return "you asked for a change to it"
        for watch in self.person.get("watches", ()):
            if fnmatchcase(path, watch["glob"]):
                return watch["why"]
        claim = self.card.best_for([part]) if part else None
        if claim and claim.level == "touched":
            return "you changed this code recently"
        if claim and claim.level == "owner":
            return "you own this part"
        return None

    def _publish(self, path: str, old: str, new: str, message: str, requested_by=(), by_rule: bool = False,
                 undo_of: str | None = None) -> dict:
        added, removed = diffs.stats(old, new)
        part = part_for_path(path, self.parts)
        commit = {"owner": self.id, "path": path, "part": part, "message": message,
                  "requested_by": list(requested_by), "at": clock.fmt(self.net.t), "by_rule": by_rule,
                  "added": added, "removed": removed, "diff": diffs.unified(old, new, path)}
        if undo_of:
            commit["undo_of"] = undo_of
        if looks_secret(commit["diff"]):
            commit["diff"] = None
            commit["held_back"] = "The diff isn't included because it contains something that looks like a key."
        audience = [other for other in self.net.others(self.id)
                    if self.net.send(self.id, other, "watch_check", {"path": path, "part": part}).get("answer") == "yes"]
        commit["to"] = audience
        self.net.record("commit", card=commit, to=audience)
        for other in audience:
            self.net.send(self.id, other, "commit", {"commit": commit})
        return commit

    def _refresh(self, owner: str, path: str) -> None:
        r = self.net.send(self.id, owner, "share_request", {"path": path})
        for f in r.get("shared", []):
            self.copies[(owner, f["path"])] = f["text"]
            self.quotes.pop((owner, f["path"]), None)
            self.tell(f"I pulled the new version of {self.name(owner)}'s {path} for you.",
                      short=f"pulled the new version of {self.name(owner)}'s {path}")

    def _part_name(self, part_id: str) -> str:
        return next((p["name"] for p in self.parts if p["id"] == part_id), part_id)

    # ---------------------------------------------------------------- time

    def _review_time(self) -> None:
        asks = [a for a in self.time_asks if a["before"] > self.net.t]
        self.time_asks = []
        if not asks:
            return
        deadline = min(a["before"] for a in asks)
        length = min(30, max(a["minutes"] for a in asks) + 5 * (len(asks) - 1))
        start = max((deadline - 10 - length) // 5 * 5, -(-self.net.t // 5) * 5)
        names = [self.name(a["from"]) for a in asks]
        detail = ", ".join(f"{self.name(a['from'])} {a['minutes']} min ({a['about']})" for a in asks)
        if len(asks) == 1:
            prompt = (f"{names[0]} wants {asks[0]['minutes']} minutes before {clock.fmt(deadline)} "
                      f"({asks[0]['about']}). Meet at {clock.fmt(start)}?")
            options = [("yes", "Book it"), ("no", "No time today")]
        else:
            prompt = (f"{join_names(names)} each want time with you before {clock.fmt(deadline)}: {detail}. "
                      f"One shared slot from {clock.fmt(start)} to {clock.fmt(start + length)} "
                      f"instead of {len(asks)} interruptions?")
            options = [("yes", "Book one slot"), ("no", "No time today")]

        def answer(choice):
            for a in asks:
                if choice == "yes":
                    others = [n for n in names if n != self.name(a["from"])]
                    body = {"start": clock.fmt(start), "end": clock.fmt(start + length), "with": others}
                else:
                    body = {"declined": True}
                self.net.send(self.id, a["from"], "slot", body)

        self.ask(self._key("slot"), prompt, options, answer, order=7)

    # ------------------------------------------------------------- helpers

    def _file(self, path: str, to: str) -> dict:
        self.holders.setdefault(path, set()).add(to)
        return {"path": path, "text": self.ws.read(path)}
