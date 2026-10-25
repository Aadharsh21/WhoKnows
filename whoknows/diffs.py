"""Line diffs: what a change touches, how big it is, and whether two changes collide."""

from __future__ import annotations

import difflib


def unified(old: str, new: str, path: str) -> str:
    return "".join(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True), f"a/{path}", f"b/{path}", n=1))


def _opcodes(old: str, new: str):
    return difflib.SequenceMatcher(None, old.splitlines(), new.splitlines(), autojunk=False).get_opcodes()


def stats(old: str, new: str) -> tuple[int, int]:
    """(lines added, lines removed)."""
    added = removed = 0
    for tag, i1, i2, j1, j2 in _opcodes(old, new):
        if tag in ("replace", "delete"):
            removed += i2 - i1
        if tag in ("replace", "insert"):
            added += j2 - j1
    return added, removed


def touched(old: str, new: str) -> list[tuple[int, int]]:
    """Ranges of the old text's lines a change touches, 1-based and inclusive.

    An insertion counts as touching the lines on both sides of it, so two edits
    right next to each other are treated as a collision. Better to ask the
    owner than to merge silently.
    """
    ranges = []
    for tag, i1, i2, j1, j2 in _opcodes(old, new):
        if tag == "equal":
            continue
        if i1 == i2:
            ranges.append((max(i1, 1), i1 + 1))
        else:
            ranges.append((i1 + 1, i2))
    return ranges


def overlaps(a, b) -> bool:
    return any(s1 <= e2 and s2 <= e1 for s1, e1 in a for s2, e2 in b)
