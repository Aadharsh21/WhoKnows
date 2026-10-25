"""WhoKnows on a real git repository.

Every recent contributor gets an agent that knows only their own commits, plus
any CODEOWNERS lines that name them. Ask who knows something and every agent
checks its own person's history; the ones who know answer with one line of
why. The agents of the people who know then quote their own commit messages
about it, naming the commit. Nobody is notified.

    python3 -m whoknows.repo PATH "who knows the session cookies?"
    python3 -m whoknows.repo PATH                  # type questions; an empty line quits
    python3 -m whoknows.repo PATH --json "..."     # the same, as JSON
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from fnmatch import fnmatchcase
from pathlib import Path

from . import search
from .agent import PersonalAgent
from .cards import RANK, Card, Claim, when_words
from .network import Network
from .policy import Policy
from .workspace import Workspace

# Words that say nothing about which part of a codebase a question is about.
_GENERIC = set("""
code file files function functions method methods class logic module modules part parts thing things stuff piece
bug bugs fix fixes fixed issue issues problem change changes changed update updates updated add added remove
removed delete deleted use used using make made new old test tests src lib main index init readme work works
right wrong break broke broken thing write wrote written why who what know knows knew someone anyone person
""".split())
GENERIC = _GENERIC | {search.stem(w) for w in _GENERIC}
SKIP = re.compile(r"(?i)(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|cargo\.lock|go\.sum)$"
                  r"|\.(png|jpe?g|gif|svg|ico|webp|pdf|zip|gz|woff2?|ttf|min\.js|map|lock)$")
BOT = re.compile(r"(?i)\[bot\]|dependabot|github-actions|pre-commit-ci|renovate|^noreply@github\.com$")
CODEOWNERS = ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS")
TRAILER = re.compile(r"(?im)^\s*(co-authored-by|signed-off-by|reviewed-by|acked-by|reported-by|tested-by):.*$")
EMAIL = re.compile(r"<?[\w.+-]+@[\w-]+(\.[\w-]+)+>?")


@dataclass
class RepoClaim(Claim):
    """A claim from one commit, with the words it is about: the file's path and what the commit said."""
    terms: frozenset = frozenset()


def path_words(path: str) -> set[str]:
    """Words in a file path: directories and the file name, in snake_case and camelCase pieces. Not the extension."""
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", path)
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", stem)
    return search.terms(re.sub(r"[/_.\-]+", " ", spaced)) - GENERIC


# ------------------------------------------------------------------ history

def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


def read_history(repo: Path, days: int = 1825, max_commits: int = 4000) -> list[dict]:
    """Recent non-merge commits: who, when, what they said, and which files."""
    recent = [int(t) for t in git(repo, "log", "-n500", "--format=%ct").split()]
    if not recent:
        return []
    since = datetime.fromtimestamp(max(recent) - days * 86400, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = git(repo, "log", "--no-merges", f"--since={since}", f"-n{max_commits}", "--name-only",
              "--format=%x1e%h%x1f%an%x1f%ae%x1f%at%x1f%s%x1f%b%x1d")
    commits = []
    for chunk in out.split("\x1e"):
        if "\x1d" not in chunk:
            continue
        head, names = chunk.split("\x1d", 1)
        sha, name, email, at, subject, body = head.split("\x1f", 5)
        files = [f for f in names.split("\n") if f.strip() and not SKIP.search(f)]
        body = EMAIL.sub("", TRAILER.sub("", body)).strip()  # no co-author lines or addresses in quotes
        commits.append({"sha": sha, "name": name.strip(), "email": email.strip().lower(), "at": int(at),
                        "subject": EMAIL.sub("", subject).strip(), "body": body, "files": files})
    return commits


def read_codeowners(repo: Path) -> list[tuple[str, str]]:
    rules = []
    for rel in CODEOWNERS:
        path = repo / rel
        if path.is_file():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.split("#", 1)[0].strip()
                if line:
                    pattern, *owners = line.split()
                    rules += [(pattern, owner) for owner in owners]
    return rules


def owns(pattern: str, path: str) -> bool:
    """A small subset of CODEOWNERS matching: directories, globs, anchored and unanchored patterns."""
    anchored, p = pattern.startswith("/"), pattern.strip("/")
    if not p or p in ("*", "**"):
        return True
    candidates = [path] if anchored else [path] + [path.split("/", i)[-1] for i in range(1, path.count("/") + 1)]
    for c in candidates:
        if fnmatchcase(c, p) or c.startswith(p + "/") or fnmatchcase(c, p + "/*") or fnmatchcase(c, p.rstrip("*") + "*"):
            return True
    return False


# --------------------------------------------------------------- the team

def _slug(name: str, taken: set) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "someone"
    slug, n = base, 2
    while slug in taken:
        slug, n = f"{base}-{n}", n + 1
    taken.add(slug)
    return slug


def build_team(repo: Path, days: int = 1825, top: int = 60, now: float | None = None) -> dict:
    """People, parts and cards for a real repo, from its own history."""
    repo = Path(repo)
    now = time.time() if now is None else now
    commits = [c for c in read_history(repo, days) if not BOT.search(c["name"]) and not BOT.search(c["email"])]

    # One person per name, whatever addresses they committed from.
    key_of = {}
    for c in commits:
        key_of.setdefault(c["email"], " ".join(c["name"].lower().split()))
    counts = Counter(key_of[c["email"]] for c in commits)
    keep = {k for k, _ in counts.most_common(top)}
    names, emails, taken = {}, defaultdict(set), set()
    for c in commits:
        k = key_of[c["email"]]
        if k in keep:
            names.setdefault(k, c["name"])
            emails[k].add(c["email"])
    order = sorted(keep, key=lambda k: (-counts[k], k))  # most active first; ties by name, so runs repeat
    pid = {k: _slug(names[k], taken) for k in order}

    # Parts are files with recent history. A person knows a file through their own commits to it, and each
    # claim is about the file's path words plus what that one commit said. Nobody borrows anyone else's words.
    files = sorted({f for c in commits for f in c["files"]})
    # A word in most paths (the package's own name, like "flask" in src/flask/) says nothing about any one part.
    df = Counter(w for f in files for w in path_words(f))
    common = {w for w, n in df.items() if len(files) >= 10 and n > 0.4 * len(files)} | path_words(repo.name)
    part_terms = {f: frozenset(path_words(f) - common) for f in files}
    parts = [{"id": f, "name": f, "owner": None, "paths": [f], "keywords": []} for f in files]

    now_dt = datetime.fromtimestamp(now, timezone.utc).astimezone()
    times = Counter((key_of[c["email"]], f) for c in commits for f in c["files"])
    cards = {pid[k]: Card(pid[k]) for k in order}
    for c in commits:
        k = key_of[c["email"]]
        if k not in keep:
            continue
        said = frozenset(search.terms(c["subject"] + " " + c["body"][:400]) - GENERIC - common)
        for f in c["files"]:
            more = times[(k, f)] - 1
            tail = f" (one of {more + 1} changes they made to it)" if more else ""
            why = f"changed {f} {when_words(c['at'], now_dt)}: {c['subject']}{tail}"
            cards[pid[k]].claims.append(RepoClaim(f, "touched", why, c["at"], part_terms[f] | said))

    # CODEOWNERS handles are GitHub logins; match them to people by address or name where we can.
    def person_for(handle: str):
        h = handle.lstrip("@").lower()
        if "/" in h:  # a GitHub team, not a person
            return None
        for k in order:
            local = {e.split("@")[0].split("+")[-1] for e in emails[k]}
            if h in emails[k] or h in local or h == k.replace(" ", ""):
                return pid[k]
        return None

    for pattern, handle in read_codeowners(repo):
        who = person_for(handle)
        if who:
            for f in part_terms:
                if owns(pattern, f):
                    cards[who].claims.append(RepoClaim(f, "owner", f"is a code owner of {f} (CODEOWNERS: {pattern})",
                                                       now, part_terms[f]))

    people = [{"id": pid[k], "name": names[k], "role": f"{counts[k]} commits", "sleep": [],
               "policy": {"auto": ["notes/*"]}} for k in order]
    notes = {pid[k]: [c for c in commits if key_of[c["email"]] == k] for k in order}
    return {"repo": repo.name, "people": people, "parts": parts, "part_terms": part_terms, "common": common,
            "cards": cards,
            "notes": notes, "commits": len(commits), "days": days}


# ----------------------------------------------------------------- agents

class RepoAgent(PersonalAgent):
    """A contributor's agent. It matches questions against the words in its own person's history."""

    @property
    def first(self) -> str:
        return self.person["name"]

    def on_question(self, body, sender):
        # Search the commit messages for what the question is about, not for words like "code" or "fix".
        skip = GENERIC | self.net.common_words
        words = re.findall(r"[A-Za-z0-9]+", body.get("question", ""))
        kept = [w for w in words if w.lower() not in skip and search.stem(w.lower()) not in skip]
        return super().on_question({**body, "question": " ".join(kept)}, sender)

    def on_who_knows(self, body, sender):
        want = search.terms(body.get("question", "")) - GENERIC - self.net.common_words
        if not want:
            return {"answer": "no"}
        need = 1 if len(want) <= 3 else 2
        paths = self.net.part_terms
        best = None
        for claim in self.card.claims:
            score = len(want & claim.terms)
            if score >= need:
                # Among equally good claims, prefer the file whose own name matches (sessions.py over CHANGES.rst).
                key = (score, len(want & paths.get(claim.part, frozenset())), RANK[claim.level], claim.when)
                if best is None or key > best[0]:
                    best = (key, claim)
        if not best:
            return {"answer": "no"}
        (score, _, _, when), claim = best
        return {"answer": claim.level, "part": claim.part, "why": claim.why, "match": score, "when": when}


def _notes_text(commits: list) -> str:
    """A contributor's own commit messages, one paragraph each, newest first."""
    blocks = []
    for c in sorted(commits, key=lambda c: -c["at"]):
        day = datetime.fromtimestamp(c["at"], timezone.utc).strftime("%Y-%m-%d")
        body = "\n".join(line for line in c["body"].splitlines() if line.strip())
        blocks.append(f"{c['subject']} (commit {c['sha']}, {day})" + (f"\n{body}" if body else ""))
    return "\n\n".join(blocks) + "\n"


class RepoTeam:
    """A network of agents for one repo, plus an asker who isn't on the team."""

    def __init__(self, repo, days: int = 1825, top: int = 60, now: float | None = None, workdir=None):
        self.info = build_team(Path(repo), days, top, now)
        self._tmp = tempfile.TemporaryDirectory() if workdir is None else None
        root = Path(workdir or self._tmp.name)
        team = {"project": {"name": self.info["repo"]}, "people": self.info["people"], "parts": self.info["parts"]}
        self.net = Network(team)
        self.net.part_terms = self.info["part_terms"]
        self.net.common_words = frozenset(self.info["common"])
        for person in self.info["people"]:
            ws_root = root / person["id"]
            (ws_root / "notes").mkdir(parents=True, exist_ok=True)
            (ws_root / "notes" / "commits.md").write_text(_notes_text(self.info["notes"][person["id"]]), encoding="utf-8")
            self.net.add(RepoAgent(person, Workspace(ws_root), Policy.from_dict(person["policy"]),
                                   self.info["cards"][person["id"]], team, None))
        you = {"id": "you", "name": "You", "role": "asking", "sleep": []}
        (root / "you").mkdir(parents=True, exist_ok=True)
        self.you = PersonalAgent(you, Workspace(root / "you"), Policy(), Card("you"), team, None)
        self.net.add(self.you)
        self.net.start(0)

    def close(self):
        if self._tmp:
            self._tmp.cleanup()

    def ask(self, question: str, show: int = 5, quote_from: int = 3) -> dict:
        """Who knows, ranked, and what the top people wrote about it in their own commit messages."""
        start = len(self.net.steps)
        hits = self.you.find_who_knows(question)
        hits.sort(key=lambda h: (-h[1].get("match", 0), -RANK[h[1]["answer"]], -h[1].get("when", 0)))
        if hits:  # keep the people who match nearly as well as the best one
            top = hits[0][1].get("match", 0)
            hits = [h for h in hits if h[1].get("match", 0) >= max(1, top - 1)]
        self.you.last_hits = [pid for pid, _ in hits]
        quotes = self.you.ask_question(question, people=self.you.last_hits[:quote_from]) if hits else []
        steps = self.net.steps[start:]
        notified = {s["person"] for s in steps if s["type"] in ("phone", "decision") and s["person"] != "you"}
        asked = sum(1 for s in steps if s["type"] == "msg" and s["kind"] == "who_knows")
        return {
            "question": question,
            "asked": asked,
            "know": len(hits),
            "who": [{"person": self.net.name(pid), "level": r["answer"], "why": r["why"]} for pid, r in hits[:show]],
            "quotes": [{"person": self.net.name(pid), "text": " ".join(q["text"].split())} for pid, q in quotes][:quote_from],
            "notified": len(notified),
            "blocked": sum(1 for s in steps if s["type"] == "blocked"),
            "messages": sum(1 for s in steps if s["type"] == "msg" and not s["kind"].startswith("reply:")),
        }


# -------------------------------------------------------------------- CLI

def render(result: dict) -> str:
    lines = [f"> {result['question']}",
             f"  Asked {result['asked']} agents at once. {result['know']} know, "
             f"{result['asked'] - result['know']} said no. People notified: {result['notified']}."]
    for n, w in enumerate(result["who"], 1):
        lines.append(f"  {n}. {w['person']} {w['why']}")
    if result["quotes"]:
        lines.append("  What they wrote, quoted from their own commit messages:")
        lines += [f"  - {q['person']}: \"{q['text'][:300]}{'...' if len(q['text']) > 300 else ''}\"" for q in result["quotes"]]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Ask a real git repo's contributors' agents who knows what.")
    parser.add_argument("repo", help="path to a git repository")
    parser.add_argument("questions", nargs="*", help="questions to ask; with none, type them one per line")
    parser.add_argument("--days", type=int, default=1825, help="how far back to read history (default 1825, five years)")
    parser.add_argument("--top", type=int, default=60, help="how many of the most active people get an agent")
    parser.add_argument("--json", action="store_true", help="print results as JSON")
    args = parser.parse_args(argv)
    try:
        team = RepoTeam(args.repo, args.days, args.top)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"{args.repo} doesn't look like a git repository.", file=sys.stderr)
        return 1
    info = team.info
    if not args.json:
        print(f"WhoKnows on {info['repo']}: {len(info['people'])} people with an agent, {len(info['parts'])} files, "
              f"{info['commits']} commits from the last {info['days']} days.\n")
    questions = args.questions or iter(lambda: input("? ").strip(), "")
    results = []
    try:
        for q in questions:
            r = team.ask(q)
            results.append(r)
            if not args.json:
                print(render(r) + "\n")
    except (EOFError, KeyboardInterrupt):
        pass
    if args.json:
        print(json.dumps({"repo": info["repo"], "people": len(info["people"]), "files": len(info["parts"]),
                          "commits": info["commits"], "days": info["days"], "results": results}, indent=1))
    team.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
