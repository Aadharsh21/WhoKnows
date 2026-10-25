"""How WhoKnows compares with a team group chat and with messaging your best guess.

A seeded generator builds a team: a plan, a CODEOWNERS file, a git repo with a
few days of commits, and a folder for each person with notes they share,
drafts they don't, and private files. Then it writes a week of questions, about
one per person per day, asked at times the asker is awake. Each answer is held
by exactly one person: the part's owner, or whoever changed that part most
recently.

The WhoKnows numbers come from running the real agents on every question. The
two baselines follow the same simple rules for people, listed in ASSUMPTIONS.
When a rule had to be guessed, it was guessed in the baselines' favor.

    python3 -m whoknows.bench                  # print the tables
    python3 -m whoknows.bench --out site/bench.json
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import clock
from .agent import PersonalAgent
from .cards import build_cards, parts_in
from .network import Network
from .policy import NEVER, Policy
from .workspace import Workspace

REPLY = 15                 # minutes an awake person takes to see a message and answer it
DRAFTS = 0.15              # share of answers sitting in drafts, which need the owner's OK
HIDDEN = 0.3               # chance a part has one answer held by someone who left no trace of it
HOPS = 2                   # people the agent tries in turn before the asker falls back to the group chat
TZ = timezone(timedelta(hours=-7))
START = datetime(2026, 11, 2, tzinfo=TZ)  # a Monday at midnight; the week runs from here
WEEK_DAYS = 7

ASSUMPTIONS = [
    "Each team gets one question per person per day, asked at a random minute while the asker is awake.",
    "An awake person sees a message and answers within 15 minutes. A sleeping person answers 15 minutes "
    "after waking. Nobody is counted as woken up early, so a night ping never speeds up an answer.",
    "Group chat: every member gets a notification, and the person who knows always sees the question and "
    "answers. Both are generous to the group chat.",
    "Best guess: the asker messages the part's owner from the team plan. If someone else changed it "
    "recently, the owner always knows who and says so, and the asker passes the question on at their next "
    "waking minute. Owners asking about their own part check git and message whoever changed it. For parts "
    "with no owner in the plan, or answers nobody can point to, the asker falls back to the group chat.",
    "WhoKnows: the real agents run on every question. They ask who knows, then search the shareable notes of "
    "those people, then everyone's. If no quote contains the answer, the agent hands the question to the best "
    "match, then the next one if the first says not me, with the same 15 minute rule. After two misses the "
    "asker falls back to the group chat and pays its full cost, night pings included.",
    "About a quarter of answers belong to someone who changed a part recently rather than its owner, and a "
    "few belong to someone who left no trace in the plan, CODEOWNERS, git, or their agent. Half of all "
    "answers are written in notes their holder shares, 15% sit in drafts that need an OK, and the rest are "
    "only in someone's head. The second table varies the written share.",
]

# Parts of a made-up product: id, name, the phrase questions use, and the keywords that identify it.
COMPONENTS = [
    ("search", "Search indexer", "search indexer", ["search indexer", "search"]),
    ("billing", "Billing", "billing service", ["billing"]),
    ("notify", "Notifications", "notification service", ["notification", "notifications"]),
    ("uploads", "File uploads", "upload service", ["upload service", "uploads"]),
    ("login", "Login", "login flow", ["login"]),
    ("feed", "Activity feed", "activity feed", ["activity feed", "feed"]),
    ("chat", "Chat", "chat backend", ["chat"]),
    ("maps", "Maps", "map tiles", ["map tiles", "maps"]),
    ("export", "CSV export", "CSV export", ["csv export"]),
    ("onboarding", "Onboarding", "onboarding flow", ["onboarding"]),
    ("analytics", "Analytics", "analytics pipeline", ["analytics"]),
    ("admin", "Admin panel", "admin panel", ["admin panel", "admin"]),
    ("email", "Email", "email sender", ["email sender", "email"]),
    ("cache", "Cache", "cache layer", ["cache layer", "cache"]),
    ("jobs", "Job queue", "job queue", ["job queue"]),
    ("pricing", "Pricing page", "pricing page", ["pricing"]),
    ("profiles", "Profiles", "profile service", ["profile service", "profiles"]),
    ("settings", "Settings", "settings page", ["settings page", "settings"]),
    ("i18n", "Translations", "translation loader", ["translation loader", "translations"]),
    ("webhooks", "Webhooks", "webhook relay", ["webhook relay", "webhooks"]),
    ("ios", "iOS app", "iOS app", ["ios app", "ios"]),
    ("android", "Android app", "Android app", ["android app", "android"]),
    ("ci", "CI pipeline", "CI pipeline", ["ci pipeline"]),
    ("deploy", "Deploys", "deploy script", ["deploy script", "deploys"]),
    ("docs", "Docs site", "docs site", ["docs site"]),
    ("reports", "Reports", "report builder", ["report builder", "reports"]),
    ("calendar", "Calendar sync", "calendar sync", ["calendar sync", "calendar"]),
    ("images", "Image resizer", "image resizer", ["image resizer"]),
    ("audit", "Audit log", "audit log", ["audit log"]),
    ("gateway", "API gateway", "API gateway", ["api gateway"]),
]

THINGS = [
    ("timeout", lambda r: f"{r.choice([5, 10, 15, 30, 45, 60])} seconds"),
    ("retry limit", lambda r: f"{r.randint(2, 6)} tries"),
    ("batch size", lambda r: f"{r.choice([50, 100, 200, 500])} items"),
    ("rate limit", lambda r: f"{r.choice([30, 60, 120, 600])} requests a minute"),
    ("page size", lambda r: f"{r.choice([20, 25, 50, 100])} rows"),
    ("size cap", lambda r: f"{r.choice([5, 10, 25, 50])} MB"),
    ("retention period", lambda r: f"{r.choice([7, 14, 30, 90])} days"),
    ("thread count", lambda r: f"{r.choice([2, 4, 8, 16])} threads"),
    ("polling interval", lambda r: f"{r.choice([5, 15, 30, 60])} seconds"),
    ("expiry window", lambda r: f"{r.choice([15, 30, 60, 120])} minutes"),
    ("connection cap", lambda r: f"{r.choice([10, 20, 50, 100])} connections"),
    ("alert threshold", lambda r: f"{r.choice([1, 2, 5, 10])} percent errors"),
]

REASONS = ["imports kept timing out", "the free tier ran out of quota", "people saw duplicates",
           "the staging demo stalled", "support asked for it", "costs doubled last month"]
CHANGE_DAYS = [("Friday", 4), ("Saturday", 5), ("Saturday", 22), ("Sunday", 15)]  # (weekday, hour)

FIRST = ["Ava", "Ben", "Cleo", "Dev", "Eli", "Fay", "Gus", "Hao", "Ines", "Jai", "Kofi", "Lena", "Milo",
         "Noor", "Oki", "Pia", "Quinn", "Ravi", "Sana", "Tom", "Uma", "Vik", "Wen", "Xia", "Yara", "Zed",
         "Aiko", "Bram", "Chen", "Dina", "Emre", "Gita", "Hugo", "Ivy", "Jon", "Kai", "Lior", "Maya",
         "Nils", "Odin", "Paz", "Rhea", "Sol", "Tara", "Ugo", "Vera", "Wes", "Yuki", "Zoe", "Arlo"]
SLEEP_STARTS = ["22:00", "22:30", "23:00", "23:30", "00:00", "00:30", "01:00", "01:30", "02:00", "03:00"]
SLEEP_HOURS = [6.0, 6.5, 7.0, 7.5, 8.0, 8.5]


@dataclass
class Fact:
    part: str
    holder: str
    text: str
    question: str
    kind: str      # config (the owner's), change (a recent change by someone else), or hidden (no trace)
    where: str     # notes, drafts, or head


@dataclass
class Question:
    asker: str
    t: int         # minutes since the start of the week
    fact: Fact


@dataclass
class Outcome:
    notified: int          # people other than the asker whose phone showed something
    night: int             # of those, notifications that reached someone asleep
    minutes: int           # until the asker has the answer
    first_try: bool        # the first person contacted held the answer
    found: bool = True     # the person who knows was reached at all
    messages: int = 0      # agent to agent requests (WhoKnows only)
    summary_lines: int = 0  # lines added to sleeping teammates' morning summaries (WhoKnows only)
    blocked: int = 0
    private_sent: int = 0
    fallback: bool = False  # the asker had to use the group chat after all
    agent_night: int = 0    # night notifications caused by agents themselves (should always be 0)


# ------------------------------------------------------------------ the team

@dataclass
class Team:
    root: Path
    data: dict
    facts: list = field(default_factory=list)

    @property
    def people(self):
        return self.data["people"]

    def person(self, pid):
        return next(p for p in self.people if p["id"] == pid)

    def part(self, part_id):
        return next(p for p in self.data["parts"] if p["id"] == part_id)


def _sleep(rng):
    start = rng.choice(SLEEP_STARTS)
    end = (clock.parse(start) + int(rng.choice(SLEEP_HOURS) * 60)) % clock.DAY
    return [[start, f"{end // 60:02d}:{end % 60:02d}"]]


def make_team(root: Path, size: int, seed: int, written: float = 0.5) -> Team:
    rng = random.Random(seed)
    root = Path(root)
    people = [{"id": f"p{i:02d}", "name": f"{FIRST[i]} {chr(65 + i % 26)}.", "role": "Engineer",
               "sleep": _sleep(rng), "policy": {"auto": ["notes/*"]}} for i in range(size)]
    n_parts = max(4, min(len(COMPONENTS), round(size * 0.7)))
    comps = COMPONENTS[:n_parts]
    n_unowned = max(1, n_parts // 8)
    order = [p["id"] for p in people]
    rng.shuffle(order)
    parts, holders = [], {}
    for i, (pid, name, phrase, keywords) in enumerate(comps):
        owner = order[i % size]
        unowned = i >= n_parts - n_unowned
        parts.append({"id": pid, "name": name, "owner": None if unowned else owner,
                      "paths": [f"{pid}/"], "keywords": keywords, "phrase": phrase})
        holders[pid] = owner
        if unowned:  # nobody in the plan, but someone told their agent they're on it
            next(p for p in people if p["id"] == owner).setdefault("says", []).append(
                {"part": pid, "detail": f"the {phrase}"})

    facts, commits = [], []
    for part in parts:
        things = rng.sample(THINGS, len(THINGS))
        for thing, value in things[:3]:
            val = value(rng)
            facts.append(Fact(part["id"], holders[part["id"]], f"The {part['phrase']} {thing} is {val}.",
                              f"what's the {thing} for the {part['phrase']}?", "config", ""))
        touchers = rng.sample([p["id"] for p in people if p["id"] != holders[part["id"]]],
                              k=min(size - 1, rng.choice([0, 1, 1, 2])))
        if rng.random() < HIDDEN:  # someone knows this without leaving a trace anywhere
            thing, value = things[5]
            who = rng.choice([p["id"] for p in people if p["id"] != holders[part["id"]] and p["id"] not in touchers])
            facts.append(Fact(part["id"], who, f"The {part['phrase']} {thing} is {value(rng)}.",
                              f"what's the {thing} for the {part['phrase']}?", "hidden", ""))
        for k, who in enumerate(touchers):
            thing, value = things[3 + k]
            day, hour = rng.choice(CHANGE_DAYS)
            facts.append(Fact(part["id"], who,
                              f"Changed the {part['phrase']} {thing} to {value(rng)} on {day} because "
                              f"{rng.choice(REASONS)}.",
                              f"why did the {part['phrase']} {thing} change?", "change", ""))
            when = START - timedelta(days=7 - ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                                               "Saturday", "Sunday"].index(day)) + timedelta(hours=hour)
            commits.append((who, when, f"{part['id']}: {thing}", f"{part['id']}/main.py"))
    for fact in facts:
        roll = rng.random()
        fact.where = "notes" if roll < written else "drafts" if roll < written + DRAFTS else "head"

    data = {"project": {"name": "Benchmark team"}, "people": people, "parts": parts}
    for fact in facts:  # every question has to point at exactly one part
        assert parts_in(fact.question, parts) == [fact.part], fact.question
    _write(root, data, facts, commits, rng)
    return Team(root, data, facts)


def _write(root: Path, data: dict, facts: list, commits: list, rng) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "team.json").write_text(json.dumps(data, indent=1))
    for person in data["people"]:
        ws = root / "workspaces" / person["id"]
        (ws / "personal").mkdir(parents=True, exist_ok=True)
        key = "".join(rng.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(24))
        (ws / ".env").write_text(f"PAYMENTS_SECRET_KEY=sk_test_{key}\n")
        (ws / "personal" / "journal.md").write_text(f"Private notes for {person['name']}.\n")
        for where in ("notes", "drafts"):
            mine = [f for f in facts if f.holder == person["id"] and f.where == where]
            for part_id in sorted({f.part for f in mine}):
                name = next(p["name"] for p in data["parts"] if p["id"] == part_id)
                body = "\n\n".join(f.text for f in mine if f.part == part_id)
                (ws / where).mkdir(exist_ok=True)
                (ws / where / f"{part_id}.md").write_text(f"# {name}\n\n{body}\n")

    repo = root / "repo"
    repo.mkdir(exist_ok=True)
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}

    def git(*args, who=None, when=None):
        extra = {}
        if who:
            stamp = when.isoformat()
            extra = {"GIT_AUTHOR_NAME": who, "GIT_AUTHOR_EMAIL": f"{who}@team.example", "GIT_AUTHOR_DATE": stamp,
                     "GIT_COMMITTER_NAME": who, "GIT_COMMITTER_EMAIL": f"{who}@team.example",
                     "GIT_COMMITTER_DATE": stamp}
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env={**env, **extra})

    git("init", "-q")
    owned = [p for p in data["parts"] if p["owner"]]
    (repo / "CODEOWNERS").write_text("".join(f"/{p['id']}/ @{p['owner']}\n" for p in owned))
    for p in data["parts"]:
        (repo / p["id"]).mkdir(exist_ok=True)
        (repo / p["id"] / "main.py").write_text(f"# {p['name']}\n")
    git("add", "-A")
    git("commit", "-q", "-m", "Start the project", who="p00", when=START - timedelta(days=30))
    for n, (who, when, subject, path) in enumerate(sorted(commits, key=lambda c: c[1])):
        with open(repo / path, "a") as f:
            f.write(f"# change {n}\n")
        git("add", "-A")
        git("commit", "-q", "-m", subject, who=who, when=when)


def make_questions(team: Team, seed: int) -> list:
    rng = random.Random(seed + 1)
    people = [p["id"] for p in team.people]
    out = []
    for _ in range(len(people) * WEEK_DAYS):
        fact = rng.choice(team.facts)
        asker = rng.choice([p for p in people if p != fact.holder])
        while True:
            t = rng.randrange(WEEK_DAYS * clock.DAY)
            if awake(team.person(asker), t):
                break
        out.append(Question(asker, t, fact))
    return sorted(out, key=lambda q: q.t)


# --------------------------------------------------------------- people time

def awake(person: dict, t: int) -> bool:
    return not any(clock.in_window(t, s, e) for s, e in person.get("sleep", ()))


def next_awake(person: dict, t: int) -> int:
    """The first minute at or after t when this person is awake."""
    for s, e in person.get("sleep", ()):
        if clock.in_window(t, s, e):
            end = (t // clock.DAY) * clock.DAY + clock.parse(e)
            return end if end > t else end + clock.DAY
    return t


# ------------------------------------------------------------- the three ways

def group_chat(team: Team, q: Question) -> Outcome:
    others = [p for p in team.people if p["id"] != q.asker]
    night = sum(1 for p in others if not awake(p, q.t))
    holder = team.person(q.fact.holder)
    return Outcome(len(others), night, next_awake(holder, q.t) + REPLY - q.t, first_try=True)


def best_guess(team: Team, q: Question) -> Outcome:
    owner = team.part(q.fact.part)["owner"]
    holder, asker = team.person(q.fact.holder), team.person(q.asker)
    if owner == q.asker and q.fact.kind == "change":  # an owner can see who changed their own code
        return Outcome(1, int(not awake(holder, q.t)), next_awake(holder, q.t) + REPLY - q.t, first_try=True)
    if not owner or owner == q.asker:
        out = group_chat(team, q)
        out.first_try = False
        return out
    guess = team.person(owner)
    night = int(not awake(guess, q.t))
    if owner == q.fact.holder:
        return Outcome(1, night, next_awake(guess, q.t) + REPLY - q.t, first_try=True)
    redirect = next_awake(guess, q.t) + REPLY          # "not me"
    resend = next_awake(asker, redirect)                # the asker tries again
    if q.fact.kind == "hidden":                         # the owner can't say who knows, so: the group chat
        chat = group_chat(team, Question(q.asker, resend, q.fact))
        return Outcome(1 + chat.notified, night + chat.night, resend - q.t + chat.minutes, first_try=False)
    night += int(not awake(holder, resend))
    return Outcome(2, night, next_awake(holder, resend) + REPLY - q.t, first_try=False)


class Agents:
    """The real agents for one team. Each question gets a fresh network, so questions don't help each other."""

    def __init__(self, team: Team):
        self.team = team
        self.cards = build_cards(team.data, team.root / "repo", START)
        self.spaces = {p["id"]: Workspace(team.root / "workspaces" / p["id"]) for p in team.people}

    def network(self, t: int) -> Network:
        net = Network(self.team.data)
        for person in self.team.people:
            pid = person["id"]
            net.add(PersonalAgent(person, self.spaces[pid], Policy.from_dict(person.get("policy")),
                                  self.cards[pid], self.team.data, None))
        net.start(t)
        return net

    def ask(self, q: Question) -> Outcome:
        net = self.network(q.t)
        me = net.agents[q.asker]
        hits = [pid for pid, _ in me.find_who_knows(q.fact.question)]
        quotes = me.ask_question(q.fact.question, people=hits) if hits else []
        answered = any(q.fact.text in a["text"] for _, a in quotes)
        if not answered:  # searching everyone else's shareable notes costs no one any attention
            rest = [p for p in net.others(q.asker) if p not in hits]
            quotes = me.ask_question(q.fact.question, people=rest)
            answered = any(q.fact.text in a["text"] for _, a in quotes)
        ranked = me.rank(q.fact.question, hits)
        out = Outcome(0, 0, 0, first_try=answered or (ranked[:1] == [q.fact.holder]), found=q.fact.holder in hits)
        when = q.t
        if not answered:
            for pid in ranked[:HOPS]:  # hand it to the best match; if they say "not me", try the next one
                net.advance_to(when)
                me.pass_on(q.fact.question, [pid])
                when = next_awake(self.team.person(pid), when) + REPLY
                if pid == q.fact.holder:
                    out.minutes = when - q.t
                    break
            else:  # the agents missed the person who knows: fall back to the group chat, and pay for it
                when = next_awake(self.team.person(q.asker), when)
                chat = group_chat(self.team, Question(q.asker, when, q.fact))
                out.minutes, out.notified, out.night = when - q.t + chat.minutes, chat.notified, chat.night
                out.fallback = True
        self._count(net, q, out)
        return out

    def _count(self, net: Network, q: Question, out: Outcome) -> None:
        asleep, buzzed = set(), set()
        for s in net.steps:
            if s["type"] == "status":
                (asleep.add if s["state"] == "asleep" else asleep.discard)(s["person"])
            elif s["type"] in ("phone", "decision") and s["person"] != q.asker:
                out.night += s["person"] in asleep
                out.agent_night += s["person"] in asleep
                if s.get("tone") == "receipts":  # the once-a-morning list of what the agent did unasked
                    out.summary_lines += s["text"].count("\n- ")
                elif not s.get("key", "").endswith("_receipts"):
                    buzzed.add(s["person"])
            elif s["type"] == "msg" and not s["kind"].startswith("reply:"):
                out.messages += 1
            elif s["type"] == "blocked":
                out.blocked += 1
            if s["type"] == "msg":
                for path in s.get("files", []):
                    owner = net.agents.get(s["sender"])
                    out.private_sent += bool(owner and owner.policy.tier(path) == NEVER)
        for pid, agent in net.agents.items():
            if pid != q.asker and agent.digest:
                buzzed.add(pid)  # a question waiting in their morning summary still needs them
            out.summary_lines += len(agent.receipts)
            for (owner, path) in agent.quotes:
                out.private_sent += net.agents[owner].policy.tier(path) == NEVER
        out.notified += len(buzzed)


# ------------------------------------------------------------------ summary

def _pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))]


def summarize(outcomes: list, weeks: int = 1) -> dict:
    minutes = [o.minutes for o in outcomes]
    n = len(outcomes)
    return {
        "questions": n,
        "notified_per_question": round(sum(o.notified for o in outcomes) / n, 2),
        "median_notified": statistics.median(o.notified for o in outcomes),
        "night_pings": sum(o.night for o in outcomes),
        "night_pings_per_week": round(sum(o.night for o in outcomes) / weeks),
        "fallbacks": sum(o.fallback for o in outcomes),
        "agent_night_pings": sum(o.agent_night for o in outcomes),
        "night_pings_per_question": round(sum(o.night for o in outcomes) / n, 2),
        "mean_minutes": round(statistics.mean(minutes)),
        "median_minutes": statistics.median(minutes),
        "p90_minutes": _pct(minutes, 0.9),
        "answered_at_once": round(sum(1 for m in minutes if m == 0) / n, 3),
        "first_try": round(sum(o.first_try for o in outcomes) / n, 3),
        "found": round(sum(o.found for o in outcomes) / n, 3),
        "messages_per_question": round(sum(o.messages for o in outcomes) / n, 1),
        "summary_lines_per_question": round(sum(o.summary_lines for o in outcomes) / n, 2),
        "blocked": sum(o.blocked for o in outcomes),
        "private_files_sent": sum(o.private_sent for o in outcomes),
    }


ARMS = ("group_chat", "best_guess", "whoknows")


def run_team(size: int, seed: int, written: float = 0.5) -> tuple[list, dict]:
    """One generated team, one week of questions, all three ways. Returns the questions and outcomes."""
    with tempfile.TemporaryDirectory() as tmp:
        team = make_team(Path(tmp), size, seed, written)
        questions = make_questions(team, seed)
        agents = Agents(team)
        outcomes = {"group_chat": [group_chat(team, q) for q in questions],
                    "best_guess": [best_guess(team, q) for q in questions],
                    "whoknows": [agents.ask(q) for q in questions]}
        asleep = [not awake(team.person(q.fact.holder), q.t) for q in questions]
        return [(q.fact.kind, a) for q, a in zip(questions, asleep)], outcomes


def run_teams(size: int, seeds, written: float = 0.5) -> dict:
    """Several teams of the same size, each with its own week of questions, pooled."""
    asked, pooled = [], {arm: [] for arm in ARMS}
    for seed in seeds:
        qs, outcomes = run_team(size, seed, written)
        asked += qs
        for arm in ARMS:
            pooled[arm] += outcomes[arm]
    n = len(asked)
    return {
        "team": size, "written": written, "weeks": len(seeds), "questions": n,
        "change_questions": round(sum(kind == "change" for kind, _ in asked) / n, 3),
        "hidden_questions": round(sum(kind == "hidden" for kind, _ in asked) / n, 3),
        "asked_while_holder_asleep": round(sum(a for _, a in asked) / n, 3),
        "arms": {arm: summarize(pooled[arm], len(seeds)) for arm in ARMS},
    }


def run_all(seeds=range(1, 6), main_size: int = 30, sizes=(5, 10, 20, 30, 50),
            written=(0.0, 0.25, 0.5, 0.75)) -> dict:
    seeds = list(seeds)
    main = run_teams(main_size, seeds)
    return {
        "seeds": seeds,
        "reply_minutes": REPLY,
        "assumptions": ASSUMPTIONS,
        "main": main,
        "written": [main if w == 0.5 else run_teams(main_size, seeds, w) for w in written],
        "sizes": [main if s == main_size else run_teams(s, seeds) for s in sizes],
    }


# ------------------------------------------------------------------- output

def _time(m) -> str:
    m = int(round(m))
    if m == 0:
        return "0 min"
    h, mm = divmod(m, 60)
    return f"{h}h {mm:02d}m" if h else f"{mm} min"


def tables(results: dict) -> str:
    main = results["main"]
    a = main["arms"]
    names = [("group_chat", "Group chat"), ("best_guess", "Message your best guess"), ("whoknows", "WhoKnows")]
    rows = [
        ("People notified per question", lambda s: f"{s['notified_per_question']:.1f}"),
        ("Notifications that reached someone asleep, per week", lambda s: f"{s['night_pings_per_week']:,}"),
        ("Average wait for the answer", lambda s: _time(s["mean_minutes"])),
        ("Wait for the slowest 1 in 10", lambda s: _time(s["p90_minutes"])),
        ("Answered on the spot", lambda s: f"{s['answered_at_once']:.0%}"),
        ("First person contacted knew the answer", lambda s: f"{s['first_try']:.0%}"),
    ]
    out = [f"Teams of {main['team']}, one week each, {main['weeks']} teams, {main['questions']} questions.", "",
           "| | " + " | ".join(label for _, label in names) + " |", "|---|---|---|---|"]
    for label, fmt in rows:
        out.append(f"| {label} | " + " | ".join(fmt(a[key]) for key, _ in names) + " |")
    w = a["whoknows"]
    out += ["", f"WhoKnows agents sent {w['messages_per_question']:.0f} agent to agent messages per question, "
                f"found the person who knew {w['found']:.0%} of the time, fell back to the group chat "
                f"{w['fallbacks']} times (every one of its night notifications; the agents caused "
                f"{w['agent_night_pings']}), and added "
                f"{w['summary_lines_per_question']:.1f} lines per question to sleeping teammates' morning "
                f"summaries. Gate blocks: {w['blocked']}. Private files sent: {w['private_files_sent']}.", ""]
    out += ["| Written in shareable notes | " + " | ".join(f"{r['written']:.0%}" for r in results["written"]) + " |",
            "|---|" + "---|" * len(results["written"])]
    for label, key, fmt in (("People notified per question", "notified_per_question", lambda v: f"{v:.1f}"),
                            ("Average wait", "mean_minutes", _time),
                            ("Notifications to someone asleep, per week", "night_pings_per_week",
                             lambda v: f"{v:,}")):
        out.append(f"| {label} | " + " | ".join(fmt(r["arms"]["whoknows"][key]) for r in results["written"]) + " |")
    out += ["", "| Team size | " + " | ".join(str(r["team"]) for r in results["sizes"]) + " |",
            "|---|" + "---|" * len(results["sizes"])]
    for key, label in names:
        out.append(f"| {label}: people notified | "
                   + " | ".join(f"{r['arms'][key]['notified_per_question']:.1f}" for r in results["sizes"]) + " |")
    return "\n".join(out)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--teams", type=int, default=5, help="generated teams per row (seeds 1 to N)")
    parser.add_argument("--out", help="write the results as JSON here")
    args = parser.parse_args(argv)
    results = run_all(range(1, args.teams + 1))
    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=1))
    print(tables(results))


if __name__ == "__main__":
    main()
