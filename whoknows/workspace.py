"""One person's folder. Every path is checked so an agent can never reach outside it."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .policy import normalize


class OutsideWorkspace(ValueError):
    pass


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


class Workspace:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        # path -> list of (text before the write, hash after the write), for undo
        self.history: dict[str, list[tuple[str | None, str]]] = {}

    def resolve(self, rel: str) -> Path:
        rel = normalize(rel)
        candidate = Path(rel)
        if not rel or candidate.is_absolute() or ".." in candidate.parts:
            raise OutsideWorkspace(rel)
        full = (self.root / candidate).resolve()
        if full != self.root and self.root not in full.parents:
            raise OutsideWorkspace(rel)
        return full

    def exists(self, rel: str) -> bool:
        try:
            return self.resolve(rel).is_file()
        except OutsideWorkspace:
            return False

    def files(self) -> list[str]:
        return sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file())

    def read(self, rel: str) -> str:
        return self.resolve(rel).read_text(encoding="utf-8")

    def hash(self, rel: str) -> str | None:
        return digest(self.read(rel)) if self.exists(rel) else None

    def write(self, rel: str, text: str) -> None:
        path = self.resolve(rel)
        old = path.read_text(encoding="utf-8") if path.is_file() else None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.history.setdefault(normalize(rel), []).append((old, digest(text)))

    def undo(self, rel: str) -> bool:
        """Put back the version before the last write, unless the file changed since."""
        rel = normalize(rel)
        past = self.history.get(rel)
        if not past:
            return False
        old, written = past[-1]
        if self.hash(rel) != written:
            return False  # someone changed it after; don't clobber their work
        past.pop()
        path = self.resolve(rel)
        if old is None:
            path.unlink()
        else:
            path.write_text(old, encoding="utf-8")
        return True
