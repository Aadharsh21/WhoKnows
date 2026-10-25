"""Finding the passage in one person's own files that answers a question.

There is no shared index. Each agent searches only its own person's files, and
only the ones its person lets it share, then returns a short passage copied
exactly from the file so the gate can check it against the original.
"""

from __future__ import annotations

import re

STOP = set("""
a an the and or but if of to in on at by for from with without about into over under is are was were be been being
do does did doing have has had having i you he she it we they me him her them my your his its our their this that these
those what which who whom whose why how when where can could would should will shall may might must not no yes get gets
got make makes made any some all just only also very there here than then so too up down out off again once more most
other such own same both each few anyone anybody know knows need needs work works working tell said say
""".split())


def stem(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("es") and word[-3] in "sxz":
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    if len(word) > 5 and word.endswith("ing"):
        return word[:-3]
    if len(word) > 4 and word.endswith("ed"):
        return word[:-2]
    return word


def terms(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {stem(w) for w in words if (len(w) >= 3 or w.isdigit()) and w not in STOP}


def best_passage(text: str, want: set[str], max_lines: int = 3) -> tuple[str | None, int]:
    """The paragraph sharing the most terms with the question, trimmed around its best line."""
    if not want:
        return None, 0
    lines = text.split("\n")
    paragraphs, current = [], []
    for i, line in enumerate(lines):
        if line.strip():
            current.append(i)
        elif current:
            paragraphs.append(current)
            current = []
    if current:
        paragraphs.append(current)
    best_score, best = 0, None
    for para in paragraphs:
        found = set()
        for i in para:
            found |= terms(lines[i]) & want
        if len(found) > best_score:
            best_score, best = len(found), para
    if not best:
        return None, 0
    while len(best) > 1 and lines[best[0]].lstrip().startswith("#"):
        best = best[1:]  # a heading isn't an answer
    if len(best) > max_lines:
        scores = [len(terms(lines[i]) & want) for i in best]
        k = scores.index(max(scores))
        start = max(0, min(k - 1, len(best) - max_lines))
        best = best[start:start + max_lines]
    return "\n".join(lines[i] for i in best), best_score
