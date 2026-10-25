"""What each person works on, learned the way a teammate would.

An agent builds its person's card from four places: the team plan, the repo's
CODEOWNERS file, recent git commits, and what the person told their own agent
("I'm doing the README tonight"). The card stays with the agent. Other agents
only ever get short answers derived from it.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from . import clock

RANK = {"owner": 3, "touched": 2, "claims": 1}


@dataclass
class Claim:
    part: str
    level: str   # owner | touched | claims
    why: str     # one shareable line, like "owns the Payments API"
    when: float = 0.0


@dataclass
class Card:
    person: str
    claims: list = field(default_factory=list)

    def best_for(self, part_ids) -> Claim | None:
        pool = [c for c in self.claims if c.part in part_ids]
        if not pool:
            return None
        return max(pool, key=lambda c: (RANK[c.level], c.when))

    def known_parts(self) -> list[str]:
        """Parts this person knows: ones they own or have changed recently. Part names only."""
        return sorted({c.part for c in self.claims if c.level in ("owner", "touched")})

    def public_claims(self) -> list[tuple[str, str]]:
        """What goes on the team board: part ids this person owns or has claimed. Nothing else."""
        best: dict[str, str] = {}
        for c in self.claims:
            if c.level in ("owner", "claims") and RANK[c.level] > RANK.get(best.get(c.part, ""), 0):
                best[c.part] = c.level
        return sorted(best.items())


def _has(text: str, phrase: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(phrase.lower()) + r"(?![a-z0-9])"
    return re.search(pattern, text.lower()) is not None


def parts_in(text: str, parts) -> list[str]:
    """Part ids whose keywords appear in a question."""
    return [p["id"] for p in parts if any(_has(text, k) for k in p.get("keywords", ()))]


def part_for_path(path: str, parts) -> str | None:
    for p in parts:
        if any(path == pre or path.startswith(pre) for pre in p.get("paths", ())):
            return p["id"]
    words = re.sub(r"[/._-]+", " ", path)
    for p in parts:
        if any(_has(words, k) for k in p.get("keywords", ())):
            return p["id"]
    return None


def read_codeowners(repo: Path) -> list[tuple[str, str]]:
    rules = []
    path = Path(repo) / "CODEOWNERS"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            pattern, *owners = line.split()
            rules.extend((pattern.lstrip("/"), owner.lstrip("@")) for owner in owners)
    return rules


def read_commits(repo: Path, since: datetime) -> list[dict]:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "log", f"--since={since.isoformat()}", "--name-only",
             "--format=\x1e%ae\x1f%at\x1f%s"],
            capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    commits = []
    for chunk in out.split("\x1e"):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        head, *files = chunk.split("\n")
        email, at, subject = head.split("\x1f")
        commits.append({"author": email.split("@")[0], "at": int(at), "subject": subject,
                        "files": [f for f in files if f.strip()]})
    return commits


def when_words(epoch: float, now: datetime) -> str:
    t = datetime.fromtimestamp(epoch, now.tzinfo)
    days = (now.date() - t.date()).days
    at = clock.fmt(t.hour * 60 + t.minute)
    if days <= 0:
        return f"tonight at {at}" if t.hour < 5 else f"today at {at}"
    if days == 1:
        return f"yesterday at {at}"
    return f"on {t.strftime('%A')} at {at}"


def join(items) -> str:
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def build_cards(team: dict, repo: Path, now: datetime, days: int = 3) -> dict[str, Card]:
    parts = team["parts"]
    names = {p["id"]: p["name"] for p in parts}
    cards = {person["id"]: Card(person["id"]) for person in team["people"]}
    stamp = now.timestamp()

    for p in parts:
        if p.get("owner") in cards:
            cards[p["owner"]].claims.append(Claim(p["id"], "owner", f"owns the {p['name']}", stamp))

    for pattern, handle in read_codeowners(repo):
        part = part_for_path(pattern, parts)
        card = cards.get(handle)
        if card and part and not any(c.part == part and c.level == "owner" for c in card.claims):
            card.claims.append(Claim(part, "owner", f"owns the {names[part]} (CODEOWNERS)", stamp))

    for commit in read_commits(repo, now - timedelta(days=days)):
        card = cards.get(commit["author"])
        if not card:
            continue
        by_part: dict[str, list[str]] = {}
        for f in commit["files"]:
            part = part_for_path(f, parts)
            if part:
                by_part.setdefault(part, []).append(f)
        subject = re.sub(r"^[\w ]+:\s*", "", commit["subject"])
        for part, files in by_part.items():
            why = f"changed {join(sorted(files))} {when_words(commit['at'], now)}: {subject}"
            card.claims.append(Claim(part, "touched", why, commit["at"]))

    for person in team["people"]:
        for said in person.get("says", ()):
            cards[person["id"]].claims.append(
                Claim(said["part"], "claims", f"said they're doing {said['detail']} tonight", stamp))
    return cards
