"""The network the agents talk over.

Every message goes through the sender's gate on the way out and the replier's
gate on the way back. Everything that happens is written to a trace: messages
that crossed, messages the gates blocked, what each person saw on their phone,
and every decision a person made. The site and the video replay that trace.
"""

from __future__ import annotations

from fnmatch import fnmatchcase

from . import clock
from .agent import join_names


def _label(kind: str, body: dict) -> str:
    body = body or {}
    if kind == "who_knows":
        return "who knows this?"
    if kind == "fetch":
        return f"anything on {body.get('part')}?"
    if kind == "share_request":
        return f"can I have {body.get('path')}?"
    if kind == "help":
        return f"{body.get('minutes')} min of help now?"
    if kind == "help_answer":
        return "yes, free now" if body.get("answer") == "yes" else "not now"
    if kind == "change":
        return f"change request: {body.get('path')}"
    if kind == "change_status":
        return f"{body.get('status')}: {body.get('path')}"
    if kind == "time":
        return f"{body.get('minutes')} min before {clock.fmt(clock.parse(body.get('before', '23:59')))}?"
    if kind == "slot":
        return "no time today" if body.get("declined") else f"booked {body.get('start')}"
    if kind == "watch_check":
        return f"who needs {body.get('path')}?"
    if kind == "commit":
        c = body.get("commit", {})
        return f"commit: {c.get('path')} +{c.get('added')} -{c.get('removed')}"
    if kind == "delivery":
        if body.get("shared"):
            return "sent " + ", ".join(f["path"] for f in body["shared"])
        return f"kept {body.get('kept')} private"
    return kind


def _reply_label(kind: str, reply: dict) -> str:
    reply = reply or {}
    if kind == "who_knows":
        word = {"no": "no", "owner": "owns it", "touched": "changed it recently",
                "claims": "says it's theirs"}.get(reply.get("answer"), "no")
        return word + (" (asleep)" if reply.get("status") else "")
    if kind in ("fetch", "share_request") and (reply.get("shared") or reply.get("mentions")):
        n, m = len(reply.get("shared", [])), len(reply.get("mentions", []))
        bits = [f"sent {', '.join(f['path'] for f in reply.get('shared', []))}"] if n else []
        if m:
            bits.append(f"{m} more need an OK")
        return "; ".join(bits)
    if kind == "change" and reply.get("status") == "queued":
        clash = " (collides)" if reply.get("collides_with") else ""
        return f"queued for the owner{clash}"
    if kind == "watch_check":
        return reply.get("answer", "no")
    status = reply.get("status", "ok")
    return {"queued": "queued for the owner", "unavailable": "not available", "not_mine": "not mine to share",
            "asking": "asking them", "asleep": "asleep", "seen": "seen"}.get(status, status)


class Network:
    def __init__(self, team: dict, choices: dict | None = None):
        self.team = team
        self.parts = team["parts"]
        self.choices = dict(choices or {})
        self.used: dict[str, str] = {}
        self.agents: dict = {}
        self.order: list[str] = []
        self.steps: list[dict] = []
        self.t = 0
        self._after: list = []
        self._depth = 0
        self.board = {p["id"]: {"owners": [], "note": ""} for p in self.parts}

    # ------------------------------------------------------------- setup

    def add(self, agent) -> None:
        self.agents[agent.id] = agent
        self.order.append(agent.id)
        agent.net = self

    def others(self, pid: str) -> list[str]:
        return [a for a in self.order if a != pid]

    def name(self, pid: str) -> str:
        agent = self.agents.get(pid)
        return agent.first if agent else pid

    # -------------------------------------------------------------- time

    def start(self, t: int) -> None:
        self.t = t
        for aid in self.order:
            self.record("status", person=aid, state="awake" if self.agents[aid].awake() else "asleep")

    def advance_to(self, t: int) -> None:
        """Move the clock forward, putting people to sleep and waking them up in order."""
        events = []
        for index, aid in enumerate(self.order):
            for s, e in self.agents[aid].person.get("sleep", ()):
                for minute, state in ((clock.parse(s), "asleep"), (clock.parse(e), "awake")):
                    if self.t < minute <= t:
                        events.append((minute, index, aid, state))
        for minute, _, aid, state in sorted(events):
            self.t = minute
            self.record("status", person=aid, state=state)
            if state == "awake":
                self.agents[aid].wake()
        self.t = t

    # ------------------------------------------------------------- trace

    def record(self, step_type: str, **data) -> None:
        self.steps.append({"t": self.t, "time": clock.fmt(self.t), "type": step_type, **data})

    def caption(self, text: str) -> None:
        self.record("caption", text=text)

    def typed(self, person: str, text: str) -> None:
        """A person writes to their own agent."""
        self.record("phone", person=person, sender="person", text=text)

    def phone(self, person: str, text: str, **extra) -> None:
        """An agent writes to its person."""
        self.record("phone", person=person, sender="agent", text=text, **extra)

    def ask_person(self, person: str, item) -> None:
        """Put a question in front of a person. Here, the scripted choice answers it right away."""
        item.on_answer(self.decide(person, item.key, item.prompt, item.options, **item.extra))

    def decide(self, person: str, key: str, prompt: str, options: list, **extra) -> str:
        values = [value for value, _ in options]
        choice = self.choices.get(key, values[0])
        if choice not in values:
            raise ValueError(f"{key}: {choice!r} is not one of {values}")
        self.used[key] = choice
        self.record("decision", person=person, key=key, prompt=prompt,
                    options=[{"value": v, "label": label} for v, label in options], chosen=choice, **extra)
        return choice

    # ---------------------------------------------------------- messages

    def after(self, fn) -> None:
        """Run fn once the current exchange is finished, so replies land before follow-ups."""
        self._after.append(fn)
        if self._depth == 0:
            self._flush()

    def _flush(self) -> None:
        while self._after:
            self._after.pop(0)()

    def send(self, frm: str, to: str, kind: str, body: dict | None = None) -> dict:
        body = body or {}
        self._depth += 1
        try:
            if frm not in self.agents or to not in self.agents:
                self.record("blocked", sender=frm, to=to, kind=kind, label=_label(kind, body),
                            reason="not on this team")
                return {"status": "refused"}
            ok, why = self.agents[frm].gate.check(kind, body, to)
            if not ok:
                self.record("blocked", sender=frm, to=to, kind=kind, label=_label(kind, body), reason=why)
                return {"status": "blocked", "reason": why}
            self.record("msg", sender=frm, to=to, kind=kind, label=_label(kind, body),
                        files=[f["path"] for f in body.get("shared", [])])
            reply = self.agents[to].handle(kind, body, frm)
            ok, why = self.agents[to].gate.check("reply", reply, frm)
            if not ok:
                self.record("blocked", sender=to, to=frm, kind="reply", label=f"reply to {kind}", reason=why)
                return {"status": "blocked", "reason": why}
            self.record("msg", sender=to, to=frm, kind=f"reply:{kind}", label=_reply_label(kind, reply),
                        files=[f["path"] for f in reply.get("shared", [])])
            return reply
        finally:
            self._depth -= 1
            if self._depth == 0:
                self._flush()

    # ------------------------------------------------------------- board

    def board_snapshot(self) -> list[dict]:
        needs = set(self.team.get("project", {}).get("needs", ()))
        return [{"id": p["id"], "name": p["name"], "owners": list(self.board[p["id"]]["owners"]),
                 "note": self.board[p["id"]]["note"], "due": p.get("due"), "critical": p["id"] in needs,
                 "knowers": list(self.board[p["id"]].get("knowers", [])),
                 "backup": list(self.board[p["id"]].get("backup", []))} for p in self.parts]

    def team_check(self) -> None:
        """Every agent posts which parts its person owns, has claimed, or knows. Then the agents sort out
        duplicates, parts nobody owns, and parts the deadline depends on that only one person knows."""
        claims: dict[str, list[str]] = {}
        knows: dict[str, list[str]] = {}
        for aid in self.order:
            card = self.agents[aid].card
            mine = card.public_claims()
            known = card.known_parts()
            body = {"claims": [{"part": p, "level": level} for p, level in mine], "knows": known}
            ok, why = self.agents[aid].gate.check("claims", body, "board")
            if not ok:
                self.record("blocked", sender=aid, to="board", kind="claims", label="claims", reason=why)
                continue
            self.record("msg", sender=aid, to="board", kind="claims",
                        label=", ".join(p for p, _ in mine) or "nothing", files=[])
            for p, _ in mine:
                claims.setdefault(p, []).append(aid)
            for p in known:
                knows.setdefault(p, []).append(aid)
        for p in self.parts:
            self.board[p["id"]]["owners"] = list(claims.get(p["id"], []))
            self.board[p["id"]]["knowers"] = list(knows.get(p["id"], []))
        dups = [p for p in self.parts if len(claims.get(p["id"], [])) > 1]
        gaps = [p for p in self.parts if not claims.get(p["id"])]
        self.record("board", parts=self.board_snapshot(), duplicates=[p["id"] for p in dups],
                    orphans=[p["id"] for p in gaps])
        for p in dups:
            self._split(p, claims[p["id"]])
        for p in gaps:
            self._find_owner(p, self._candidates(p))
        self._radar(knows)

    # --------------------------------------------------------- bus factor

    def _radar(self, knows: dict) -> None:
        """For each part the deadline depends on, count who knows it. One person is a single point of
        failure: line up a backup who's awake, or flag it for that person's morning."""
        needs = self.team.get("project", {}).get("needs", ())
        risky = []
        for pid in needs:
            people = knows.get(pid, [])
            if len(people) == 1:
                risky.append((next(p for p in self.parts if p["id"] == pid), people[0]))
        if not risky:
            return
        self.record("board", parts=self.board_snapshot(),
                    single=[{"part": part["id"], "knower": knower} for part, knower in risky])
        for part, knower in risky:
            backup = self._backup_for(part, knower)
            if backup:
                self._ask_backup(part, knower, backup)
            else:
                self._only_one(part, knower)

    def _only_one(self, part: dict, knower: str) -> None:
        """No backup tonight: put it on the board and let the one person who knows the part hear about it."""
        self.board[part["id"]]["note"] = f"only {self.name(knower)} knows it"
        self.agents[knower].tell(
            f"The demo depends on the {part['name']} and you're the only one who knows it. Your shareable "
            f"notes on it are there if anyone needs them, but think about briefing someone before 9.",
            short=f"you're the only one who knows the {part['name']}, and the demo depends on it")
        self.record("board", parts=self.board_snapshot())

    def _backup_for(self, part: dict, knower: str):
        def relevance(aid):
            person = self.agents[aid].person
            return sum(2 for w in person.get("watches", ()) for path in part.get("paths", ())
                       if fnmatchcase(path, w["glob"]) or fnmatchcase(w["glob"].rstrip("*"), path + "*"))

        def load(aid):
            return sum(1 for b in self.board.values() if aid in b["owners"] or aid in b.get("backup", []))

        pool = [a for a in self.order if a != knower and self.agents[a].awake() and not self.agents[a].person.get("busy")]
        if not pool:
            return None
        return sorted(pool, key=lambda a: (-relevance(a), load(a), self.order.index(a)))[0]

    def _ask_backup(self, part: dict, knower: str, backup: str) -> None:
        agent = self.agents[backup]
        self.record("msg", sender="board", to=backup, kind="backup", label=f"backup for {part['name']}?", files=[])

        def answer(choice):
            if choice != "yes":
                self._only_one(part, knower)
                return
            self.board[part["id"]].setdefault("backup", []).append(backup)
            self.board[part["id"]]["note"] = f"{agent.first} is backup"
            agent.fetch_from(knower, part["id"])
            self.record("board", parts=self.board_snapshot())

        agent.ask(f"{backup}_backup_{part['id']}",
                  f"Only {self.name(knower)} knows the {part['name']}, and the demo depends on it. Be the backup? "
                  f"Your agent will pull {self.name(knower)}'s shareable notes on it now.",
                  [("yes", "I'll be backup"), ("no", "Not tonight")], answer)

    def board_update(self, by: str, part_id: str, status: str, detail: str = "") -> None:
        part = next(p for p in self.parts if p["id"] == part_id)
        self.record("msg", sender=by, to="board", kind="report", label=f"{part['name']}: {status}", files=[])
        self.board[part_id]["note"] = status
        self.record("board", parts=self.board_snapshot())
        for owner in self.board[part_id]["owners"]:
            if owner != by and owner in self.agents:
                self.record("msg", sender="board", to=owner, kind="board_news", label=f"{part['name']}: {status}",
                            files=[])
                more = f" {detail}" if detail else ""
                self.agents[owner].tell(f"Board update from {self.name(by)}: the {part['name']} is {status}.{more}",
                                        short=f"{self.name(by)} marked the {part['name']} {status}.{more}")

    def _split(self, part: dict, people: list[str]) -> None:
        details = {}
        for aid in people:
            said = next((s["detail"] for s in self.agents[aid].person.get("says", ()) if s["part"] == part["id"]), None)
            details[aid] = said
        if not all(details.values()):
            self.board[part["id"]]["note"] = "two people on it"
            for aid in people:
                others = join_names(self.name(o) for o in people if o != aid)
                self.agents[aid].tell(f"Heads up: {others} is also on the {part['name']}. Worth a quick chat.")
            self.record("board", parts=self.board_snapshot())
            return
        answers: dict[str, str] = {}

        def finish():
            if all(v == "yes" for v in answers.values()):
                note = "split: " + ", ".join(f"{self.name(a)} has {details[a]}" for a in people)
            else:
                note = "two people on it, sorting it out"
            self.board[part["id"]]["note"] = note
            self.record("board", parts=self.board_snapshot())

        for aid in people:
            others = [o for o in people if o != aid]
            theirs = join_names(f"{self.name(o)} takes {details[o]}" for o in others)
            prompt = (f"{join_names(self.name(o) for o in others)} is also writing the {part['name']}. "
                      f"Split it so you take {details[aid]} and {theirs}?")
            self.record("msg", sender="board", to=aid, kind="duplicate", label=f"two people on {part['name']}",
                        files=[])

            def answer(choice, aid=aid):
                answers[aid] = choice
                if len(answers) == len(people):
                    finish()

            self.agents[aid].ask(f"{aid}_split_{part['id']}", prompt, [("yes", "Split it"), ("no", "Talk first")],
                                 answer)

    def _candidates(self, part: dict) -> list[str]:
        needs = set(part.get("needs", ()))

        def load(aid):
            return sum(1 for b in self.board.values() if aid in b["owners"])

        pool = [a for a in self.order if self.agents[a].awake() and not self.agents[a].person.get("busy")]
        return sorted(pool, key=lambda a: (-len(needs & set(self.agents[a].person.get("good_at", ()))),
                                           load(a), self.order.index(a)))

    def _find_owner(self, part: dict, candidates: list[str]) -> None:
        if not candidates:
            self.board[part["id"]]["note"] = "nobody yet"
            self.record("board", parts=self.board_snapshot())
            return
        aid, rest = candidates[0], candidates[1:]
        agent = self.agents[aid]
        skill = sorted(set(part.get("needs", ())) & set(agent.person.get("good_at", ())))
        due = f" and it's due at {clock.fmt(clock.parse(part['due']))}" if part.get("due") else ""
        why = f" You're good at {join_names(skill)}." if skill else ""
        self.record("msg", sender="board", to=aid, kind="orphan", label=f"can {agent.first} take the {part['name']}?",
                    files=[])

        def answer(choice):
            if choice == "yes":
                self.board[part["id"]]["owners"] = [aid]
                self.board[part["id"]]["note"] = f"{agent.first} took it at {clock.fmt(self.t)}"
                self.record("board", parts=self.board_snapshot())
            else:
                self._find_owner(part, rest)

        agent.ask(f"{aid}_take_{part['id']}", f"Nobody has the {part['name']}{due}.{why} Can you take it?",
                  [("yes", "I'll take it"), ("no", "Can't")], answer)
