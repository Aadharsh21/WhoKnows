"""The live demo, with no chat app attached.

Live runs the demo team as agents that real people can step into: take a seat
(say, Nina), and Nina's agent works for you. Seats nobody has taken are played
by simulated teammates who follow the same rules and answer with their default
choice. Live turns what people type into actions for their agents, puts
questions in front of real people instead of answering them, and collects
everything that should be shown somewhere as outgoing messages. The Discord bot
is a thin layer that delivers those messages.
"""

from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import clock, scenario
from .agent import join_names
from .cards import Claim
from .drafting import SmartDrafter
from .network import Network
from .story import build_network
from .understand import HELP, Understander


class LiveNetwork(Network):
    def __init__(self, team, choices=None, live=None):
        super().__init__(team, choices)
        self.live = live

    def record(self, step_type: str, **data) -> None:
        super().record(step_type, **data)
        if self.live:
            self.live.on_step(self.steps[-1])

    def ask_person(self, person: str, item) -> None:
        if self.live and self.live.is_real(person):
            self.live.ask_real(person, item)
        else:
            super().ask_person(person, item)


@dataclass
class Out:
    kind: str                  # "dm" or "channel"
    to: object                 # a user for DMs, a channel name otherwise
    text: str
    card: dict | None = None   # a commit card to show with the message
    question: str | None = None
    options: list = field(default_factory=list)
    diffs: dict | None = None


class Live:
    START = "01:07"
    QUIET = 20 * 60   # seconds of silence before the night starts over for whoever comes next
    BUSY = 10 * 60    # someone who wrote this recently is still playing

    def __init__(self, ai=None):
        self.ai = ai
        self.understand = Understander(ai)
        self.seats: dict[str, object] = {}
        self.last_seen: dict = {}  # user -> when they last wrote, so a shared night survives many visitors
        self.out: list[Out] = []
        self.reset()

    # ------------------------------------------------------------ setup

    def reset(self) -> None:
        root = scenario.build(Path(tempfile.mkdtemp(prefix="whoknows-")))
        self.out = []
        self.pending: dict[str, tuple] = {}
        self.questions: dict[str, str] = {}  # each seat's last question, for "pass it on"
        self._qid = 0
        self.net = build_network(root, network_cls=LiveNetwork, drafter=SmartDrafter(self.ai), live=self)
        self.start = clock.parse(self.START)
        self.net.start(self.start)

    def is_real(self, person: str) -> bool:
        return person in self.seats

    def seat_of(self, user) -> str | None:
        return next((p for p, u in self.seats.items() if u == user), None)

    def name(self, pid: str) -> str:
        return self.net.name(pid)

    def _who(self, pid: str) -> str:
        if pid == "board":
            return "Board"
        return f"{self.name(pid)}'s agent" if pid in self.net.agents else f"{pid} (not on the team)"

    # --------------------------------------------------- what gets shown

    def on_step(self, s: dict) -> None:
        kind = s["type"]
        if kind == "phone":
            if s.get("sender") == "person":
                return
            pid = s["person"]
            if self.is_real(pid):
                self.out.append(Out("dm", self.seats[pid], s["text"], card=s.get("card")))
            else:
                self.out.append(Out("channel", "teammates", f"**{self.name(pid)}'s phone**, {s['time']}: {s['text']}",
                                    card=s.get("card")))
        elif kind == "decision":
            pid = s["person"]
            if not self.is_real(pid):
                label = next(o["label"] for o in s["options"] if o["value"] == s["chosen"])
                self.out.append(Out("channel", "teammates",
                                    f"**{self.name(pid)}** was asked, {s['time']}: {s['prompt']}\n"
                                    f"Simulated {self.name(pid)} picked **{label}**."))
        elif kind == "msg":
            files = f" [{', '.join(s['files'])}]" if s.get("files") else ""
            self.out.append(Out("channel", "backchannel",
                                f"`{s['time']}` {self._who(s['sender'])} > {self._who(s['to'])}: {s['label']}{files}"))
        elif kind == "blocked":
            self.out.append(Out("channel", "backchannel",
                                f"`{s['time']}` BLOCKED {self._who(s['sender'])} > {self._who(s['to'])}: "
                                f"{s['label']} ({s['reason']})"))
        elif kind == "commit":
            c = s["card"]
            to = join_names(self.name(p) for p in s["to"]) or "nobody"
            self.out.append(Out("channel", "backchannel",
                                f"`{s['time']}` COMMIT {self.name(c['owner'])}'s {c['path']} "
                                f"+{c['added']} -{c['removed']}, sent only to {to}"))
        elif kind == "board":
            self.out.append(Out("channel", "team-board", self.board_text(s["parts"])))
        elif kind == "status":
            pid = s["person"]
            if s["t"] == self.start:
                return
            self.out.append(Out("channel", "backchannel", f"`{s['time']}` {self.name(pid)} is {s['state']}"))
            if self.is_real(pid):
                agent = self.net.agents[pid]
                if s["state"] == "asleep":
                    self.out.append(Out("dm", self.seats[pid],
                                        f"It's {s['time']} in the demo and {self.name(pid)} is asleep now. "
                                        f"Your agent won't wake you. It holds everything until {agent.wakes_at()}."))
                else:
                    self.out.append(Out("dm", self.seats[pid], f"Good morning. It's {s['time']} in the demo."))

    def board_text(self, parts) -> str:
        rows = []
        for p in parts:
            owners = join_names(self.name(o) for o in p["owners"]) or "NOBODY"
            note = f" ({p['note']})" if p["note"] else ""
            rows.append(f"- {p['name']}: {owners}{note}")
        return f"**Team board, {clock.fmt(self.net.t)}**\n" + "\n".join(rows)

    def status_text(self, user=None) -> str:
        awake = [self.name(a) for a in self.net.order if self.net.agents[a].awake()]
        asleep = [self.name(a) for a in self.net.order if not self.net.agents[a].awake()]
        mine = self.seat_of(user)
        taken = [f"{self.name(p)}{' (you)' if p == mine else ''}" for p in self.net.order if p in self.seats]
        free = [self.name(p) for p in self.net.order if p not in self.seats]
        return (f"It's {clock.fmt(self.net.t)} in the demo. Demo day starts at 9:00 AM.\n"
                f"Awake: {', '.join(awake) or 'nobody'}. Asleep: {', '.join(asleep) or 'nobody'}.\n"
                f"Taken by real people: {', '.join(taken) or 'none yet'}. Free seats: {', '.join(free) or 'none'}.")

    # ------------------------------------------------------- questions

    def ask_real(self, person: str, item) -> None:
        self._qid += 1
        qid = f"q{self._qid}"
        self.pending[qid] = (person, item)
        self.out.append(Out("dm", self.seats[person], item.prompt, question=qid, options=list(item.options),
                            diffs=item.extra.get("diffs")))

    def answer(self, user, qid: str, value: str, now: float | None = None) -> str:
        self.last_seen[user] = time.time() if now is None else now
        person, item = self.pending.get(qid, (None, None))
        if item is None:
            return "That question has expired."
        if self.seats.get(person) != user:
            return "That question is for someone else."
        del self.pending[qid]
        self.net.choices[item.key] = value
        choice = self.net.decide(person, item.key, item.prompt, item.options, **item.extra)
        item.on_answer(choice)
        return next(label for v, label in item.options if v == choice)

    # ----------------------------------------------------- what people type

    def take_seat(self, user, person: str) -> str:
        holder = self.seats.get(person)
        if holder is not None and holder != user:
            free = ", ".join(self.name(p) for p in self.net.order if p not in self.seats)
            return f"Someone already has {self.name(person)}. Free seats: {free}."
        old = self.seat_of(user)
        if old:
            del self.seats[old]
        self.seats[person] = user
        agent = self.net.agents[person]
        state = "awake" if agent.awake() else f"asleep until {agent.wakes_at()}"
        return (f"You're {agent.person['name']} ({agent.person['role']}). It's {clock.fmt(self.net.t)} in the demo "
                f"and you're {state}. Your agent works for you from now on. Say help to see what you can ask it.")

    def move_clock(self, hhmm: str) -> str:
        t = clock.parse(hhmm)
        if t <= self.net.t:
            return f"Demo time only moves forward. It's {clock.fmt(self.net.t)}. Say reset to start the night over."
        self.net.advance_to(t)
        return f"It's now {clock.fmt(t)} in the demo."

    def _wake_early(self, person: str) -> None:
        agent = self.net.agents[person]
        agent.person["sleep"] = []
        self.net.record("status", person=person, state="awake")
        agent.wake()

    def handle(self, user, text: str, now: float | None = None) -> str | None:
        """What someone typed in a DM. Returns the bot's direct reply, if any; everything else goes to out."""
        now = time.time() if now is None else now
        note = self._start_over_if_quiet(now)
        others = [u for u, t in self.last_seen.items() if u != user and now - t < self.BUSY]
        self.last_seen[user] = now
        reply = self._handle(user, text, others_playing=bool(others))
        if note:
            return note + ("\n\n" + reply if reply else "")
        return reply

    def _start_over_if_quiet(self, now: float) -> str | None:
        """A public server gets visitors hours apart. Give each new one a fresh night instead of the last one's."""
        if not self.last_seen or now - max(self.last_seen.values()) < self.QUIET:
            return None
        self.seats.clear()
        self.last_seen.clear()
        self.reset()
        return "It had been quiet for a while, so the night started over at 1:07 AM and every seat is free again."

    def _handle(self, user, text: str, others_playing: bool = False) -> str | None:
        me = self.seat_of(user)
        a = self.understand.parse(text, me, self.net.team)
        act = a["action"]
        if act == "help_text":
            return HELP
        if act == "seat":
            return self.take_seat(user, a["person"])
        if act == "status":
            return self.status_text(user)
        if act == "board":
            return self.board_text(self.net.board_snapshot())
        if act == "reset":
            if others_playing:
                return ("Someone else is playing right now, so I won't restart the night under them. "
                        "It starts over on its own after 20 quiet minutes.")
            self.reset()
            return "Started the night over at 1:07 AM. Everyone kept their seat."
        if act == "clock":
            return self.move_clock(a["before"])
        if act == "check":
            self.net.team_check()
            return "Ran the team board check. The results are in #team-board."
        if not me:
            free = ", ".join(f"{self.name(p)} ({self.net.agents[p].person['role']})"
                             for p in self.net.order if p not in self.seats)
            return f"Take a seat first, like: seat nina. Free seats: {free}."
        agent = self.net.agents[me]
        if not agent.awake():
            self._wake_early(me)
        self.net.typed(me, text)
        if act == "who_knows":
            agent.find_who_knows(a.get("question") or text)
        elif act == "question":
            self.questions[me] = a.get("question") or text
            agent.ask_question(self.questions[me])
        elif act == "pass_on":
            question = self.questions.get(me)
            if not question:
                return "Ask your question first, then say pass it on."
            if not agent.last_hits:
                agent.find_who_knows(question)
            if not agent.last_hits:
                return "Nobody's agent knows of anyone on that, so there's no one to pass it to yet."
            agent.pass_on(question)
        elif act == "fetch":
            agent.fetch_from(a["person"], a.get("part"), look_for=("must", "idempotency"))
        elif act == "file":
            agent.request_file(a["person"], a["path"])
        elif act == "help":
            agent.ask_for_help(a["person"], a.get("minutes") or 15, a.get("about") or text, part=a.get("part"))
        elif act == "change":
            agent.request_change(a["person"], a["path"], a.get("recipe") or "", a.get("intent") or text)
        elif act == "time":
            agent.request_time(a["person"], a.get("minutes") or 10, a.get("before") or "09:00", a.get("about") or text)
        elif act == "claim":
            part = next(p for p in self.net.parts if p["id"] == a["part"])
            agent.card.claims.append(Claim(part["id"], "claims", f"said they're doing {a.get('detail', part['name'])}"))
            return f"Got it. Your agent will put you down for the {part['name']} at the next board check."
        else:
            return "I didn't catch that. Here's what I understand:\n" + HELP
        return None
