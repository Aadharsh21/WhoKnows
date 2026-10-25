"""Each person's sharing rules.

Every file is in one of three tiers:
  auto   the agent may share it on its own
  ask    the agent asks its person first
  never  it never leaves, and the agent won't even say it exists

Anything a person hasn't listed is "ask". Secrets and personal folders are
always "never", whatever a person's own rules say.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase

AUTO, ASK, NEVER = "auto", "ask", "never"

# No rule a person writes can open these up.
ALWAYS_PRIVATE = (
    ".env*", "*/.env*", "*.env", "*.pem", "*.key", "*id_rsa*",
    "*secret*", "*password*", "*credential*", "personal/*", "*/personal/*",
)


def normalize(path: str) -> str:
    path = str(path).replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


@dataclass(frozen=True)
class Policy:
    auto: tuple = ()
    ask: tuple = ()
    never: tuple = ()

    @classmethod
    def from_dict(cls, rules: dict | None) -> "Policy":
        rules = rules or {}
        return cls(tuple(rules.get("auto", ())), tuple(rules.get("ask", ())), tuple(rules.get("never", ())))

    def tier(self, path: str) -> str:
        path = normalize(path)
        if any(fnmatchcase(path.lower(), rule) for rule in ALWAYS_PRIVATE):
            return NEVER
        if any(fnmatchcase(path, rule) for rule in self.never):
            return NEVER
        if any(fnmatchcase(path, rule) for rule in self.auto):
            return AUTO
        return ASK
