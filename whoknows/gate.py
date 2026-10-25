"""The gate: everything an agent sends passes through here first.

It doesn't trust the agent. It re-reads every shared file from the sender's own
folder, re-applies the owner's rules, and scans all text for things that look
like keys. An agent that has been tricked still can't get a private file past it.
"""

from __future__ import annotations

import re

from .policy import ASK, NEVER

SECRET_PATTERNS = (
    re.compile(r"sk_(?:live|test)_[A-Za-z0-9]{8,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"(?i)\b(?:password|passwd|api[_-]?key|secret[_-]?key)\s*[:=]\s*\S{6,}"),
)


def looks_secret(text: str) -> bool:
    return any(p.search(text) for p in SECRET_PATTERNS)


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from strings(item)


class Gate:
    def __init__(self, owner: str, workspace, policy):
        self.owner = owner
        self.ws = workspace
        self.policy = policy
        self.approved: dict[tuple[str, str], str] = {}  # (path, recipient) -> approved content digest
        self.blocked: list[dict] = []                 # what this gate stopped

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

    def check(self, kind: str, body: dict | None, recipient: str) -> tuple[bool, str]:
        body = body or {}
        for item in body.get("shared", []) or []:
            path = item.get("path", "")
            if not self.ws.exists(path):
                return self._stop(kind, recipient, "not this person's file")
            if item.get("text") != self.ws.read(path):
                return self._stop(kind, recipient, "doesn't match the file on disk")
            tier = self.policy.tier(path)
            if tier == NEVER:
                return self._stop(kind, recipient, "private file")
            if tier == ASK and not self.allowed(path, recipient):
                return self._stop(kind, recipient, "needs the owner's OK first")
        for item in body.get("answers", []) or []:
            path = item.get("path", "")
            if not self.ws.exists(path):
                return self._stop(kind, recipient, "not this person's file")
            if not item.get("text") or item["text"] not in self.ws.read(path):
                return self._stop(kind, recipient, "quote isn't in the file")
            tier = self.policy.tier(path)
            if tier == NEVER:
                return self._stop(kind, recipient, "private file")
            if tier == ASK and not self.allowed(path, recipient):
                return self._stop(kind, recipient, "needs the owner's OK first")
        for item in body.get("mentions", []) or []:
            if self.policy.tier(item.get("path", "")) == NEVER:
                return self._stop(kind, recipient, "private file")
        if any(looks_secret(s) for s in strings(body)):
            return self._stop(kind, recipient, "looks like a secret")
        return True, ""

    def _stop(self, kind: str, recipient: str, reason: str) -> tuple[bool, str]:
        self.blocked.append({"kind": kind, "to": recipient, "reason": reason})
        return False, reason
